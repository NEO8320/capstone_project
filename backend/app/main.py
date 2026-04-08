"""
FastAPI 애플리케이션 엔트리포인트
==================================

주요 설정:
  1. 비동기 lifespan 관리: DB 초기화, Redis 연결, APScheduler 시작/종료
  2. Rate Limiting: SlowAPI를 통한 분당 60회 요청 제한
  3. CORS: React SPA 프론트엔드 허용
  4. 라우터 등록: 인증, 피드, 피드백, 구독, 설정 API
"""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import init_db

# ── Rate Limiter 설정 ──
# 클라이언트 IP 기반으로 분당 60회 제한
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT])

# ── Redis 클라이언트 (전역, lifespan에서 초기화) ──
redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 비동기 lifespan 컨텍스트 매니저.

    시작 시:
      1. PostgreSQL + pgvector 테이블 초기화
      2. Redis 연결 풀 생성
      3. APScheduler 크롤링 스케줄러 시작 (별도 모듈에서 구현 예정)

    종료 시:
      1. Redis 연결 풀 해제
      2. APScheduler 정상 종료
    """
    global redis_client

    # ── 시작(Startup) ──
    # DB 초기화 (PostgreSQL 미실행 시 경고 후 계속 진행)
    try:
        print("[Startup] PostgreSQL + pgvector 초기화 중...")
        await init_db()
        print("[Startup] DB 초기화 완료.")
    except Exception as e:
        print(f"[Startup] DB 연결 실패 (서버는 계속 시작됨): {e}")

    # Redis 연결 (미실행 시 경고 후 계속 진행)
    try:
        print("[Startup] Redis 연결 중...")
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        print("[Startup] Redis 연결 완료.")
    except Exception as e:
        redis_client = None
        print(f"[Startup] Redis 연결 실패 (캐시 비활성): {e}")

    # APScheduler 시작 (2단계에서 구현 예정)
    # from app.services.crawler import start_scheduler
    # start_scheduler()
    print("[Startup] APScheduler 크롤링 스케줄러는 2단계에서 활성화됩니다.")

    print(f"[Startup] {settings.APP_NAME} 서버 준비 완료!")

    yield  # ← 여기서 애플리케이션이 요청을 처리

    # ── 종료(Shutdown) ──
    print("[Shutdown] 리소스 정리 중...")
    if redis_client:
        await redis_client.close()
        print("[Shutdown] Redis 연결 해제 완료.")

    # APScheduler 종료
    # scheduler.shutdown(wait=True)
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
        "http://localhost:3000",  # 대체 포트
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Redis 의존성 주입 헬퍼
# ============================================================
def get_redis() -> aioredis.Redis:
    """FastAPI Depends()를 통해 Redis 클라이언트를 주입한다."""
    if redis_client is None:
        raise RuntimeError("Redis 연결이 초기화되지 않았습니다.")
    return redis_client


# ============================================================
# API 라우터 등록 (단계별 구현 시 주석 해제)
# ============================================================
# from app.api.auth import router as auth_router
# from app.api.feed import router as feed_router
# from app.api.feedback import router as feedback_router
# from app.api.subscriptions import router as subscription_router
# from app.api.settings import router as settings_router

# app.include_router(auth_router, prefix="/api/auth", tags=["인증"])
# app.include_router(feed_router, prefix="/api", tags=["피드"])
# app.include_router(feedback_router, prefix="/api/articles", tags=["피드백"])
# app.include_router(subscription_router, prefix="/api/subscriptions", tags=["구독"])
# app.include_router(settings_router, prefix="/api/settings", tags=["설정"])


# ============================================================
# 헬스 체크 엔드포인트
# ============================================================
@app.get("/health", tags=["시스템"])
@limiter.limit(settings.RATE_LIMIT)
async def health_check(request: Request):
    """
    서버 상태 확인용 엔드포인트.
    DB 및 Redis 연결 상태를 포함하여 반환한다.
    """
    # Redis 상태 확인
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "redis_connected": redis_ok,
    }


# ============================================================
# 전역 예외 핸들러
# ============================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    처리되지 않은 예외를 500 응답으로 변환.
    운영 환경에서는 상세 오류를 노출하지 않는다.
    """
    if settings.DEBUG:
        detail = str(exc)
    else:
        detail = "서버 내부 오류가 발생했습니다."
    return JSONResponse(status_code=500, content={"detail": detail})


# ============================================================
# 개발 서버 실행 (직접 실행 시)
# ============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 개발 시 핫 리로드 활성화
    )
