"""
LLM 처리 모듈 — CT-01(요약) / CT-02(분류) 분리 아키텍처
=========================================================

CT-01 (LlamaService): 기사 본문 → 3줄 요약 (5W1H 한국어)
  - 엔진: 로컬 Ollama (Llama 3)
  - 프롬프트: 5W1H 핵심 사실 위주, 한국어 출력
  - ★ 신뢰도 평가는 LLM이 아닌 규칙 기반 credibility.py 에서 수행

CT-02 (GPTService): 기사 제목 + 3줄 요약 → 카테고리 분류
  - 엔진: OpenAI GPT API (gpt-4o-mini)
  - 입력: "기사 제목 [SEP] 3줄 요약" (512 토큰 제한)
  - 출력: 8개 카테고리 중 하나

신뢰도 평가 ID 체계 (RB-01~RB-05):  ← credibility.py 참조
  RB-01: 문체 중립성 (30%) — 감정·선정적 어휘 출현 빈도 (규칙 기반)
  RB-02: 정보 밀도   (25%) — 숫자·날짜·단위 밀도 (정규식)
  RB-03: 인용구      (25%) — 직접/간접 인용 개수 (정규식)
  RB-04: 기자 실명   (20%) — 바이라인 존재 여부
  RB-05: 뱃지 등급 — 90+:높음 / 70~89:보통 / 69이하:낮음 (UI 단계)

  ※ 이전에는 LLM에게 RB-01~04 점수를 직접 생성시켰으나, Llama 3 8B가
     JSON 스키마의 일부 서브필드를 빈번히 누락해 `_clamp` fallback(50)으로
     수렴하는 버그가 있었다. 현재는 credibility.py 에서 결정론적으로 계산.

설정값: config.yaml (NFR-E03)에서 모델명·엔드포인트를 읽어온다.
서킷 브레이커: 5회 연속 실패 시 30초간 호출 차단.
"""

import asyncio
import re

import openai

from app.core.config import settings
from app.core.yaml_config import get_yaml_config
from app.services.credibility import calculate_credibility
from app.services.resilience import CircuitBreaker

# ── LLM API 전용 서킷 브레이커 ──
llm_circuit = CircuitBreaker(name="llm_api", failure_threshold=5, recovery_timeout=30.0)

# ── 유효 카테고리 목록 (8종) ──
VALID_CATEGORIES = [
    "정치", "경제", "사회", "IT·과학", "생활·문화", "세계", "연예", "스포츠",
]


# ============================================================
# CT-01 프롬프트: 3줄 요약 전용 (5W1H 핵심 사실 위주)
# ============================================================
# ※ 이전 버전은 신뢰도 서브스코어(RB-01~04)까지 LLM에게 동시 생성시켰지만,
#    Llama 3 8B가 JSON 스키마의 숫자 서브필드를 빈번히 누락하거나 placeholder
#    문자열을 반환해 _clamp fallback(50)으로 수렴 → 전 기사가 신뢰도 50대로
#    몰리는 버그가 있었다. 이제 LLM은 요약만 담당하고, 신뢰도는 credibility.py
#    가 결정론적으로 계산한다.
CT01_SUMMARY_PROMPT = """다음 뉴스 기사의 핵심을 3줄로 요약해주세요.

[기사 제목]
{title}

[기사 본문]
{body}

**반드시 한국어**로 작성하고, 5W1H(누가·언제·어디서·무엇을·왜·어떻게)
중에서 기사에 드러난 핵심 사실을 중심으로 3줄을 작성하세요.
각 줄은 한 문장씩, 줄바꿈(\\n)으로 구분합니다.
다른 설명·머리말·마크다운 없이 요약 텍스트만 출력하세요."""


# ============================================================
# CT-02 프롬프트: 카테고리 분류 (8개 카테고리)
# ============================================================
CT02_CLASSIFY_PROMPT = """다음 뉴스 기사의 카테고리를 분류하세요.

입력:
{input_text}

위 기사를 아래 8개 카테고리 중 **정확히 하나**로 분류하세요:
정치 | 경제 | 사회 | IT·과학 | 생활·문화 | 세계 | 연예 | 스포츠

카테고리 이름만 출력하세요 (다른 텍스트 없이)."""


