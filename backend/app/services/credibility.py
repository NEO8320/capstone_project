"""
뉴스 신뢰도 점수 계산기 (결정론적 규칙 기반)
================================================

LLM(Llama 3)이 신뢰도 서브스코어(RB-01~RB-04)를 안정적으로 산출하지 못해
대부분의 기사가 50점 근처로 수렴하는 문제가 있었다.
(원인: LLM이 JSON 스키마를 일부 누락 → `cred.get(..., 50)` 기본값 + `_clamp` fallback 50
         → 가중합이 45~55점에 집중 → 사용자에게는 "전부 50점"처럼 보임)

이 모듈은 LLM 없이도 **같은 입력 → 항상 같은 출력** 을 보장하는 규칙 기반 계산기다.
모든 산출 근거를 코드로 설명할 수 있고, 재현성·속도·신뢰성이 모두 확보된다.

────────────────────────────────────────────────────────────────
지표 정의 (가중치 합계 1.00)
────────────────────────────────────────────────────────────────
 RB-01 (30%)  문체 중립성   : 감정·선정·과장 어휘의 출현 빈도
 RB-02 (25%)  정보 밀도     : 숫자·날짜·단위·고유명사 등 객관 정보량
 RB-03 (25%)  인용구 존재   : 직접 인용("…"), 간접 인용("…라고 말했다")
 RB-04 (20%)  기자 실명     : 본문 끝 바이라인 존재 여부

 Final = RB01×0.30 + RB02×0.25 + RB03×0.25 + RB04×0.20
────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re


# ============================================================
# RB-01: 문체 중립성 — 감정·선정적 어휘 사전
# ============================================================
# 이 어휘들이 등장할수록 감점된다. 한국 기사에서 실제로 자주 나타나는
# '선정적/감정적/과장형' 표현을 수집했다. (필요 시 확장 가능)
SENSATIONAL_WORDS: tuple[str, ...] = (
    # 충격/경악 계열
    "충격", "충격적", "경악", "발칵", "소름", "헉", "헐",
    # 극단 단정 계열
    "최악", "최고", "역대급", "사상 최", "초유", "전무후무",
    "완전", "엄청", "대박", "미친", "미쳤", "무려",
    # 분노/감정 계열
    "분노", "격노", "울분", "분통", "참담", "통탄",
    # 위기/참사 계열
    "대란", "참사", "몰락", "붕괴", "재앙", "파국", "위기",
    # 단정/자극 계열
    "폭로", "단독", "속보", "긴급", "전격", "돌연", "의혹",
    "논란", "파문", "비상", "심각", "경고",
    # 극단 수치 표현
    "급락", "폭락", "폭등", "급등", "곤두박질",
    # 비하/과장 계열
    "망신", "망했", "처참", "처절",
)


def calculate_rb01_tone(title: str, body: str) -> float:
    """
    RB-01 문체 중립성: 감정·선정적 어휘가 적을수록 고득점.

    계산 방식:
      * 제목 + 본문에서 SENSATIONAL_WORDS 단어 출현 횟수(distinct) 계산
      * 제목에 있는 어휘는 2배 가중 (제목이 자극적일수록 타격 큼)

    점수 테이블:
      0건       → 100 (완전 중립)
      1~2건    →  85
      3~5건    →  65
      6~10건   →  45
      11건 이상 →  25

    Args:
        title: 기사 제목
        body: 기사 본문

    Returns:
        0~100 실수
    """
    title_safe = title or ""
    body_safe = body or ""

    # 제목 가중치 2x
    title_hits = sum(2 for w in SENSATIONAL_WORDS if w in title_safe)
    body_hits = sum(1 for w in SENSATIONAL_WORDS if w in body_safe)
    total = title_hits + body_hits

    if total == 0:
        return 100.0
    elif total <= 2:
        return 85.0
    elif total <= 5:
        return 65.0
    elif total <= 10:
        return 45.0
    else:
        return 25.0


# ============================================================
# RB-02: 정보 밀도 — 숫자/날짜/단위의 본문 대비 출현 빈도
# ============================================================
_RE_NUMBER = re.compile(r"\d+(?:[,.]\d+)*")
_RE_DATE = re.compile(
    r"\d{4}년|\d{1,2}월|\d{1,2}일|\d{1,2}시|\d{1,2}분|"
    r"오전|오후|새벽|밤|오늘|어제|내일|지난해|올해|금년|내년"
)
_RE_UNIT = re.compile(
    r"%|원|달러|엔|유로|위안|명|건|개|회|차|점|표|차례|"
    r"시간|분간|년간|개월|km|ｋｍ|m|cm|mm|kg|g|t|톤|㎡|㎏|L|ml"
)


def calculate_rb02_density(body: str) -> float:
    """
    RB-02 정보 밀도: 구체적 수치·날짜·단위 정보의 밀도.

    계산 방식:
      * 본문에서 숫자·날짜·단위 매칭을 모두 세고
      * 본문 길이(문자수)로 나눠 1000자당 밀도를 구한다
      * 밀도 5 이상이면 100, 선형 스케일

    짧은 본문(<100자)은 평가가 불안정하므로 30점으로 고정.

    Args:
        body: 기사 본문

    Returns:
        20~100 실수
    """
    if not body or len(body) < 100:
        return 30.0

    entities = (
        len(_RE_NUMBER.findall(body))
        + len(_RE_DATE.findall(body))
        + len(_RE_UNIT.findall(body))
    )
    density_per_1000 = (entities / len(body)) * 1000

    # 밀도 5 이상 → 100, 0 → 20 (완전 서술문 기사도 아주 낮진 않게)
    score = 20.0 + density_per_1000 * 16.0
    return max(20.0, min(100.0, score))


# ============================================================
# RB-03: 인용구 존재 — 직접/간접 인용 개수
# ============================================================
# 직접 인용: "..." '...' 「...」 『...』  (내용 5자 이상)
_RE_DIRECT_QUOTE = re.compile(r'"[^"]{5,}"|“[^”]{5,}”|「[^」]{5,}」|『[^』]{5,}』')
# 간접 인용: '...라고 (말했|밝혔|전했|강조했|설명했|덧붙였|지적했|주장했)'
_RE_INDIRECT_QUOTE = re.compile(
    r"라고\s*(?:말했|밝혔|전했|강조했|설명했|덧붙였|지적했|주장했|관측했|분석했|진단했)"
)


def calculate_rb03_quotes(body: str) -> float:
    """
    RB-03 인용구 존재: 직접 인용 + 간접 인용 개수 기반.

    점수 테이블:
      0개    →   0
      1개    →  55
      2개    →  75
      3개    →  90
      4개 이상→ 100

    Args:
        body: 기사 본문

    Returns:
        0~100 실수
    """
    if not body:
        return 0.0

    direct = len(_RE_DIRECT_QUOTE.findall(body))
    indirect = len(_RE_INDIRECT_QUOTE.findall(body))
    total = direct + indirect

    if total == 0:
        return 0.0
    elif total == 1:
        return 55.0
    elif total == 2:
        return 75.0
    elif total == 3:
        return 90.0
    else:
        return 100.0


# ============================================================
# RB-04: 기자 실명
# ============================================================
def calculate_rb04_journalist(journalist: str | None) -> float:
    """
    RB-04 기자 실명: 바이라인이 존재하면 100, 없으면 0.
    pipeline._extract_journalist()의 결과를 그대로 사용.
    """
    if journalist and journalist.strip():
        return 100.0
    return 0.0


# ============================================================
# 통합 계산 함수 (LLM 파이프라인에서 호출)
# ============================================================
def calculate_credibility(
    title: str,
    body: str,
    journalist: str | None = None,
) -> dict:
    """
    4개 서브스코어 계산 + 가중합 최종 신뢰도 반환.

    가중치:
      Final = RB01 × 0.30 + RB02 × 0.25 + RB03 × 0.25 + RB04 × 0.20

    Args:
        title:       기사 제목
        body:        기사 본문 (스크래핑된 텍스트 또는 description 폴백)
        journalist:  기자 실명 (없으면 None)

    Returns:
        {
            "credibility":     float,  # 0~100 최종 점수 (가중합)
            "rb01_tone":       float,  # 0~100 문체 중립성
            "rb02_density":    float,  # 20~100 정보 밀도
            "rb03_quotes":     float,  # 0~100 인용구
            "rb04_journalist": float,  # 0 or 100 기자 실명
        }
    """
    rb01 = calculate_rb01_tone(title, body)
    rb02 = calculate_rb02_density(body)
    rb03 = calculate_rb03_quotes(body)
    rb04 = calculate_rb04_journalist(journalist)

    final = rb01 * 0.30 + rb02 * 0.25 + rb03 * 0.25 + rb04 * 0.20

    return {
        "credibility": round(final, 2),
        "rb01_tone": round(rb01, 2),
        "rb02_density": round(rb02, 2),
        "rb03_quotes": round(rb03, 2),
        "rb04_journalist": round(rb04, 2),
    }
