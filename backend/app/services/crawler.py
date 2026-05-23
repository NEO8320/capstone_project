"""
네이버 뉴스 수집 모듈 (Crawler)
================================

네이버 뉴스 검색 API를 통해 6개 카테고리별 기사를 비동기로 수집하고,
BeautifulSoup으로 본문을 정제하는 역할을 담당한다.

파이프라인 흐름:
  1. 네이버 뉴스 검색 API 호출 (카테고리별 키워드 검색)
  2. 각 기사 URL에서 본문 HTML을 가져와 BeautifulSoup으로 정제
  3. 정제된 기사 데이터를 딕셔너리 리스트로 반환

서킷 브레이커가 적용되어 API 5회 연속 실패 시 30초간 호출을 차단한다.
"""

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.resilience import CircuitBreaker

# ── 본문 추출 라이브러리 (선택적 의존성) ──
# trafilatura 는 콘텐츠 밀도 기반 자동 본문 추출. BS4 셀렉터 패턴 매칭으로
# 잡지 못하는 외부 언론사 사이트의 잡음(네비, UI, 태그, 관련기사 카루셀,
# 저작권 고지 등)을 깨끗하게 제거한다. 미설치 시 BS4 폴백만 사용.
try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False
    print("[Crawler] trafilatura 미설치 - BS4 폴백만 사용. pip install trafilatura 권장")

# ── 네이버 뉴스 API 전용 서킷 브레이커 ──
naver_circuit = CircuitBreaker(name="naver_news_api", failure_threshold=5, recovery_timeout=30.0)

# ── 카테고리별 검색 키워드 매핑 ──
# 네이버 뉴스 검색 API는 카테고리 필터가 없으므로 대표 키워드로 검색한다.
#
# ★ 중요 (2026-04-17 수정):
#   네이버 뉴스 검색 API는 `query` 파라미터의 공백 구분 단어를 "모두 포함"(AND)으로
#   처리한다. 과거 "연예 아이돌 드라마"처럼 3단어 AND 쿼리를 사용해 세계/연예/스포츠
#   카테고리 수집량이 극도로 적었다(DB에 각 1건). 키워드를 1~2개 핵심어로 축소하여
#   검색 결과 집합을 충분히 확보한다.
#
# ★ 키는 반드시 config.yaml categories와 동일한 가운뎃점(·) 형식으로 유지해야 한다.
#   - 과거에 "IT/과학", "생활/문화" (슬래시) 형식을 쓰다가 DB에 이중 카테고리가 저장되는
#     치명적 버그가 있었음. 프론트엔드 필터/탭이 매칭 실패하는 원인이 되었다.
#   - 이제 8개 카테고리 전부 커버 (연예·스포츠 포함).
CATEGORY_KEYWORDS: dict[str, str] = {
    "정치": "정치",
    "경제": "경제",
    "사회": "사회 사건",       # '사회' 단독은 너무 범용 → '사건' 추가
    "생활·문화": "문화",
    "IT·과학": "IT",
    # ★ 2026-04-19 수정 (세계/연예 버킷 비어있는 문제):
    #   '국제' 는 '국제교류/국제학교/국제회의' 같은 비-세계뉴스도 대량 유입되고,
    #   '연예' 는 연예인 스캔들 기사 외에 '연예인의 골프경기' 같은 스포츠 기사도
    #   섞여 GPT 가 재분류 → 세계/연예 카테고리가 비어버리는 현상이 있었다.
    #   → 더 구체적인 키워드로 교체해 카테고리-본문 불일치를 줄인다.
    "세계": "해외",            # '국제' → '해외' (명확한 해외뉴스만 매칭)
    "연예": "연예인",          # '연예' → '연예인' (실제 연예 기사만 매칭)
    "스포츠": "스포츠",
}


