import logging
from typing import Final

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.config import Settings

logger = logging.getLogger(__name__)

REDIS_TRANSIENT_ERRORS: Final[tuple[type[BaseException], ...]] = (
    RedisConnectionError,
    RedisTimeoutError,
    RedisError,
    OSError,
    TimeoutError,
)


class RedisUnavailableError(RuntimeError):
    """Raised when Redis is uninitialized or unreachable."""


class RedisConnectionManager:
    """Manages a single async Redis client and its underlying connection pool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Redis | None = None

    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RedisUnavailableError("Redis client has not been initialized.")
        return self._client

    async def startup(self, *, fail_on_error: bool = False) -> None:
        """Create the async Redis client and verify connectivity."""
        if self._client is not None:
            return

        client = Redis.from_url(
            self._settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=self._settings.redis_max_connections,
            socket_connect_timeout=self._settings.redis_socket_connect_timeout,
            socket_timeout=self._settings.redis_socket_timeout,
            health_check_interval=30,
        )

        try:
            await client.ping()
            self._client = client
            logger.info("Connected to Redis successfully.")
        except REDIS_TRANSIENT_ERRORS as exc:
            await client.aclose()
            logger.warning("Redis unavailable during startup: %s", exc)
            if fail_on_error:
                raise RedisUnavailableError("Failed to connect to Redis on startup.") from exc

    async def shutdown(self) -> None:
        """Close the Redis client and release pooled connections."""
        if self._client is None:
            return

        client = self._client
        self._client = None
        try:
            await client.aclose()
            logger.info("Redis connection pool closed.")
        except REDIS_TRANSIENT_ERRORS as exc:
            logger.warning("Error while closing Redis client: %s", exc)

    async def is_healthy(self) -> bool:
        """Check live Redis connectivity without raising on transient outages."""
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except REDIS_TRANSIENT_ERRORS:
            return False