# ============================================================
# CT-01: LlamaService — 3줄 요약 + 신뢰도 평가
# ============================================================
class LlamaService:
    """
    CT-01: Llama 로컬 모델을 사용한 3줄 요약 및 신뢰도 평가.
    config.yaml → llm.summarizer 섹션에서 모델/엔드포인트를 읽는다.
    """

    @staticmethod
    async def summarize(
        title: str, body: str, journalist: str | None = None,
    ) -> str | None:
        """
        기사 본문 → 3줄 요약 (텍스트만 반환).

        신뢰도 서브스코어(RB-01~04)는 여기서 계산하지 않고,
        상위 호출자(process_article_with_llm)가 credibility.calculate_credibility()
        로 별도 계산한다.

        Args:
            title: 기사 제목
            body: 기사 본문
            journalist: 기자 실명 (현재는 미사용. 인터페이스 호환 유지)

        Returns:
            3줄 요약 문자열 또는 실패 시 None
        """
        try:
            cfg = get_yaml_config().get("llm", {}).get("summarizer", {})
            model = cfg.get("model", settings.LLM_PRIMARY_MODEL)
            base_url = cfg.get("base_url", settings.LLM_PRIMARY_BASE_URL)
            max_tokens = cfg.get("max_tokens", 1024)
            temperature = cfg.get("temperature", 0.3)

            truncated_body = body[:3000] if len(body) > 3000 else body
            prompt = CT01_SUMMARY_PROMPT.format(title=title, body=truncated_body)

            client = openai.AsyncOpenAI(
                base_url=base_url,
                api_key="ollama",  # 로컬 서버는 키 불필요
            )
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                print("[CT-01] Llama 응답이 비어 있음")
                return None

            # 간혹 Llama가 '요약:', '## Summary' 같은 머리말을 붙이는 경우 제거
            text = re.sub(r"^\s*(요약|Summary|##.*?)\s*[:：]\s*", "", text)
            print(f"[CT-01] Llama 요약 성공 ({model})")
            return text
        except Exception as e:
            print(f"[CT-01] Llama 요약 실패: {e}")
            return None


# ============================================================
# CT-02: GPTService — 카테고리 분류
# ============================================================
class GPTService:
    """
    CT-02: OpenAI GPT API를 사용한 카테고리 분류.
    config.yaml → llm.classifier 섹션에서 모델/엔드포인트를 읽는다.
    입력: "기사 제목 [SEP] 3줄 요약" (512 토큰 제한)
    출력: 8개 카테고리 중 하나
    """

    @staticmethod
    async def classify(title: str, summary: str) -> str | None:
        """
        기사 제목 + 3줄 요약 → 카테고리 분류.
        최대 3회 재시도, 지수 백오프 적용. (Task 3)

        Returns:
            카테고리 문자열 또는 실패 시 None
        """
        MAX_RETRIES = 3

        cfg = get_yaml_config().get("llm", {}).get("classifier", {})
        model = cfg.get("model", settings.LLM_FALLBACK_OPENAI_MODEL)
        base_url = cfg.get("base_url", settings.LLM_FALLBACK_OPENAI_BASE_URL)
        max_tokens = cfg.get("max_tokens", 512)
        temperature = cfg.get("temperature", 0.1)

        api_key = settings.OPENAI_API_KEY
        if not api_key:
            print("[CT-02] OPENAI_API_KEY 미설정 — GPT 분류 건너뜀")
            return None

        # 입력 포맷: "기사 제목 [SEP] 3줄 요약"
        input_text = f"{title} [SEP] {summary}"
        prompt = CT02_CLASSIFY_PROMPT.format(input_text=input_text)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
                response = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                result_text = response.choices[0].message.content.strip()
                category = _parse_category(result_text)
                if category:
                    print(f"[CT-02] GPT 분류 성공 ({model}): {category}")
                    return category

                # 파싱 실패 → 재시도
                if attempt < MAX_RETRIES:
                    print(
                        f"[CT-02] 카테고리 파싱 실패 "
                        f"(시도 {attempt}/{MAX_RETRIES}): '{result_text}'"
                    )
                    await asyncio.sleep(0.5 * attempt)
                    continue
                print(f"[CT-02] 카테고리 파싱 최종 실패: '{result_text}'")
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(
                        f"[CT-02] GPT API 오류 "
                        f"(시도 {attempt}/{MAX_RETRIES}): {e}"
                    )
                    await asyncio.sleep(1.0 * attempt)
                    continue
                print(f"[CT-02] GPT 분류 최종 실패: {e}")

        return None


