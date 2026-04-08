"""
기사 수집 파이프라인 오케스트레이터 + APScheduler 스케줄러
=========================================================

1시간 주기로 실행되는 전체 파이프라인:

  ┌──────────────────────────────────────────────────────────────┐
  │  [적응형 수집량 결정]  CPU 부하에 따라 카테고리당 수집 건수 결정  │
  │          ↓                                                    │
  │  [네이버 뉴스 API 수집]  6개 카테고리 × N건 비동기 수집         │
  │          ↓                                                    │
  │  [BeautifulSoup 본문 정제]  기사 URL → 본문 텍스트 추출         │
  │          ↓                                                    │
  │  [백프레셔 확인]  대기큐 100건 초과 시 일시 중지                 │
  │          ↓                                                    │
  │  [LLM 처리]  3줄 요약 + 카테고리 분류 + 신뢰도 점수 산출        │
  │          ↓                                                    │
  │  [Ko-SBERT 임베딩]  '제목 + 요약' → 768차원 벡터 생성          │
  │          ↓                                                    │
  │  [DB 저장]  pgvector에 기사 + 임베딩 upsert                   │
  └──────────────────────────────────────────────────────────────┘

가용성 제어:
  - 서킷 브레이커: 외부 API 5회 연속 실패 시 30초간 호출 중단
  - 백프레셔: 대기 큐 100건 초과 시 일시 중지, 50건 이하 시 재개
  - 적응형 수집량: CPU <50%→50건, 50~70%→30건, >70%→15건
"""

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import async_session
from app.models import Article
from app.services.crawler import fetch_naver_news, scrape_article_body
from app.services.embedding import get_embedding, get_embeddings_batch
from app.services.llm_processor import process_article_with_llm
from app.services.resilience import (
    AdaptiveRateController,
    BackPressureController,
)

# ── 백프레셔 컨트롤러 (모듈 레벨 싱글턴) ──
back_pressure = BackPressureController(pause_threshold=100, resume_threshold=50)


async def run_crawl_pipeline():
    """
    전체 기사 수집 파이프라인을 실행한다.
    APScheduler에 의해 1시간 주기로 호출된다.

    실행 흐름:
      1. CPU 부하 측정 → 카테고리당 수집량 결정
      2. 6개 카테고리 병렬 수집 (네이버 뉴스 API)
      3. 각 기사에 대해:
         a. 백프레셔 확인 (대기큐 초과 시 대기)
         b. 본문 스크래핑 (BeautifulSoup)
         c. LLM 처리 (요약/분류/신뢰도)
         d. Ko-SBERT 임베딩 생성
         e. DB에 upsert
    """
    pipeline_start = datetime.now()
    print(f"\n{'='*60}")
    print(f"[Pipeline] 기사 수집 파이프라인 시작: {pipeline_start}")
    print(f"{'='*60}")

    # ── Step 1: 적응형 수집량 결정 ──
    articles_per_category = await AdaptiveRateController.get_articles_per_category_async()

    # ── Step 2: 6개 카테고리 병렬 수집 ──
    categories = settings.CRAWL_CATEGORIES
    print(f"[Pipeline] {len(categories)}개 카테고리 × {articles_per_category}건 수집 시작")

    # 모든 카테고리를 동시에 비동기 수집
    fetch_tasks = [
        fetch_naver_news(category, max_articles=articles_per_category)
        for category in categories
    ]
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # 수집 결과를 단일 리스트로 병합
    all_raw_articles = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"[Pipeline] {categories[i]} 수집 실패: {result}")
            continue
        all_raw_articles.extend(result)
        print(f"[Pipeline] {categories[i]}: {len(result)}건 수집")

    print(f"[Pipeline] 총 {len(all_raw_articles)}건 수집 완료, 처리 시작...")

    # ── Step 3: 개별 기사 처리 ──
    # 백프레셔에 전체 건수 등록
    await back_pressure.increment(len(all_raw_articles))

    processed_count = 0
    skipped_count = 0

    for raw in all_raw_articles:
        # 백프레셔 확인 — 대기큐 초과 시 재개될 때까지 대기
        await back_pressure.wait_if_paused()

        try:
            success = await _process_single_article(raw)
            if success:
                processed_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"[Pipeline] 기사 처리 중 오류: {e}")
            skipped_count += 1
        finally:
            # 처리 완료 → 백프레셔 카운트 감소
            await back_pressure.decrement()

    # ── 완료 보고 ──
    elapsed = (datetime.now() - pipeline_start).total_seconds()
    print(f"\n[Pipeline] 파이프라인 완료:")
    print(f"  - 처리 성공: {processed_count}건")
    print(f"  - 건너뜀/실패: {skipped_count}건")
    print(f"  - 소요 시간: {elapsed:.1f}초")
    print(f"{'='*60}\n")


