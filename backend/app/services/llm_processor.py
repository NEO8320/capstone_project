"""
LLM 처리 모듈 (요약, 카테고리 분류, 신뢰도 점수 산출)
======================================================

LLM 호출 우선순위 (NFR-E03: 환경변수로 유연하게 교체 가능):
  1순위: 로컬 Ollama (Llama 3) — LLM_PRIMARY_BASE_URL / LLM_PRIMARY_MODEL
  2순위: Claude Haiku          — ANTHROPIC_API_KEY가 있을 때만
  3순위: OpenAI 호환 원격       — OPENAI_API_KEY가 있을 때만

모든 모델명과 API 주소는 config.py / .env에서 관리하므로
코드 수정 없이 환경변수만 바꿔서 LLM 엔진을 교체할 수 있다.

신뢰도 점수 산출 공식:
  Score = (문체_중립성 x 0.30) + (정보_밀도 x 0.25)
        + (인용구_존재 x 0.25) + (기자_실명 x 0.20)

서킷 브레이커: 5회 연속 실패 시 30초간 호출 차단.
"""

import json
import re

import openai

from app.core.config import settings
from app.services.resilience import CircuitBreaker

# ── LLM API 전용 서킷 브레이커 ──
llm_circuit = CircuitBreaker(name="llm_api", failure_threshold=5, recovery_timeout=30.0)

# ── 유효 카테고리 목록 ──
VALID_CATEGORIES = ["정치", "경제", "사회", "생활/문화", "IT/과학", "세계"]

# ── LLM 프롬프트 템플릿 ──
SUMMARY_PROMPT = """다음 뉴스 기사를 분석하여 JSON 형식으로 응답해 주세요.

[기사 제목]
{title}

[기사 본문]
{body}

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "summary": "3줄 요약 (각 줄은 '\\n'으로 구분)",
  "category": "정치|경제|사회|생활/문화|IT/과학|세계 중 하나",
  "credibility": {{
    "tone_neutrality": 0~100 사이 정수 (감정적/선정적 표현이 없으면 높은 점수),
    "info_density": 0~100 사이 정수 (구체적 수치/데이터/팩트가 많으면 높은 점수),
    "has_quotes": 0~100 사이 정수 (직접 인용구가 있으면 높은 점수, 없으면 낮은 점수),
    "journalist_named": 0~100 사이 정수 (기자 실명이 있으면 100, 없으면 0)
  }}
}}"""


async def process_article_with_llm(
    title: str,
    body: str,
    journalist: str | None = None,
) -> dict | None:
    """
    LLM을 통해 기사를 분석한다: 3줄 요약 + 카테고리 분류 + 신뢰도 점수.

    호출 우선순위:
      1) 로컬 Ollama (Llama 3) — 항상 시도
      2) Claude Haiku          — ANTHROPIC_API_KEY 있을 때
      3) OpenAI 원격           — OPENAI_API_KEY 있을 때

    Args:
        title: 기사 제목
        body: 기사 본문 (정제 완료)
        journalist: 기자명 (없으면 None)

    Returns:
        {"summary": str, "category": str, "credibility": float}
        또는 실패 시 None
    """
    # 서킷 브레이커 확인
    if not llm_circuit.can_call():
        return None

    # 본문이 너무 길면 앞부분만 사용 (토큰 절약)
    truncated_body = body[:3000] if len(body) > 3000 else body
    prompt = SUMMARY_PROMPT.format(title=title, body=truncated_body)

    result = None

    # ── 1순위: 로컬 Ollama (Llama 3) ──
    result = await _call_ollama_local(prompt)

    # ── 2순위: Claude Haiku (API 키 있을 때만) ──
    if result is None and settings.ANTHROPIC_API_KEY:
        result = await _call_claude(prompt)

    # ── 3순위: OpenAI 호환 원격 (API 키 있을 때만) ──
    if result is None and settings.OPENAI_API_KEY:
        result = await _call_openai_remote(prompt)

    if result is None:
        await llm_circuit.record_failure()
        return None

    await llm_circuit.record_success()

    # ── 응답 파싱 및 신뢰도 점수 가중합산 ──
    try:
        parsed = _parse_llm_response(result, journalist)
        return parsed
    except Exception as e:
        print(f"[LLM] 응답 파싱 실패: {e}")
        return None