# ============================================================
# 통합 처리 함수 (파이프라인 호출용)
# ============================================================
async def process_article_with_llm(
    title: str,
    body: str,
    journalist: str | None = None,
) -> dict | None:
    """
    CT-01 → CT-02 순차 호출 + 규칙 기반 신뢰도 계산.

    1단계 (CT-01): Llama로 3줄 요약
    2단계 (CT-02): GPT로 카테고리 분류 (CT-01 요약을 입력)
    3단계 (규칙)   : credibility.calculate_credibility() 로 RB-01~04 산출

    ★ 과거 아키텍처와의 차이:
      - 이전: Llama가 JSON 스키마로 summary + credibility를 동시 반환
        → Llama 8B가 숫자 서브필드를 자주 누락/placeholder화
        → _clamp fallback 50 + cred.get(..., 50) 기본값 조합으로
          대부분의 기사가 신뢰도 45~55점으로 몰림
      - 현재: LLM은 요약만 담당, 신뢰도는 결정론적 규칙 계산
        → 같은 기사 → 항상 같은 점수, 기사별 편차가 실제로 드러남

    Args:
        title: 기사 제목
        body: 기사 본문
        journalist: 기자명 (없으면 None)

    Returns:
        {"summary": str, "category": str, "credibility": float,
         "rb01_tone", "rb02_density", "rb03_quotes", "rb04_journalist"}
        또는 요약 실패 시 None (상위에서 description 폴백)
    """
    if not llm_circuit.can_call():
        return None

    # ── CT-01: Llama 요약 (문자열 반환) ──
    summary_text = await LlamaService.summarize(title, body, journalist)

    if summary_text is None:
        await llm_circuit.record_failure()
        return None

    # ── CT-02: GPT 분류 (CT-01의 요약을 입력으로) ──
    category = await GPTService.classify(title, summary_text)

    if category is None:
        # GPT 실패 시 기본 카테고리 (파이프라인 중단 방지)
        category = "사회"

    await llm_circuit.record_success()

    # ── 규칙 기반 신뢰도 계산 (결정론적, LLM 의존 없음) ──
    cred = calculate_credibility(title=title, body=body, journalist=journalist)

    return {
        "summary": summary_text,
        "category": category,
        "credibility": cred["credibility"],
        "rb01_tone": cred["rb01_tone"],
        "rb02_density": cred["rb02_density"],
        "rb03_quotes": cred["rb03_quotes"],
        "rb04_journalist": cred["rb04_journalist"],
    }


# ============================================================
# 파싱 헬퍼
# ============================================================
# GPT 출력 변형 → 정규 카테고리 매핑 (Output parsing error 방지, Task 3)
_CATEGORY_FUZZY_MAP = {
    "IT": "IT·과학", "it": "IT·과학", "과학": "IT·과학", "기술": "IT·과학",
    "IT/과학": "IT·과학", "IT과학": "IT·과학",
    "생활": "생활·문화", "문화": "생활·문화", "생활/문화": "생활·문화",
    "국제": "세계", "외교": "세계", "글로벌": "세계",
}


def _parse_category(text: str) -> str | None:
    """CT-02 응답에서 유효한 카테고리 문자열을 파싱한다. 퍼지 매칭 포함."""
    text = text.strip().strip('"').strip("'")
    # 1차: 정확 매칭
    for cat in VALID_CATEGORIES:
        if cat in text:
            return cat
    # 2차: 퍼지 매칭 (GPT가 유사 표현을 반환한 경우)
    for keyword, cat in _CATEGORY_FUZZY_MAP.items():
        if keyword in text:
            return cat
    return None
