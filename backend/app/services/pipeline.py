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
  │  [CT-01 Llama 요약] 3줄 요약 + 신뢰도 점수 산출                 │
  │          ↓                                                    │
  │  [CT-02 GPT 분류]  카테고리 분류 (CT-01 요약 입력)              │
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

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import async_session
from app.models import Article
from app.services.crawler import fetch_naver_news, scrape_article_body
from app.services.credibility import calculate_credibility
from app.services.embedding import get_embedding, get_embeddings_batch
from app.services.llm_processor import (
    VALID_CATEGORIES,
    _CATEGORY_FUZZY_MAP,
    process_article_with_llm,
)
from app.services.resilience import (
    AdaptiveRateController,
    BackPressureController,
)

# ── 백프레셔 컨트롤러 (모듈 레벨 싱글턴) ──
back_pressure = BackPressureController(pause_threshold=100, resume_threshold=50)


# ============================================================
# 카테고리 정규화 (LLM 실패 시 폴백 방어)
# ============================================================
def _normalize_category(cat: str | None) -> str:
    """
    crawler의 슬래시 형식("IT/과학"), 혹은 LLM이 반환한 유사 표현을
    config.yaml의 표준 카테고리(가운뎃점 "IT·과학")로 강제 정규화한다.

    ■ 왜 필요한가:
      - crawler.py fallback은 `raw.get("category", "사회")`로 네이버 API 호출 시
        사용한 키워드 카테고리를 그대로 저장. 여기에 슬래시 버전이 섞이면
        DB에 "IT·과학"과 "IT/과학"이 공존하여 프론트엔드 필터/탭이 깨진다.

    ■ 처리 순서:
      1. None/빈 문자열 → "사회" (안전 폴백)
      2. 이미 표준 VALID_CATEGORIES 중 하나면 그대로 반환
      3. _CATEGORY_FUZZY_MAP으로 부분 매칭 ("IT/과학" → "IT·과학" 등)
      4. 그래도 못 찾으면 "사회"
    """
    if not cat:
        return "사회"
    cat = cat.strip()
    if cat in VALID_CATEGORIES:
        return cat
    for keyword, canonical in _CATEGORY_FUZZY_MAP.items():
        if keyword in cat:
            return canonical
    # 슬래시/중간점 혼합 대응
    normalized = cat.replace("/", "·")
    if normalized in VALID_CATEGORIES:
        return normalized
    return "사회"


# ============================================================
# Redis 캐시 무효화 (Task 4)
# ============================================================
async def _invalidate_all_feed_caches():
    """
    크롤링 완료 후 모든 사용자의 피드 캐시를 무효화한다.
    새 기사가 DB에 적재되면 즉시 피드에 반영되도록 보장.
    Redis 장애 시에도 파이프라인은 중단되지 않음 (5분 TTL 만료 대기).
    """
    try:
        redis_conn = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            deleted = 0
            async for key in redis_conn.scan_iter(match="user:*:feed", count=100):
                await redis_conn.delete(key)
                deleted += 1
            if deleted:
                print(f"[Pipeline] Redis 피드 캐시 {deleted}건 무효화 완료")
        finally:
            await redis_conn.aclose()
    except Exception as e:
        print(f"[Pipeline] Redis 캐시 무효화 실패 (무시, 5분 TTL 만료 대기): {e}")


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

    # ── Step 0: NAVER 자격증명 사전 점검 ──
    if not settings.NAVER_CLIENT_ID or not settings.NAVER_CLIENT_SECRET:
        print(
            "[Pipeline] NAVER_CLIENT_ID/SECRET 미설정 — 크롤링 불가. "
            "backend/.env 파일에 API 키를 추가하세요."
        )
        return

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

    print(f"[Pipeline] 총 {len(all_raw_articles)}건 수집 완료, 중복 필터링 중...")

    # ── Step 3: 일괄 중복 필터링 (DB 1회 조회로 이미 있는 URL 제거) ──
    all_urls = [raw["link"] for raw in all_raw_articles]
    existing_urls = await _get_existing_urls(all_urls)
    new_articles = [raw for raw in all_raw_articles if raw["link"] not in existing_urls]

    dup_count = len(all_raw_articles) - len(new_articles)
    print(f"[Pipeline] 중복 {dup_count}건 제외, 신규 {len(new_articles)}건 처리 시작...")

    # ── Step 4: 개별 기사 처리 ──
    # 백프레셔에 신규 건수만 등록
    await back_pressure.increment(len(new_articles))

    processed_count = 0
    skipped_count = 0

    for raw in new_articles:
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

    # ── Redis 캐시 무효화: 새 기사가 즉시 피드에 반영되도록 (Task 4) ──
    if processed_count > 0:
        await _invalidate_all_feed_caches()

    # ── 완료 보고 ──
    elapsed = (datetime.now() - pipeline_start).total_seconds()
    print(f"\n[Pipeline] 파이프라인 완료:")
    print(f"  - 처리 성공: {processed_count}건")
    print(f"  - 건너뜀/실패: {skipped_count}건")
    print(f"  - 소요 시간: {elapsed:.1f}초")
    print(f"{'='*60}\n")