async def fetch_naver_news(
    category: str,
    max_articles: int = 20,
) -> list[dict]:
    """
    네이버 뉴스 검색 API를 호출하여 기사 메타데이터를 수집한다.

    Args:
        category: 뉴스 카테고리 (CATEGORY_KEYWORDS 키 중 하나)
        max_articles: 수집할 최대 기사 수 (적응형 수집량 조절기가 결정)

    Returns:
        기사 메타데이터 딕셔너리 리스트:
        [{"title": str, "link": str, "description": str, "pub_date": datetime}, ...]

    Note:
        서킷 브레이커가 OPEN 상태이면 빈 리스트를 반환한다.
    """
    # 서킷 브레이커 확인 — OPEN이면 즉시 빈 리스트 반환
    if not naver_circuit.can_call():
        return []

    keyword = CATEGORY_KEYWORDS.get(category, category)
    articles = []

    # 네이버 API는 한 번에 최대 100건, start 파라미터로 페이징
    # display=100, start=1부터 시작
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 필요한 만큼 페이징하여 수집 (API 제한: start ≤ 1000)
            for start in range(1, max_articles + 1, 100):
                display = min(100, max_articles - len(articles))
                if display <= 0:
                    break

                response = await client.get(
                    "https://openapi.naver.com/v1/search/news.json",
                    params={
                        "query": keyword,
                        "display": display,
                        "start": start,
                        "sort": "date",  # 최신순 정렬
                    },
                    headers={
                        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
                        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
                    },
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("items", []):
                    # HTML 태그 제거 (네이버 API 응답에 <b> 태그 포함)
                    clean_title = _strip_html(item.get("title", ""))
                    clean_desc = _strip_html(item.get("description", ""))

                    # 발행 시간 파싱 (RFC 2822 형식)
                    pub_date = _parse_pub_date(item.get("pubDate", ""))

                    original_url = item.get("originallink") or item.get("link", "")
                    naver_url = item.get("link", "")
                    articles.append({
                        "title": clean_title,
                        "link": original_url,       # 표시용 (원본 언론사 귀속)
                        "naver_link": naver_url,    # 스크래핑 전용 (dic_area 보장)
                        "description": clean_desc,
                        "pub_date": pub_date,
                        "category": category,
                    })

            # API 호출 성공 기록
            await naver_circuit.record_success()

        except Exception as e:
            print(f"[Crawler] 네이버 뉴스 API 호출 실패 ({category}): {e}")
            await naver_circuit.record_failure()
            return []

    return articles[:max_articles]


# ── 잡음 클래스/ID 패턴 (BS4 폴백 단계용, 모듈 레벨 컴파일로 성능 확보) ──
# trafilatura 가 잡지 못한 경우 BS4 가 받는데, 이 패턴이 가능한 한 많은
# 잡음 영역을 미리 제거하여 추출 정확도를 끌어올린다.
#
# 확장 영역(2026-05 newsroad 사례 대응):
#   - navigation: 이전/다음 기사, 페이지 이동
#   - toolbar/utility: 복사, 공유, 글자크기, 인쇄
#   - scroll/UI control: 스크롤바, 맨위로, 위로
#   - tag/keyword: 해시태그, 키워드 영역
#   - byline: 기자명/이메일/소속
#   - related/carousel: 관련 기사 슬라이드, 추천 기사 목록
#   - footer/copyright: 저작권, 무단전재 고지
_NOISE_PATTERN = re.compile(
    # 댓글/추천/광고
    r"u_cmt|comment|댓글|reply"
    r"|related_article|news_ranking|related_news|newsflash_body|related[_-]?list"
    r"|ad_area|advertisement|banner|ad[_-]?wrap|google_?ads"
    r"|u_likeit|likeit|like[_-]?count|recommend"
    # 기자/언론사 정보
    r"|journalist_info|reporter_area|byline|author[_-]?(area|info|profile)"
    r"|press_subscribe|channel_subscribe|subscribe[_-]?btn|profile[_-]?wrap"
    # 저작권/공유
    r"|copyright|footer_area|footer[_-]?info"
    r"|sns_area|share_area|share[_-]?wrap|social[_-]?share"
    # 네비게이션
    r"|nav[_-]?(wrap|menu|bar)|navigation|prev[_-]?next|page[_-]?nav"
    r"|prev_?article|next_?article|article[_-]?nav"
    r"|breadcrumb|gnb|lnb"
    # UI 컨트롤 (글자크기, 인쇄, 복사, 스크롤)
    r"|font[_-]?(size|control|resize)|text[_-]?size"
    r"|btn[_-]?(copy|share|print|zoom)|copy[_-]?btn|print[_-]?btn"
    r"|scroll[_-]?(bar|indicator|top)|back[_-]?to[_-]?top|go[_-]?top"
    r"|toolbar|util[_-]?area|utility[_-]?menu"
    # 태그/키워드
    r"|tag[_-]?(area|list|wrap)|keyword[_-]?(area|list|wrap)|hashtag"
    # 관련 기사 카루셀
    r"|carousel|slider|swiper|thumb[_-]?list|article[_-]?(list|deck)"
    # 추천 / 인기
    r"|popular[_-]?news|top[_-]?news|hot[_-]?news|recommend[_-]?news"
    # 기타
    r"|skip[_-]?(nav|menu)|a11y|hidden",
    re.IGNORECASE,
)


def _trafilatura_extract(html: str) -> str | None:
    """
    trafilatura 로 본문 추출 (1순위 엔진).
    콘텐츠 밀도 분석으로 사이트별 셀렉터 없이도 본문만 추출한다.
    한국어 뉴스 사이트 (네이버 뉴스, 조선, 한겨레, newsroad 등) 모두 정상 동작.
    """
    if not _HAS_TRAFILATURA:
        return None
    try:
        text = trafilatura.extract(
            html,
            favor_precision=True,       # 정밀도 우선 (덜 가져오더라도 정확하게)
            include_comments=False,     # 댓글 영역 제외
            include_tables=False,       # 표 제외 (대부분 뉴스 본문엔 표 없음)
            include_images=False,
            include_links=False,        # 인라인 링크 텍스트는 유지하되 URL 은 제거
            no_fallback=False,          # trafilatura 자체 폴백 알고리즘 허용
            target_language="ko",
            deduplicate=True,           # 중복 단락 제거
        )
        return text or None
    except Exception as e:
        print(f"[Crawler] trafilatura 추출 실패: {e}")
        return None


def _bs4_extract(html: str) -> str | None:
    """
    BeautifulSoup4 로 본문 추출 (2순위, trafilatura 가 실패하거나 빈 결과를 줄 때).
    네이버 뉴스의 article#dic_area 같은 특정 구조에서는 trafilatura 보다 정확할 수 있다.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")

        # ── 불필요 태그 제거 ──
        for tag in soup.find_all([
            "script", "style", "iframe", "aside", "nav", "header", "footer",
            "noscript", "form", "button", "input",
        ]):
            tag.decompose()

        # ── 잡음 클래스/ID 제거 (확장된 패턴) ──
        noise_tags = [
            tag for tag in soup.find_all(True)
            if _NOISE_PATTERN.search(tag.get("id", "") or "")
            or _NOISE_PATTERN.search(" ".join(tag.get("class", []) or []))
        ]
        for tag in noise_tags:
            tag.decompose()

        # ── 본문 추출 우선순위 ──
        body_el = soup.find("article", {"id": "dic_area"})  # 네이버
        if not body_el:
            body_el = soup.find("div", {"id": "newsct_article"})  # 네이버 신구조
        if not body_el:
            body_el = soup.find("div", class_=re.compile(
                r"article[_-]?body|news[_-]?body|article[_-]?content|news[_-]?content"
                r"|story[_-]?body|article[_-]?txt|view[_-]?content",
                re.IGNORECASE,
            ))
        if not body_el:
            body_el = soup.find("article")
        if not body_el:
            return None  # 최후 수단(body 전체) 은 잡음 너무 많으므로 제외

        text = body_el.get_text(separator="\n", strip=True)
        return text or None

    except Exception as e:
        print(f"[Crawler] BS4 추출 실패: {e}")
        return None


# ── 한국어 뉴스 특화 후처리 패턴 ──
# trafilatura/BS4 가 못 잡은 잔여 잡음을 줄 단위로 제거.
_KO_NOISE_LINE_PATTERNS = [
    # 네비게이션
    re.compile(r"^\s*(이전\s*기사(보기)?|다음\s*기사(보기)?|기사목록|목록보기)\s*$"),
    re.compile(r"^\s*(맨\s*위로|위로|TOP|TOP으로)\s*$", re.IGNORECASE),
    # UI 버튼
    re.compile(r"^\s*(복사하기|바로가기|공유하기|인쇄|프린트|스크랩)\s*$"),
    re.compile(r"^\s*본문\s*글씨\s*(줄이기|키우기|크기)\s*$"),
    re.compile(r"^\s*(글자\s*크기|폰트\s*크기)\s*[가-힣\s]{0,5}$"),
    re.compile(r"^\s*스크롤\s*이동\s*상태바\s*$"),
    # 키워드/태그 영역
    re.compile(r"^\s*키워드\s*$"),
    re.compile(r"^\s*#[가-힣A-Za-z0-9_]+(\s+#[가-힣A-Za-z0-9_]+)*\s*$"),
    re.compile(r"^\s*태그\s*[:：]?\s*$"),
    # 저작권/언론사 고지 (단독 줄 + 줄 끝부분에 붙은 경우 둘 다 대응)
    re.compile(r"저작권자.*무단\s*전재.*재배포.*금지"),
    re.compile(r"^\s*©.*\s*All\s*[Rr]ights\s*[Rr]eserved", re.IGNORECASE),
    re.compile(r"Copyright\s*©.{0,80}All\s*rights\s*reserved", re.IGNORECASE),
    re.compile(r"^\s*무단\s*(전재|복제|배포)", re.IGNORECASE),
    # 권유/안내 푸터
    re.compile(r"^\s*함께\s*(봤던|본)\s*(기사|뉴스)"),
    re.compile(r"^\s*이\s*기사를?\s*본\s*이용자들"),
    # 댓글 UI
    re.compile(r"^\s*(내\s*댓글(\s*모음)?|닫기|댓글\s*\d+)\s*$"),
    # 구독/공유 안내
    re.compile(r"^\s*(구독|구독하기|채널\s*구독|페이스북|트위터|카카오톡)\s*$"),
    # 기자명 + 이메일 + "다른기사 보기" 패턴 (한 줄 또는 인접 줄)
    re.compile(r"^[가-힣]{2,4}\s+(기자|특파원|논설위원)\s*$"),
    re.compile(r"^\s*[\w.\-+]+@[\w.\-]+\.[a-zA-Z]{2,}\s*$"),  # 이메일만 있는 줄
    re.compile(r"^\s*(다른\s*기사\s*보기|기자의\s*다른\s*기사|이\s*기자의\s*기사)\s*$"),
    # 추천/관련 기사 라벨
    re.compile(r"^\s*(관련\s*기사|추천\s*기사|많이\s*본\s*기사|인기\s*기사|이전\s*기사)\s*$"),
    # 광고/협찬
    re.compile(r"^\s*(\[광고\]|\[협찬\]|AD|Advertisement)\s*$", re.IGNORECASE),
    # 사진/자료 출처 (단독 라인)
    re.compile(r"^\s*(사진|자료|영상)\s*=?\s*[\S\s]{0,30}제공\s*$"),
]


def _korean_postprocess(text: str) -> str:
    """
    한국어 뉴스 본문에서 추출 후 남은 정형화된 잡음을 줄 단위로 제거한다.

    동작:
      1. 줄 단위로 분리하여 _KO_NOISE_LINE_PATTERNS 매치 줄 삭제
      2. 마지막 부분의 "관련 기사 카루셀" 휴리스틱: 짧은 줄(40자 이하)이
         연속 5개 이상 나오면 그 시작 지점부터 끝까지 절단
      3. 연속 공백/줄바꿈 정리
    """
    if not text:
        return ""

    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in _KO_NOISE_LINE_PATTERNS):
            continue
        cleaned.append(stripped)

    # ── 관련 기사 카루셀 절단 휴리스틱 ──
    # 마지막 부분에서 짧은 줄(40자 이하)이 연속 5개 이상이면 그 시작부터 모두 제거.
    # 본문은 보통 50자 이상의 줄이 다수, 카루셀/관련기사 목록은 짧은 헤드라인 연속.
    short_run = 0
    cutoff = len(cleaned)
    for i in range(len(cleaned) - 1, -1, -1):
        if len(cleaned[i]) <= 40:
            short_run += 1
            if short_run >= 5:
                cutoff = i
        else:
            short_run = 0
            if cutoff < len(cleaned):
                break  # 본문 영역 재진입 - 절단 지점 확정

    if cutoff < len(cleaned):
        cleaned = cleaned[:cutoff]

    # 정리
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


async def scrape_article_body(url: str, fallback_url: str | None = None) -> str | None:
    """
    기사 URL에서 본문 텍스트를 추출한다.

    추출 순서:
      1) trafilatura (콘텐츠 밀도 기반, 가장 정확)
      2) BeautifulSoup + 확장된 _NOISE_PATTERN
      3) fallback_url 로 재시도

    각 단계 결과는 _korean_postprocess() 로 한국어 특화 잔여 잡음을 제거하고
    _is_valid_body() 로 품질 검사를 거친다.

    Args:
        url: 1순위 URL (보통 news.naver.com 의 wrapper)
        fallback_url: 1순위 실패 시 재시도 URL (보통 원본 언론사 URL)

    Returns:
        정제된 본문 텍스트, 또는 실패 시 None
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        html = response.text

        # ── 1순위: trafilatura ──
        text = _trafilatura_extract(html)
        if text:
            text = _korean_postprocess(text)
            if _is_valid_body(text):
                return text

        # ── 2순위: BS4 + 확장된 NOISE_PATTERN ──
        text = _bs4_extract(html)
        if text:
            text = _korean_postprocess(text)
            if _is_valid_body(text):
                return text

        # ── 3순위: fallback URL 재시도 ──
        if fallback_url and fallback_url != url:
            print(f"[Crawler] 본문 품질 불합격 - fallback 재시도: {fallback_url}")
            return await scrape_article_body(fallback_url, fallback_url=None)
        return None

    except Exception as e:
        print(f"[Crawler] 본문 스크래핑 실패 ({url}): {e}")
        if fallback_url and fallback_url != url:
            print(f"[Crawler] 스크래핑 오류 - fallback 재시도: {fallback_url}")
            return await scrape_article_body(fallback_url, fallback_url=None)
        return None


