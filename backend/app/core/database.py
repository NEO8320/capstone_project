"""
비동기 데이터베이스 세션 관리 모듈
- SQLAlchemy 2.0 비동기 엔진(asyncpg) 기반
- FastAPI의 Depends()를 통해 요청별 세션을 주입
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ── 비동기 엔진 생성 ──
# pool_size: 동시 커넥션 수, max_overflow: 초과 허용 커넥션 수
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
)

# ── 비동기 세션 팩토리 ──
# expire_on_commit=False: 커밋 후에도 객체 속성 접근 가능 (비동기 환경 필수)
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── 선언적 베이스 클래스 ──
class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """
    FastAPI 의존성 주입용 비동기 DB 세션 제너레이터.
    요청 시작 시 세션을 열고, 요청 종료 시 자동으로 닫는다.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    애플리케이션 시작 시 pgvector 확장팩을 활성화하고 테이블을 생성한다.
    운영 환경에서는 Alembic 마이그레이션을 사용할 것을 권장.

    ■ DB 연결 레이스 컨디션 방어:
      docker-compose가 postgres 컨테이너를 시작한 직후 backend가 연결을 시도하면
      컨테이너가 아직 준비되지 않아 ConnectionRefusedError가 발생할 수 있다.
      이를 방지하기 위해 지수 백오프로 최대 DB_INIT_MAX_RETRIES회 재시도한다.
      (2s → 4s → 8s → 16s → 32s = 총 최대 62초 버짓)

    최종 실패 시 RuntimeError를 올려 호출자(main.py lifespan)가 경고 로깅 후
    서버를 계속 시작하도록 한다.
    """
    import asyncio
    from sqlalchemy import text as _text
    from sqlalchemy.exc import DBAPIError, OperationalError

    max_retries = settings.DB_INIT_MAX_RETRIES
    delay = settings.DB_INIT_INITIAL_DELAY
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            async with engine.begin() as conn:
                # pgvector 확장팩 활성화 (CREATE EXTENSION IF NOT EXISTS vector)
                await conn.execute(_text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)

                # ── 신뢰도 sub-score 컬럼 멱등 추가 (기존 DB 호환) ──
                # create_all은 기존 테이블에 새 컬럼을 추가하지 않으므로
                # ALTER TABLE로 직접 추가한다. IF NOT EXISTS로 멱등성 보장.
                for col in ("rb01_tone", "rb02_density", "rb03_quotes", "rb04_journalist"):
                    await conn.execute(_text(
                        f"ALTER TABLE articles ADD COLUMN IF NOT EXISTS {col} FLOAT"
                    ))
            if attempt > 1:
                print(f"[DB] {attempt}번째 시도에서 초기화 성공")
            return
        except (OperationalError, DBAPIError, ConnectionRefusedError, OSError) as e:
            last_error = e
            if attempt < max_retries:
                print(
                    f"[DB] 초기화 실패 ({attempt}/{max_retries}) — "
                    f"{delay:.0f}초 후 재시도: {type(e).__name__}"
                )
                await asyncio.sleep(delay)
                delay *= 2  # 지수 백오프
            else:
                print(f"[DB] 초기화 {max_retries}회 모두 실패: {e}")

    # 모든 재시도 실패 — 호출자(lifespan)에서 catch하여 서버 시작 자체는 계속 진행
    raise RuntimeError(
        f"init_db: {max_retries}회 재시도 실패 — {last_error}"
    ) from last_error