async def _get_existing_urls(urls: list[str]) -> set[str]:
    """
    URL 리스트를 받아 이미 DB에 존재하는 URL을 일괄 조회한다.
    크롤링 전 한 번만 호출하여 불필요한 스크래핑/LLM 처리를 방지한다.

    Args:
        urls: 확인할 URL 리스트

    Returns:
        DB에 이미 존재하는 URL의 set
    """
    if not urls:
        return set()

    async with async_session() as session:
        # URL 목록으로 IN 쿼리 — 대량 조회를 1회 DB 호출로 처리
        stmt = select(Article.url).where(Article.url.in_(urls))
        result = await session.execute(stmt)
        return {row[0] for row in result.fetchall()}


async def _process_single_article(raw: dict) -> bool:
    """
    단일 기사를 처리한다: 본문 스크래핑 → LLM 처리 → 임베딩 → DB 저장.
    (중복 필터링은 run_crawl_pipeline에서 일괄 처리 완료)

    Args:
        raw: 네이버 뉴스 API에서 수집한 기사 메타데이터
            {"title", "link", "description", "pub_date", "category"}

    Returns:
        True: 성공적으로 DB에 저장됨
        False: 건너뜀 (스크래핑 실패, LLM 실패 등)
    """
    url = raw["link"]

    # ── 본문 스크래핑 ──
    # (Bug fix) 스크래핑 실패 시에도 기사를 버리지 않는다.
    #           네이버 API 응답의 description을 폴백 본문으로 사용해야
    #           '크롤링 결과 0건' 현상을 예방할 수 있다.
    body = await scrape_article_body(url)
    if not body:
        fallback = (raw.get("description") or "").strip()
        if not fallback:
            print(f"[Pipeline] 본문 스크래핑 실패 + description 없음 — 건너뜀: {url}")
            return False
        print(f"[Pipeline] 본문 스크래핑 실패 — description 폴백 사용: {url}")
        body = fallback

    # ── 기자명 / 언론사 추출 ──
    # 언론사는 credibility v2 의 RB-04 3-tier 계산(기자+언론사 조합)에
    # 사용되므로 LLM 호출 전에 미리 뽑아둔다.
    journalist = _extract_journalist(body)
    press = _extract_press(url)

    # ── LLM 처리: CT-01(Llama 요약) → CT-02(GPT 분류) 순차 호출 ──
    # fallback_category: 크롤러가 수집 시 사용한 섹션 카테고리를 전달.
    # GPT가 분류에 실패하거나 없을 때 '사회' 고정 폴백이 아닌 이 값을 사용하여
    # 세계/연예/스포츠 기사가 전부 사회로 흡수되는 현상을 방지한다.
    raw_category = _normalize_category(raw.get("category"))
    llm_result = await process_article_with_llm(
        title=raw["title"],
        body=body,
        journalist=journalist,
        fallback_category=raw_category,
        press=press,
    )

    if not llm_result:
        # LLM 실패 시에도 신뢰도는 규칙 기반으로 계산 (LLM에 의존하지 않음)
        # ★ 카테고리는 반드시 표준 가운뎃점(·) 형식으로 정규화하여 DB 일관성 유지
        fallback_summary = raw.get("description", "요약 없음")
        cred = calculate_credibility(
            title=raw["title"], body=body, journalist=journalist, press=press
        )
        llm_result = {
            "summary": fallback_summary,
            "category": _normalize_category(raw.get("category")),
            "credibility": cred["credibility"],
            "rb01_tone": cred["rb01_tone"],
            "rb02_density": cred["rb02_density"],
            "rb03_quotes": cred["rb03_quotes"],
            "rb04_journalist": cred["rb04_journalist"],
        }
    else:
        # LLM 성공 경로에서도 혹시 모를 변형(슬래시/유사표현)을 한번 더 정규화
        llm_result["category"] = _normalize_category(llm_result.get("category"))

    # ── Ko-SBERT 임베딩 생성 (512 토큰 제한: '제목+요약'만 사용, Task 4) ──
    try:
        embed_text = f"{raw['title']} {llm_result['summary']}"
        embedding = await get_embedding(embed_text)
    except Exception as e:
        print(f"[Pipeline] 임베딩 생성 실패 — 롤백 ({url}): {e}")
        return False

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
            rb01_tone=llm_result.get("rb01_tone"),
            rb02_density=llm_result.get("rb02_density"),
            rb03_quotes=llm_result.get("rb03_quotes"),
            rb04_journalist=llm_result.get("rb04_journalist"),
            press=press,
            journalist=journalist,
            published_at=raw.get("pub_date") or datetime.utcnow(),
        ).on_conflict_do_update(
            index_elements=["url"],
            set_={
                "summary": llm_result["summary"],
                "category": llm_result["category"],
                "embedding": embedding,
                "credibility": llm_result["credibility"],
                "rb01_tone": llm_result.get("rb01_tone"),
                "rb02_density": llm_result.get("rb02_density"),
                "rb03_quotes": llm_result.get("rb03_quotes"),
                "rb04_journalist": llm_result.get("rb04_journalist"),
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
    #
    # ■ 첫 실행 타이밍 설계:
    #   main.py 의 _startup_crawl() 이 서버 기동 직후 1회 즉시 크롤링을 담당한다.
    #   → 여기서는 next_run_time 을 지정하지 않아 "인터벌 후 최초 실행"(T+1h) 로
    #     설정되며, startup 크롤과의 더블 실행을 피한다.
    #   → 결과적으로 사용자 체감: T=0(즉시) → T+1h → T+2h → ... 매시간 자동 크롤.
    _scheduler.add_job(
        run_crawl_pipeline,
        trigger=IntervalTrigger(hours=settings.CRAWL_INTERVAL_HOURS),
        id="crawl_pipeline",
        name="뉴스 기사 수집 파이프라인",
        replace_existing=True,
    )

    print(
        f"[Scheduler] 크롤링 스케줄러 등록 완료 "
        f"(주기: {settings.CRAWL_INTERVAL_HOURS}시간, 첫 실행은 startup 태스크가 담당)"
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


# ============================================================
# 즉시 크롤링 안전 래퍼 (서버 시작 시 호출)
# ============================================================
async def run_crawl_pipeline_safely() -> int:
    """
    run_crawl_pipeline()을 예외 안전하게 실행하고
    실제 DB에 저장된 기사 수를 반환한다.

    ■ 용도:
      main.py의 _startup_crawl() 태스크에서 호출되어
      서버 시작 시 즉시 크롤링을 실행한다.

    ■ 예외 흡수:
      크롤링 중 어떤 예외가 발생해도 앱 전체를 중단시키지 않도록
      모든 Exception을 흡수하고 0을 반환한다. 실패 상세는 stdout에 로깅.

    ■ 반환값:
      DB의 articles 테이블 총 행 수. 호출자가 0이면 재시도 여부를 결정할 수 있다.
    """
    from sqlalchemy import func, select

    from app.core.database import async_session
    from app.models import Article

    try:
        await run_crawl_pipeline()
    except Exception as e:
        print(
            f"[Pipeline] 크롤링 실행 중 예외 발생 (서버는 계속 동작): "
            f"{type(e).__name__}: {e}"
        )
        return 0

    # 실제 DB에 저장된 행 수를 재조회
    try:
        async with async_session() as session:
            result = await session.execute(select(func.count()).select_from(Article))
            return int(result.scalar_one() or 0)
    except Exception:
        return 0
