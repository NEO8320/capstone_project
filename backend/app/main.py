# -*- coding: utf-8 -*-
"""
FastAPI 애플리케이션 엔트리포인트
==================================

주요 설정:
  1. 비동기 lifespan 관리: DB 초기화, Redis 연결, APScheduler 시작/종료
  2. Rate Limiting: SlowAPI를 통한 분당 60회 요청 제한
  3. CORS: React SPA 프론트엔드 허용
  4. 라우터 등록: 피드, 피드백 (3단계), 인증/구독/설정 (4단계 예정)
"""

import sys as _sys
# Windows cp949 환경에서 UnicodeEncodeError 방지 - 어떤 실행 경로든 보장
if _sys.platform == "win32":
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import init_db
from app.core.limiter import limiter
from app.core import redis as redis_module


# ============================================================
# 즉시 크롤링 태스크 (서버 시작 직후 백그라운드 1회 실행)
# ============================================================
# uvicorn --reload 시 자식 프로세스에서 한 번만 실행되도록 하는 모듈 레벨 플래그.
# 같은 프로세스에서 lifespan이 두 번 호출되어도 중복 크롤링을 방지한다.
_STARTUP_CRAWL_STARTED = False

# DB 초기화 성공 여부 - /health 엔드포인트에서 보고
_DB_INIT_OK = False


