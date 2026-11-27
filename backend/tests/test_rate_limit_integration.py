import asyncio
import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import Header, HTTPException, status
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.redis import RedisConnectionManager
from app.dependencies import auth as auth_dep
from app.dependencies.redis import get_redis_client
from app.main import app

TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/1")
VALID_API_KEY_A = os.getenv("TEST_API_KEY", "test-api-key-alpha")
VALID_API_KEY_B = "test-api-key-beta"
INVALID_API_KEY = "invalid-api-key-999"

SUMMARIZE_PAYLOAD = {
    "text": "FastAPI and Redis support low-latency asynchronous summarization.",
    "length": "medium",
    "style": "paragraph",
}


async def _purge_prefix(redis_client: Redis, prefix: str) -> None:
    keys = [key async for key in redis_client.scan_iter(match=f"{prefix}:*")]
    if keys:
        await redis_client.delete(*keys)


def _locate_summarizer_target(fastapi_app) -> tuple[object, str] | None:
    """Locate the summarization callable on the /summarize route for call-count assertions."""
    for route in fastapi_app.routes:
        if getattr(route, "path", None) == "/summarize" and "POST" in getattr(
            route, "methods", set()
        ):
            endpoint = route.endpoint
            module_name = getattr(endpoint, "__module__", None)
            if module_name:
                import sys

                module = sys.modules.get(module_name)
                if module is not None:
                    for attr_name in ("summarize_text_service", "summarize_service", "generate_summary"):
                        if hasattr(module, attr_name):
                            return module, attr_name
    return None


@pytest_asyncio.fixture
async def rate_limited_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, Redis, AsyncMock]]:
    prefix = f"test_rl_{os.getpid()}_{id(monkeypatch)}"
    base_settings = get_settings()
    test_settings = base_settings.model_copy(
        update={
            "api_key": VALID_API_KEY_A,
            "redis_url": TEST_REDIS_URL,
            "rate_limit_requests": 3,
            "rate_limit_window_seconds": 2,
            "rate_limit_key_prefix": prefix,
        }
    )

    manager = RedisConnectionManager(test_settings)
    await manager.startup(fail_on_error=True)

    async def _override_verify_api_key(
        x_api_key: str | None = Header(default=None, alias="X-API-KEY"),
    ) -> str:
        if x_api_key not in {VALID_API_KEY_A, VALID_API_KEY_B}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key.",
            )
        return x_api_key

    app.dependency_overrides[auth_dep.verify_api_key] = _override_verify_api_key
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_redis_client] = lambda: manager.client

    gemini_spy = AsyncMock(return_value="Mocked summary for rate-limit testing.")
    monkeypatch.setattr("app.services.summarization.summarize_text_with_gemini", gemini_spy)
    monkeypatch.setattr("app.main.summarize_text_with_gemini", gemini_spy)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            await _purge_prefix(manager.client, prefix)
            yield client, manager.client, gemini_spy
            await _purge_prefix(manager.client, prefix)
    finally:
        app.dependency_overrides.clear()
        await manager.shutdown()


@pytest.mark.asyncio
async def test_first_within_at_limit_and_exceeding_returns_429(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, _, _ = rate_limited_client
    headers = {"X-API-KEY": VALID_API_KEY_A}

    # 1. First request -> Allowed
    r1 = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert r1.status_code == 200

    # 2. Request within limit (2nd of 3) -> Allowed
    r2 = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert r2.status_code == 200

    # 3. Request exactly at limit (3rd of 3) -> Allowed
    r3 = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert r3.status_code == 200

    # 4. Request exceeding limit (4th of 3) -> 429
    r4 = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers


@pytest.mark.asyncio
async def test_counter_expiration_allows_requests_after_window(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, _, _ = rate_limited_client
    headers = {"X-API-KEY": VALID_API_KEY_A}

    for _ in range(3):
        resp = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
        assert resp.status_code == 200

    exceeded = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert exceeded.status_code == 429

    # Configured test window is 2 seconds; wait slightly past expiration
    await asyncio.sleep(2.2)

    after_expiry = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert after_expiry.status_code == 200


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401_without_consuming_quota(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, redis_client, _ = rate_limited_client
    invalid_headers = {"X-API-KEY": INVALID_API_KEY}

    for _ in range(5):
        resp = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=invalid_headers)
        assert resp.status_code == 401

    # Ensure no rate-limit counter keys were created for the rejected key
    remaining_keys = [
        key async for key in redis_client.scan_iter(match="test_rl_*")
    ]
    assert remaining_keys == []


@pytest.mark.asyncio
async def test_exceeded_quota_does_not_invoke_summarization_service(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, _, service_spy = rate_limited_client
    headers = {"X-API-KEY": VALID_API_KEY_A}

    for _ in range(3):
        resp = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
        assert resp.status_code == 200

    calls_before_429 = service_spy.await_count if service_spy is not None else None

    blocked = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
    assert blocked.status_code == 429

    if service_spy is not None and calls_before_429 is not None:
        assert service_spy.await_count == calls_before_429


@pytest.mark.asyncio
async def test_health_endpoint_is_not_rate_limited(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, _, _ = rate_limited_client

    for _ in range(10):
        resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_independent_keys_have_independent_counters(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, _, _ = rate_limited_client
    headers_a = {"X-API-KEY": VALID_API_KEY_A}
    headers_b = {"X-API-KEY": VALID_API_KEY_B}

    # Exhaust quota for key A (limit = 3)
    for _ in range(3):
        assert (await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers_a)).status_code == 200
    assert (await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers_a)).status_code == 429

    # Key B still has its own full quota
    for _ in range(3):
        resp_b = await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers_b)
        assert resp_b.status_code == 200
    assert (await client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers_b)).status_code == 429


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_exceed_limit(
    rate_limited_client: tuple[AsyncClient, Redis, AsyncMock | None],
) -> None:
    client, _, _ = rate_limited_client
    headers = {"X-API-KEY": VALID_API_KEY_A}

    # Limit is 3; fire 10 requests concurrently
    responses = await asyncio.gather(
        *(
            client.post("/summarize", json=SUMMARIZE_PAYLOAD, headers=headers)
            for _ in range(10)
        )
    )

    allowed_count = sum(1 for r in responses if r.status_code == 200)
    throttled_count = sum(1 for r in responses if r.status_code == 429)

    assert allowed_count == 3
    assert throttled_count == 7
    assert all(r.status_code in {200, 429} for r in responses)