# ── 유틸리티 함수 ──

def _strip_html(text: str) -> str:
    """HTML 태그를 제거하고 HTML 엔티티를 디코딩한다."""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&quot;", '"').replace("&amp;", "&")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">")
    return clean.strip()


def _is_valid_body(text: str) -> bool:
    """
    추출된 텍스트가 실제 뉴스 기사 본문인지 판별한다.

    검사 항목:
      1. 최소 길이 (200자)
      2. 이용약관/면책 고지 패턴 부재
      3. 방송 대화록 패턴 부재 (진행자 마커 5줄 이상)
      4. 평균 줄 길이 (짧은 줄만 모인 헤드라인 카루셀 거부)
      5. 긴 줄 비율 (50자 이상 줄이 전체의 25% 이상)

    Returns:
        True  — 유효한 기사 본문
        False — 약관/방송/광고/잡음 콘텐츠
    """
    if len(text) < 200:
        return False

    # 이용약관/면책 고지 패턴
    _TOS_PATTERN = re.compile(
        r"채널A에서 제공하는 콘텐츠"
        r"|이용약관|개인정보\s*처리방침"
        r"|책임을 지지 않습니다"
        r"|법령의 준수 여부"
        r"|회원님들께서는.*네트워크",
        re.DOTALL,
    )
    if _TOS_PATTERN.search(text):
        return False

    # 방송 대화록 패턴 (진행자 마커가 5줄 이상 = 스크립트)
    broadcast_lines = re.findall(r"^[▷▶◆◇]\s+\S+\s*:", text, re.MULTILINE)
    if len(broadcast_lines) >= 5:
        return False

    # ── 줄 길이 분포 분석 (명백한 헤드라인/네비 잡음만 타겟 거부) ──
    # 짧은 정상 기사(스포츠 속보, 연예 단신)를 과잉 거부하지 않도록 보수적으로 판단:
    #   - 줄 수가 적으면(< 6) 분석하지 않고 통과 (짧은 정상 기사 보호)
    #   - 줄이 충분히 많은데(>= 6) 50자 이상 '실질 본문 줄'이 15% 미만이면
    #     헤드라인/관련기사 목록 같은 잡음으로 간주하여 거부
    # 이 조건은 "줄은 많지만 거의 다 짧다"(= 목록형 잡음)일 때만 발동한다.
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) >= 6:
        long_lines = sum(1 for ln in lines if len(ln) >= 50)
        long_ratio = long_lines / len(lines)
        if long_ratio < 0.15:
            return False

    return True


def _parse_pub_date(date_str: str) -> datetime:
    """
    네이버 API의 pubDate(RFC 2822)를 datetime으로 파싱한다.
    예: 'Mon, 01 Jan 2024 09:00:00 +0900'
    """
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.utcnow()