# ============================================================
# 1순위: 로컬 Ollama (OpenAI 호환 API)
# ============================================================
async def _call_ollama_local(prompt: str) -> str | None:
    """
    로컬 Ollama 서버에 OpenAI 호환 API로 요청한다.

    Ollama는 /v1/chat/completions 엔드포인트를 지원하므로
    openai 라이브러리를 그대로 사용하되 base_url만 변경한다.
    API 키는 불필요하지만, openai 라이브러리가 키를 요구하므로
    더미 문자열("ollama")을 전달한다.

    설정값:
      - LLM_PRIMARY_BASE_URL: http://localhost:11434/v1 (기본값)
      - LLM_PRIMARY_MODEL: llama3 (기본값)
    """
    try:
        client = openai.AsyncOpenAI(
            base_url=settings.LLM_PRIMARY_BASE_URL,
            api_key="ollama",  # 로컬 서버는 키 불필요, 더미값
        )
        response = await client.chat.completions.create(
            model=settings.LLM_PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3,
        )
        text = response.choices[0].message.content
        print(f"[LLM] Ollama 로컬 ({settings.LLM_PRIMARY_MODEL}) 호출 성공")
        return text
    except Exception as e:
        print(f"[LLM] Ollama 로컬 호출 실패: {e}")
        return None


# ============================================================
# 2순위: Claude Haiku (Anthropic API)
# ============================================================
async def _call_claude(prompt: str) -> str | None:
    """
    Anthropic Claude API를 호출한다.

    설정값:
      - LLM_FALLBACK_CLAUDE_MODEL (기본: claude-haiku-4-5-20251001)
      - ANTHROPIC_API_KEY (비어있으면 이 함수 자체가 호출되지 않음)
    """
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model=settings.LLM_FALLBACK_CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        print(f"[LLM] Claude ({settings.LLM_FALLBACK_CLAUDE_MODEL}) 호출 성공")
        return message.content[0].text
    except Exception as e:
        print(f"[LLM] Claude API 호출 실패: {e}")
        return None


# ============================================================
# 3순위: OpenAI 호환 원격 API
# ============================================================
async def _call_openai_remote(prompt: str) -> str | None:
    """
    OpenAI 호환 원격 API를 호출한다.

    설정값:
      - LLM_FALLBACK_OPENAI_BASE_URL (기본: https://api.openai.com/v1)
      - LLM_FALLBACK_OPENAI_MODEL (기본: gpt-4o-mini)
      - OPENAI_API_KEY (비어있으면 이 함수 자체가 호출되지 않음)
    """
    try:
        client = openai.AsyncOpenAI(
            base_url=settings.LLM_FALLBACK_OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
        )
        response = await client.chat.completions.create(
            model=settings.LLM_FALLBACK_OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3,
        )
        print(f"[LLM] OpenAI 원격 ({settings.LLM_FALLBACK_OPENAI_MODEL}) 호출 성공")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] OpenAI 원격 API 호출 실패: {e}")
        return None


# ============================================================
# 응답 파싱 + 신뢰도 점수 가중합산
# ============================================================
def _parse_llm_response(response_text: str, journalist: str | None) -> dict:
    """
    LLM 응답 JSON을 파싱하고 신뢰도 점수를 가중합산한다.

    신뢰도 점수 공식:
      Score = (tone_neutrality x 0.30) + (info_density x 0.25)
            + (has_quotes x 0.25) + (journalist_named x 0.20)
    """
    # JSON 블록 추출 (```json ... ``` 감싸진 경우 대비)
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        raise ValueError(f"JSON을 찾을 수 없음: {response_text[:200]}")

    data = json.loads(json_match.group())

    summary = data.get("summary", "요약 없음")

    category = data.get("category", "사회")
    if category not in VALID_CATEGORIES:
        category = "사회"

    cred = data.get("credibility", {})
    tone_neutrality = _clamp(cred.get("tone_neutrality", 50))
    info_density = _clamp(cred.get("info_density", 50))
    has_quotes = _clamp(cred.get("has_quotes", 50))

    if journalist and journalist.strip():
        journalist_named = 100
    else:
        journalist_named = _clamp(cred.get("journalist_named", 0))

    credibility_score = (
        tone_neutrality * 0.30
        + info_density * 0.25
        + has_quotes * 0.25
        + journalist_named * 0.20
    )

    return {
        "summary": summary,
        "category": category,
        "credibility": round(credibility_score, 2),
    }


def _clamp(value: int | float, min_val: float = 0, max_val: float = 100) -> float:
    """값을 [min_val, max_val] 범위로 클램핑한다."""
    try:
        return max(min_val, min(max_val, float(value)))
    except (TypeError, ValueError):
        return 50.0
