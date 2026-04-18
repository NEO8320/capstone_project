"""
뉴스 신뢰도 점수 계산기 (결정론적 규칙 기반 — v2 연속 스케일)
==================================================================

■ 배경 (이 모듈이 존재하는 이유)
----------------------------------------------------------------
Llama 3 8B 가 신뢰도 JSON 서브필드(RB-01~04)를 자주 누락·placeholder 처리 하여
모든 기사 점수가 45~55점에 몰리는 "50점 수렴" 버그가 있었다.
이를 해결하기 위해 **LLM 의존 없이 동일 입력 → 동일 출력** 을 보장하는
규칙 기반 계산기로 전환했다.

■ v1 → v2 의 변경 이유 (2026-04-19)
----------------------------------------------------------------
v1 의 계단식(step-function) 테이블은 재현성은 확보했지만
여전히 점수가 특정 구간(평균 72, 50~59 구간 20%, 85+ 거의 없음)으로
쏠리는 현상이 있었다. 원인 3가지:

  1. RB-01 이 5단계(100/85/65/45/25) 계단 → 값이 이산점에 몰림
  2. RB-02 가 짧은 본문(<100자)에 무조건 30점 부여 → 저점 플래토
  3. RB-04 가 이진(0 / 100) → 언론사·기자 둘 다 없을 땐 0 으로 급락,
     언론사 OR 기자 OR 둘 다 라는 "중간 수준"을 표현하지 못함

v2 는 아래 원칙으로 재설계했다:

  • 연속(continuous) 스케일 — 가능한 한 선형 사상, 계단 금지
  • 중간 티어(mid-tier) 확보 — 모든 서브스코어의 바닥값을 20 이상으로 올려
    "정보 부족" 이 자동으로 50점을 만드는 수렴 현상 억제
  • 언론사 정보 반영 — RB-04 가 journalist / press 둘을 조합해 3티어

────────────────────────────────────────────────────────────────
지표 정의 (가중치 합계 1.00, 변경 없음)
────────────────────────────────────────────────────────────────
 RB-01 (30%)  문체 중립성   : 감정·선정·과장 어휘의 출현 빈도
 RB-02 (25%)  정보 밀도     : 숫자·날짜·단위·고유명사 등 객관 정보량
 RB-03 (25%)  인용구 존재   : 직접 인용("…"), 간접 인용("…라고 말했다")
 RB-04 (20%)  출처 명시     : 기자 실명 + 언론사 매칭 (3-tier)

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
    RB-01 문체 중립성 — **연속 선형 감점**.

    설계:
      * 제목 가중치 2x (자극적 헤드라인에 더 큰 타격)
      * 연속 공식: score = max(25, 100 - total_hits * 7)
         - 0회 → 100  (완전 중립)
         - 1회 →  93
         - 2회 →  86
         - 5회 →  65
         - 8회 →  44
         - 11회→  23 → 하한 25 로 클램프
      * 하한 25 를 두는 이유:
         - 아주 자극적인 기사도 사실 전달이 있을 수 있음
         - 0점에 몰리면 평균 신뢰도 분포의 왼쪽 꼬리가 얇아져 구분력 상실

    Args:
        title: 기사 제목
        body: 기사 본문

    Returns:
        25~100 실수
    """
    title_safe = title or ""
    body_safe = body or ""

    # 제목 가중치 2x
    title_hits = sum(2 for w in SENSATIONAL_WORDS if w in title_safe)
    body_hits = sum(1 for w in SENSATIONAL_WORDS if w in body_safe)
    total = title_hits + body_hits

    score = 100.0 - total * 7.0
    return max(25.0, min(100.0, score))


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
    RB-02 정보 밀도 — **연속 선형**, 짧은 본문에도 합리적 기본점.

    설계:
      * 본문이 비었거나 극히 짧은(<80자) 경우:
          설명 폴백(description)만 들어온 케이스 — 정보 부족이지 거짓은 아님
          → 55 점 (v1 의 30 은 과도한 감점, 50 수렴의 주요 원인이었음)
      * 본문이 충분한 경우:
          entities = 숫자 + 날짜 + 단위 매칭 개수
          density = (entities / len(body)) * 1000   (1000자당 밀도)
          score   = 35 + density * 13               (밀도 5 → 100)
          → 밀도 0 도 35 점 (서술 위주 기사 보호)
          → 밀도 5 이상이면 100 (수치/날짜 촘촘)

    Args:
        body: 기사 본문

    Returns:
        35~100 실수 (짧은 본문 폴백 시 55)
    """
    if not body:
        return 55.0
    if len(body) < 80:
        return 55.0

    entities = (
        len(_RE_NUMBER.findall(body))
        + len(_RE_DATE.findall(body))
        + len(_RE_UNIT.findall(body))
    )
    density_per_1000 = (entities / len(body)) * 1000

    # 35 (서술형 기사 바닥) ~ 100 (수치 밀집)
    score = 35.0 + density_per_1000 * 13.0
    return max(35.0, min(100.0, score))


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
    RB-03 인용구 존재 — **연속**, 0건도 최소 30 보장.

    설계:
      * 0건 → 30  (v1 은 0점이었음 → 경제 지표/단신·분석 기사가 과도하게 감점됨)
      * 1건 → 60
      * 2건 → 78
      * 3건 → 90
      * 4건 → 96
      * 5건 이상 → 100
      * 위 구간 사이는 선형 보간 → 연속성 확보

    왜 0건도 30점:
      - "삼성전자 2024년 영업이익 8조, 전년比 15% 증가" 같은 기사는
        인용 없이도 충분히 신뢰할 수 있다. v1 의 0점 부여는 과도했다.

    Args:
        body: 기사 본문

    Returns:
        30~100 실수
    """
    if not body:
        return 30.0

    direct = len(_RE_DIRECT_QUOTE.findall(body))
    indirect = len(_RE_INDIRECT_QUOTE.findall(body))
    total = direct + indirect

    # 앵커 포인트 테이블 — 이후 선형 보간
    # (인용 건수, 점수)
    anchors = [(0, 30.0), (1, 60.0), (2, 78.0), (3, 90.0), (4, 96.0), (5, 100.0)]

    if total >= 5:
        return 100.0

    # 정수 값이므로 앵커 직접 매칭
    for n, score in anchors:
        if total == n:
            return score

    return 30.0  # defensive (도달 불가)


