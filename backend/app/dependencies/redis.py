# app/dependencies/redis.py
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.redis import RedisConnectionManager, RedisUnavailableError


def get_redis_manager(request: Request) -> RedisConnectionManager:
    manager: RedisConnectionManager | None = getattr(request.app.state, "redis_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis manager is not configured.",
        )
    return manager


async def get_redis_client(
    manager: Annotated[RedisConnectionManager, Depends(get_redis_manager)],
) -> Redis:
    try:
        return manager.client
    except RedisUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis service is unavailable.",
        ) from exc