async def _process_single_article(raw: dict) -> bool:
    """
    단일 기사를 처리한다: 중복 확인 → 본문 스크래핑 → LLM 처리 → 임베딩 → DB 저장.

    Args:
        raw: 네이버 뉴스 API에서 수집한 기사 메타데이터
            {"title", "link", "description", "pub_date", "category"}

    Returns:
        True: 성공적으로 DB에 저장됨
        False: 건너뜀 (중복, 스크래핑 실패, LLM 실패 등)
    """
    url = raw["link"]

    # ── 중복 확인: 이미 DB에 있는 기사는 건너뜀 ──
    async with async_session() as session:
        existing = await session.get(Article, url)
        if existing:
            return False

    # ── 본문 스크래핑 ──
    body = await scrape_article_body(url)
    if not body:
        return False

    # ── 기자명 추출 (본문 끝부분에서 '기자' 패턴 검색) ──
    journalist = _extract_journalist(body)

    # ── LLM 처리: 요약 + 카테고리 + 신뢰도 점수 ──
    llm_result = await process_article_with_llm(
        title=raw["title"],
        body=body,
        journalist=journalist,
    )

    if not llm_result:
        # LLM 실패 시 기본값으로 저장 (요약은 description 사용)
        llm_result = {
            "summary": raw.get("description", "요약 없음"),
            "category": raw.get("category", "사회"),
            "credibility": 50.0,  # 기본 중간값
        }

    # ── Ko-SBERT 임베딩 생성 ──
    # '제목 + 요약'을 합쳐서 768차원 벡터 생성
    embed_text = f"{raw['title']} {llm_result['summary']}"
    embedding = await get_embedding(embed_text)

    # ── DB 저장 (upsert: 중복 URL이면 업데이트) ──
    async with async_session() as session:
        stmt = pg_insert(Article).values(
            url=url,
            title=raw["title"],
            body=body,
            summary=llm_result["summary"],
            category=llm_result["category"],
            embedding=embedding,
            credibility=llm_result["credibility"],
            press=_extract_press(url),
            journalist=journalist,
            published_at=raw.get("pub_date", datetime.utcnow()),
        ).on_conflict_do_update(
            index_elements=["url"],
            set_={
                "summary": llm_result["summary"],
                "category": llm_result["category"],
                "embedding": embedding,
                "credibility": llm_result["credibility"],
            },
        )
        await session.execute(stmt)
        await session.commit()

    return True


def _extract_journalist(body: str) -> str | None:
    """
    기사 본문에서 기자명을 추출한다.
    한국 뉴스 관례: 본문 끝에 '홍길동 기자' 패턴이 있음.
    """
    import re
    # '이름 기자' 패턴 (2~4글자 한글 이름 + 기자/특파원)
    match = re.search(r"([가-힣]{2,4})\s*(기자|특파원|통신원)", body[-200:])
    if match:
        return match.group(1)
    return None


def _extract_press(url: str) -> str:
    """
    기사 URL에서 언론사명을 추출한다.
    도메인 기반으로 주요 언론사를 매핑.
    """
    # 주요 언론사 도메인 매핑
    press_map = {
        "chosun.com": "조선일보",
        "joongang.co.kr": "중앙일보",
        "donga.com": "동아일보",
        "hani.co.kr": "한겨레",
        "khan.co.kr": "경향신문",
        "mk.co.kr": "매일경제",
        "hankyung.com": "한국경제",
        "sbs.co.kr": "SBS",
        "kbs.co.kr": "KBS",
        "mbc.co.kr": "MBC",
        "yna.co.kr": "연합뉴스",
        "ytn.co.kr": "YTN",
        "jtbc.co.kr": "JTBC",
        "mt.co.kr": "머니투데이",
        "edaily.co.kr": "이데일리",
    }

    url_lower = url.lower()
    for domain, name in press_map.items():
        if domain in url_lower:
            return name

    # 매칭되지 않으면 도메인을 그대로 반환
    import re
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else "알 수 없음"


# ============================================================
# APScheduler 스케줄러 설정
# ============================================================
_scheduler = None


def create_scheduler():
    """
    APScheduler의 AsyncIOScheduler를 생성하고
    크롤링 파이프라인을 1시간 주기로 등록한다.

    Returns:
        AsyncIOScheduler 인스턴스

    Note:
        FastAPI lifespan에서 호출하여 시작/종료를 관리한다.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    global _scheduler

    _scheduler = AsyncIOScheduler()

    # 크롤링 파이프라인을 1시간 주기로 등록
    _scheduler.add_job(
        run_crawl_pipeline,
        trigger=IntervalTrigger(hours=settings.CRAWL_INTERVAL_HOURS),
        id="crawl_pipeline",
        name="뉴스 기사 수집 파이프라인",
        replace_existing=True,
        # 서버 시작 직후 첫 실행 (next_run_time=None이면 인터벌 후 첫 실행)
        # 즉시 실행하려면 아래 주석 해제:
        # next_run_time=datetime.now(),
    )

    print(
        f"[Scheduler] 크롤링 스케줄러 등록 완료 "
        f"(주기: {settings.CRAWL_INTERVAL_HOURS}시간)"
    )

    return _scheduler


def start_scheduler():
    """APScheduler를 시작한다."""
    global _scheduler
    if _scheduler is None:
        create_scheduler()
    _scheduler.start()
    print("[Scheduler] APScheduler 시작됨")


def stop_scheduler():
    """APScheduler를 정상 종료한다."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        print("[Scheduler] APScheduler 종료됨")