# ============================================================
# RB-04: 출처 명시 — 기자 실명 + 언론사 (3-tier)
# ============================================================
def calculate_rb04_journalist(
    journalist: str | None,
    press: str | None = None,
) -> float:
    """
    RB-04 출처 명시 — **3-tier 연속화**.

    v1 은 기자 실명 유무만 보고 0 또는 100 이진값이었다.
    → 언론사는 매핑됐으나 기자명 미추출인 기사가 0점 처리되는 문제.

    v2 3-tier:
      * 기자 실명 + 언론사 매칭  → 100  (완전 출처 확보)
      * 기자 실명만 또는 언론사만 → 60   (부분 출처)
      * 둘 다 없음                → 25   (익명 게시 수준)

    press 인자는 pipeline._extract_press() 의 반환을 그대로 전달한다.
    매핑 실패 시 도메인 문자열("www.example.com")이 들어올 수 있는데,
    '.' 이 포함되면 매핑 실패로 간주하여 '언론사 없음' 으로 처리한다.

    Args:
        journalist: 기자명 (없으면 None)
        press:      언론사명 (pipeline._extract_press 의 반환)

    Returns:
        25 / 60 / 100 중 하나
    """
    has_journalist = bool(journalist and journalist.strip())

    # press 가 ".com", ".co.kr" 같은 도메인 문자열이면 매핑 실패
    has_press = bool(
        press and press.strip() and "." not in press and press != "Unknown"
    )

    if has_journalist and has_press:
        return 100.0
    if has_journalist or has_press:
        return 60.0
    return 25.0


# ============================================================
# 통합 계산 함수 (LLM 파이프라인에서 호출)
# ============================================================
def calculate_credibility(
    title: str,
    body: str,
    journalist: str | None = None,
    press: str | None = None,
) -> dict:
    """
    4개 서브스코어 계산 + 가중합 최종 신뢰도 반환.

    가중치:
      Final = RB01 × 0.30 + RB02 × 0.25 + RB03 × 0.25 + RB04 × 0.20

    Args:
        title:       기사 제목
        body:        기사 본문 (스크래핑된 텍스트 또는 description 폴백)
        journalist:  기자 실명 (없으면 None)
        press:       언론사명 (pipeline._extract_press 결과, 선택)

    Returns:
        {
            "credibility":     float,  # 0~100 최종 점수 (가중합)
            "rb01_tone":       float,  # 25~100 문체 중립성
            "rb02_density":    float,  # 35~100 (짧은 본문 55) 정보 밀도
            "rb03_quotes":     float,  # 30~100 인용구
            "rb04_journalist": float,  # 25 / 60 / 100 출처 3-tier
        }

    ■ v2 재설계 후 예상 분포 (v1 대비):
        v1 : 평균 72, 50~59 구간 20%, 85+ 거의 없음
        v2 : 평균 78~82, 50~59 구간 <10%, 85+ 15~25%
        → 프론트 배지(90+ green, 70-89 yellow, <70 red) 구분력 회복
    """
    rb01 = calculate_rb01_tone(title, body)
    rb02 = calculate_rb02_density(body)
    rb03 = calculate_rb03_quotes(body)
    rb04 = calculate_rb04_journalist(journalist, press)

    final = rb01 * 0.30 + rb02 * 0.25 + rb03 * 0.25 + rb04 * 0.20

    return {
        "credibility": round(final, 2),
        "rb01_tone": round(rb01, 2),
        "rb02_density": round(rb02, 2),
        "rb03_quotes": round(rb03, 2),
        "rb04_journalist": round(rb04, 2),
    }
