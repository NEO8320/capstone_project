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

# ── 네이버 뉴스 API 전용 서킷 브레이커 ──
naver_circuit = CircuitBreaker(name="naver_news_api", failure_threshold=5, recovery_timeout=30.0)

# ── 카테고리별 검색 키워드 매핑 ──
# 네이버 뉴스 검색 API는 카테고리 필터가 없으므로 대표 키워드로 검색한다.
#
# ★ 키는 반드시 config.yaml categories와 동일한 가운뎃점(·) 형식으로 유지해야 한다.
#   - 과거에 "IT/과학", "생활/문화" (슬래시) 형식을 쓰다가 DB에 이중 카테고리가 저장되는
#     치명적 버그가 있었음. 프론트엔드 필터/탭이 매칭 실패하는 원인이 되었다.
#   - 이제 8개 카테고리 전부 커버 (연예·스포츠 포함).
CATEGORY_KEYWORDS: dict[str, str] = {
    "정치": "정치 국회 대통령",
    "경제": "경제 주식 금리",
    "사회": "사회 사건 사고",
    "생활·문화": "문화 생활 여행",
    "IT·과학": "IT 기술 AI 과학",
    "세계": "세계 국제 외교",
    "연예": "연예 아이돌 드라마",
    "스포츠": "스포츠 축구 야구",
}


async def fetch_naver_news(
    category: str,
    max_articles: int = 50,
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

                    articles.append({
                        "title": clean_title,
                        "link": item.get("originallink") or item.get("link", ""),
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


async def scrape_article_body(url: str) -> str | None:
    """
    기사 URL에서 본문 텍스트를 추출한다.

    BeautifulSoup으로 HTML을 파싱하여 기사 본문 영역을 찾고,
    불필요한 광고/스크립트를 제거한 순수 텍스트를 반환한다.

    Args:
        url: 기사 원문 URL

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

        soup = BeautifulSoup(response.text, "html.parser")

        # ── 불필요한 요소 제거 ──
        for tag in soup.find_all(["script", "style", "iframe", "aside", "nav"]):
            tag.decompose()

        # ── 본문 추출 전략 (우선순위순) ──
        # 1) 네이버 뉴스 본문 영역
        body_el = soup.find("article", {"id": "dic_area"})
        # 2) 일반적인 기사 본문 class 패턴
        if not body_el:
            body_el = soup.find("div", class_=re.compile(r"article[_-]?body|news[_-]?body|content"))
        # 3) <article> 태그
        if not body_el:
            body_el = soup.find("article")

        if body_el:
            text = body_el.get_text(separator="\n", strip=True)
        else:
            # 최후 수단: <body> 전체 텍스트 (노이즈 포함 가능)
            text = soup.get_text(separator="\n", strip=True)

        # 연속 공백/줄바꿈 정리
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        return text.strip() if text.strip() else None

    except Exception as e:
        print(f"[Crawler] 본문 스크래핑 실패 ({url}): {e}")
        return None


# ── 유틸리티 함수 ──

def _strip_html(text: str) -> str:
    """HTML 태그를 제거하고 HTML 엔티티를 디코딩한다."""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.replace("&quot;", '"').replace("&amp;", "&")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">")
    return clean.strip()


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
