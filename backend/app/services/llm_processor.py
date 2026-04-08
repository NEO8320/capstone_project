"""
LLM 처리 모듈 (요약, 카테고리 분류, 신뢰도 점수 산출)
======================================================

기사 본문을 LLM(Claude Haiku 또는 GPT-4o-mini)에 전달하여:
  1. 3줄 요약 생성
  2. 6개 카테고리 중 하나로 분류
  3. 신뢰도 점수 산출 (0~100점)

신뢰도 점수 산출 공식:
  Score = (문체_중립성 × 0.30) + (정보_밀도 × 0.25)
        + (인용구_존재 × 0.25) + (기자_실명 × 0.20)

  각 항목은 0~100점 범위이며, 가중합산 결과도 0~100점.

LLM API 호출에는 서킷 브레이커가 적용되어
5회 연속 실패 시 30초간 호출이 차단된다.
"""

import json
import re

import anthropic
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

    Claude Haiku를 우선 시도하고, 실패 시 GPT-4o-mini로 폴백한다.

    Args:
        title: 기사 제목
        body: 기사 본문 (정제 완료)
        journalist: 기자명 (없으면 None)

    Returns:
        {
            "summary": str,         # 3줄 요약
            "category": str,        # 6개 카테고리 중 하나
            "credibility": float,   # 신뢰도 점수 (0~100)
        }
        또는 실패 시 None
    """
    # 서킷 브레이커 확인
    if not llm_circuit.can_call():
        return None

    # 본문이 너무 길면 앞부분만 사용 (토큰 절약)
    truncated_body = body[:3000] if len(body) > 3000 else body
    prompt = SUMMARY_PROMPT.format(title=title, body=truncated_body)

    # 1차 시도: Claude Haiku
    result = await _call_claude(prompt)

    # 2차 시도: GPT-4o-mini (Claude 실패 시 폴백)
    if result is None:
        result = await _call_openai(prompt)

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


async def _call_claude(prompt: str) -> str | None:
    """
    Anthropic Claude Haiku API를 호출한다.

    Returns:
        LLM 응답 텍스트, 또는 실패 시 None
    """
    if not settings.ANTHROPIC_API_KEY:
        return None

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        print(f"[LLM] Claude API 호출 실패: {e}")
        return None


async def _call_openai(prompt: str) -> str | None:
    """
    OpenAI GPT-4o-mini API를 호출한다 (Claude 실패 시 폴백).

    Returns:
        LLM 응답 텍스트, 또는 실패 시 None
    """
    if not settings.OPENAI_API_KEY:
        return None

    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] OpenAI API 호출 실패: {e}")
        return None


def _parse_llm_response(response_text: str, journalist: str | None) -> dict:
    """
    LLM 응답 JSON을 파싱하고 신뢰도 점수를 가중합산한다.

    신뢰도 점수 공식:
      Score = (tone_neutrality × 0.30) + (info_density × 0.25)
            + (has_quotes × 0.25) + (journalist_named × 0.20)

    Args:
        response_text: LLM이 반환한 JSON 문자열
        journalist: 기자명 (신뢰도 점수의 기자_실명 항목에 반영)

    Returns:
        {"summary": str, "category": str, "credibility": float}

    Raises:
        ValueError: JSON 파싱 실패 시
    """
    # JSON 블록 추출 (```json ... ``` 감싸진 경우 대비)
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        raise ValueError(f"JSON을 찾을 수 없음: {response_text[:200]}")

    data = json.loads(json_match.group())

    # ── 요약 추출 ──
    summary = data.get("summary", "요약 없음")

    # ── 카테고리 검증 (유효하지 않으면 기본값 '사회') ──
    category = data.get("category", "사회")
    if category not in VALID_CATEGORIES:
        category = "사회"

    # ── 신뢰도 점수 가중합산 ──
    cred = data.get("credibility", {})

    # 각 항목을 0~100 범위로 클램핑
    tone_neutrality = _clamp(cred.get("tone_neutrality", 50))
    info_density = _clamp(cred.get("info_density", 50))
    has_quotes = _clamp(cred.get("has_quotes", 50))

    # 기자 실명: LLM 판단값과 실제 기자명 존재 여부를 교차 검증
    # 실제 기자명이 있으면 100점, 없으면 LLM 판단값 사용
    if journalist and journalist.strip():
        journalist_named = 100
    else:
        journalist_named = _clamp(cred.get("journalist_named", 0))

    # ── 가중합산: 문체 중립성(30%) + 정보 밀도(25%) + 인용구(25%) + 기자 실명(20%) ──
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
        return 50.0  # 파싱 불가 시 중간값
