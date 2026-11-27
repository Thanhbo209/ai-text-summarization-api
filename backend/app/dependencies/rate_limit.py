import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.redis import REDIS_TRANSIENT_ERRORS
from app.dependencies.auth import verify_api_key
from app.dependencies.redis import get_redis_client

_RATE_LIMIT_LUA = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("EXPIRE", KEYS[1], tonumber(ARGV[1]))
end
local ttl = redis.call("TTL", KEYS[1])
return {current, ttl}
"""


def _build_rate_limit_key(prefix: str, api_key: str) -> str:
    key_digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{key_digest}"


class RateLimiter:
    """Fixed-window Redis rate limiter backed by an atomic Lua script."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
        key_prefix: str | None = None,
    ) -> None:
        if max_requests is not None and max_requests < 1:
            raise ValueError("max_requests must be at least 1.")
        if window_seconds is not None and window_seconds < 1:
            raise ValueError("window_seconds must be at least 1.")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    async def __call__(
        self,
        request: Request,
        api_key: Annotated[str, Depends(verify_api_key)],
        redis_client: Annotated[Redis, Depends(get_redis_client)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        limit = self.max_requests if self.max_requests is not None else settings.rate_limit_requests
        window = (
            self.window_seconds
            if self.window_seconds is not None
            else settings.rate_limit_window_seconds
        )
        prefix = self.key_prefix if self.key_prefix is not None else settings.rate_limit_key_prefix

        key = _build_rate_limit_key(prefix, api_key)

        try:
            script = redis_client.register_script(_RATE_LIMIT_LUA)
            current, ttl = await script(
                keys=[key],
                args=[window],
            )
        except REDIS_TRANSIENT_ERRORS as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiter storage is temporarily unavailable.",
            ) from exc

        count = int(current)
        ttl_seconds = int(ttl)
        retry_after = ttl_seconds if ttl_seconds > 0 else window

        request.state.rate_limit = {
            "limit": limit,
            "remaining": max(0, limit - count),
            "reset_after": retry_after,
        }

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({limit} requests per {window}s).",
                headers={"Retry-After": str(retry_after)},
            )


def rate_limit(
    max_requests: int | None = None,
    window_seconds: int | None = None,
    key_prefix: str | None = None,
) -> RateLimiter:
    """Return a FastAPI dependency reading limits dynamically from Settings unless overridden."""
    return RateLimiter(
        max_requests=max_requests,
        window_seconds=window_seconds,
        key_prefix=key_prefix,
    )
