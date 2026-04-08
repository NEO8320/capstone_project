"""
Redis 클라이언트 관리 모듈
===========================

순환 임포트를 방지하기 위해 main.py에서 분리된 Redis 싱글턴.
lifespan에서 초기화되고, API 라우터에서 Depends()로 주입된다.
"""

import redis.asyncio as aioredis

# 전역 Redis 클라이언트 (lifespan에서 초기화)
redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """
    FastAPI Depends()를 통해 Redis 클라이언트를 주입한다.

    Raises:
        RuntimeError: Redis가 초기화되지 않았거나 연결 실패 시
    """
    if redis_client is None:
        raise RuntimeError("Redis 연결이 초기화되지 않았습니다.")
    return redis_client