async def _startup_crawl():
    """
    서버 시작 직후 백그라운드에서 1회만 실행되는 즉시 크롤링 태스크.

    ■ 실행 순서 (순차 await로 레이스 방지):
      1. Ko-SBERT 모델 프리로드 대기
         — 크롤링 중 get_embedding()이 모델 로드를 기다리며 블로킹되는 것을 방지
      2. DB가 비어 있으면 샘플 기사 자동 시드
         — 콜드 스타트 사용자가 5초 내로 피드를 볼 수 있게
      3. run_crawl_pipeline_safely() 1회 실행
      4. 크롤링 결과가 0건이면 60초 후 STARTUP_CRAWL_RETRY_ON_ZERO회 재시도

    ■ 더블 크롤링 방지:
      APScheduler는 1시간 주기로 별도 실행되며, 첫 실행은 T+1h이므로
      본 startup 태스크와 시간이 겹치지 않는다.

    ■ lifespan 블로킹 방지:
      이 함수는 asyncio.ensure_future()로 호출되어 yield를 블로킹하지 않는다.
    """
    global _STARTUP_CRAWL_STARTED
    if _STARTUP_CRAWL_STARTED:
        print("[Startup] 즉시 크롤링이 이미 실행됨 - 건너뜀 (reload 재기동 감지)")
        return
    _STARTUP_CRAWL_STARTED = True

    print("[Startup] 즉시 크롤링 대기 중... (Ko-SBERT 프리로드 완료 후 시작)")

    # ── Step 1: Ko-SBERT 프리로드 (순차 대기) ──
    try:
        from app.services.embedding import get_embedding
        await get_embedding("모델 워밍업")
        print("[Startup] Ko-SBERT 모델 프리로드 완료.")
    except Exception as e:
        print(f"[Startup] Ko-SBERT 프리로드 실패 - 크롤링 중단: {e}")
        return  # 임베딩 없이는 크롤링·시드가 모두 실패하므로 중단

    # ── Step 2: 빈 DB 자동 시드 ──
    if settings.AUTO_SEED_ON_EMPTY_DB:
        try:
            from app.api.admin import seed_sample_articles_if_empty
            from app.core.database import async_session
            async with async_session() as db:
                seeded = await seed_sample_articles_if_empty(db)
                if seeded:
                    print(
                        f"[Startup] 샘플 기사 {seeded}건 자동 시드 완료 "
                        f"(피드 즉시 사용 가능)"
                    )
        except Exception as e:
            print(f"[Startup] 샘플 시드 실패 (서버는 계속 진행): {e}")

    # ── Step 3: 실제 크롤링 실행 (재시도 루프) ──
    if not settings.CRAWL_ON_STARTUP:
        print("[Startup] CRAWL_ON_STARTUP=False - 즉시 크롤링 건너뜀")
        return

    from app.services.pipeline import run_crawl_pipeline_safely

    retries_left = settings.STARTUP_CRAWL_RETRY_ON_ZERO
    attempt = 0
    while True:
        attempt += 1
        print(f"[Startup] 크롤링 즉시 실행 시작 (시도 {attempt})")
        saved = await run_crawl_pipeline_safely()
        print(f"[Startup] 크롤링 완료: {saved}건 DB 저장됨")

        if saved > 0 or retries_left <= 0:
            break

        retries_left -= 1
        print(
            f"[Startup] 크롤링 결과 0건 - 60초 후 재시도 "
            f"(남은 재시도: {retries_left})"
        )
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 비동기 lifespan 컨텍스트 매니저.

    시작 시:
      1. PostgreSQL + pgvector 테이블 초기화 (지수 백오프 재시도)
      2. Redis 연결 풀 생성
      3. APScheduler 등록 (1시간 주기, 첫 실행은 T+1h)
      4. 즉시 크롤링 태스크를 백그라운드 fire-and-forget 등록
         (내부에서 Ko-SBERT 프리로드 → 시드 → 크롤링 순차 실행)

    종료 시:
      1. Redis 연결 풀 해제
      2. APScheduler 정상 종료
    """
    # ── 1. DB 초기화 (재시도 루프, 실패해도 서버는 시작) ──
    # 모듈 레벨 플래그 - /health 엔드포인트에서 DB 상태 보고용
    global _DB_INIT_OK
    _DB_INIT_OK = False
    try:
        print("[Startup] PostgreSQL + pgvector 초기화 중 (재시도 포함)...")
        await init_db()
        print("[Startup] DB 초기화 완료.")
        _DB_INIT_OK = True
    except Exception as e:
        # 시각적으로 눈에 띄도록 큰 배너 출력 - 사용자가 백엔드 창에서 즉시 인지 가능
        banner = (
            "\n"
            "##############################################################\n"
            "#                                                            #\n"
            "#   [치명적] PostgreSQL DB 연결 실패!                        #\n"
            "#                                                            #\n"
            "#   서버는 계속 실행되지만 모든 API 가 500 을 반환합니다.    #\n"
            "#   프론트엔드에서 \"피드를 불러오는 데 실패\" 가 보일 것입니다.#\n"
            "#                                                            #\n"
            "#   해결 방법:                                               #\n"
            "#   1) Docker Desktop 이 실행 중인지 확인                    #\n"
            "#   2) docker ps 로 news_curator_db 컨테이너 상태 확인       #\n"
            "#   3) .\\diagnose.bat 실행으로 정확한 원인 파악             #\n"
            "#   4) backend\\.env 의 DATABASE_URL 비밀번호가              #\n"
            "#      docker-compose.yml 의 POSTGRES_PASSWORD 와 일치하는지 #\n"
            "#                                                            #\n"
            "##############################################################\n"
        )
        print(banner)
        print(f"[Startup] DB 초기화 최종 실패 (원인): {e}")
        print("##############################################################\n")

    # ── 2. Redis 연결 ──
    try:
        print("[Startup] Redis 연결 중...")
        redis_module.redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_module.redis_client.ping()
        print("[Startup] Redis 연결 완료.")
    except Exception as e:
        redis_module.redis_client = None
        print(f"[Startup] Redis 연결 실패 (캐시 비활성): {e}")

    # ── 3. APScheduler 크롤링 스케줄러 시작 (1시간 주기 등록만) ──
    try:
        from app.services.pipeline import start_scheduler
        start_scheduler()
        print("[Startup] APScheduler 크롤링 스케줄러 시작 완료.")
    except Exception as e:
        print(f"[Startup] 스케줄러 시작 실패 (서버는 계속 시작됨): {e}")

    # ── 4. 즉시 크롤링 태스크를 백그라운드에 등록 (yield 블로킹 없음) ──
    # 내부에서 Ko-SBERT 프리로드 → 자동 시드 → run_crawl_pipeline 순차 실행
    asyncio.ensure_future(_startup_crawl())

    print(f"[Startup] {settings.APP_NAME} 서버 준비 완료!")

    yield  # ← 여기서 애플리케이션이 요청을 처리

    # ── 종료(Shutdown) ──
    print("[Shutdown] 리소스 정리 중...")
    if redis_module.redis_client:
        await redis_module.redis_client.close()
        print("[Shutdown] Redis 연결 해제 완료.")

    try:
        from app.services.pipeline import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    print("[Shutdown] 서버 종료 완료.")


# ============================================================
# FastAPI 앱 인스턴스 생성
# ============================================================
app = FastAPI(
    title=settings.APP_NAME,
    description="AI 기반 개인화 뉴스 큐레이팅 서비스 API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Rate Limiting 미들웨어 등록 ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS 미들웨어 ──
# React SPA(Vite dev: localhost:5173, 빌드: 동일 오리진) 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite 개발 서버
        "http://localhost:5174",  # Vite 개발 서버 (포트 충돌 시 대체)
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# API 라우터 등록
# ============================================================
from app.api.admin import router as admin_router
from app.api.articles import router as articles_router
from app.api.auth import router as auth_router
from app.api.feed import router as feed_router
from app.api.feedback import router as feedback_router, undo_router
from app.api.subscriptions import router as subscriptions_router
from app.api.users import router as users_router

app.include_router(auth_router, prefix="/api/auth", tags=["인증"])
app.include_router(users_router, prefix="/api/users", tags=["사용자"])
app.include_router(feed_router, prefix="/api", tags=["피드"])
app.include_router(feedback_router, prefix="/api/articles", tags=["피드백"])
app.include_router(undo_router, prefix="/api/v1/feed", tags=["피드백"])
app.include_router(subscriptions_router, prefix="/api/subscriptions", tags=["구독"])
# NOTE: articles_router uses /{article_url:path} — must be registered LAST among /api/articles/* routes
app.include_router(articles_router, prefix="/api/articles", tags=["기사"])
app.include_router(admin_router, prefix="/api/admin", tags=["관리자"])


# ============================================================
# 헬스 체크 엔드포인트
# ============================================================
@app.get("/health", tags=["시스템"])
@limiter.limit(settings.RATE_LIMIT)
async def health_check(request: Request):
    """서버 상태 확인용 엔드포인트."""
    redis_ok = False
    if redis_module.redis_client:
        try:
            await redis_module.redis_client.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

    # DB 상태도 함께 보고 - 진단 스크립트가 이 응답으로 DB 상태 판별
    db_ok = False
    try:
        from sqlalchemy import text
        from app.core.database import async_session
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    # DB 가 안 되면 status=degraded 로 신호 (200 은 유지하여 health probe 호환)
    overall = "healthy" if (db_ok and _DB_INIT_OK) else "degraded"

    return {
        "status": overall,
        "service": settings.APP_NAME,
        "db_connected": db_ok,
        "db_init_ok": _DB_INIT_OK,
        "redis_connected": redis_ok,
    }


# ============================================================
# 개발 서버 실행 (직접 실행 시)
# ============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
