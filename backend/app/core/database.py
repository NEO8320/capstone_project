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
    """
    async with engine.begin() as conn:
        # pgvector 확장팩 활성화 (CREATE EXTENSION IF NOT EXISTS vector)
        await conn.execute(
            __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
        )
        await conn.run_sync(Base.metadata.create_all)
