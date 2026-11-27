import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.dependencies.redis import get_redis_client
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

EXPECTED_API_KEY = "super-secret-test-key-123"
HEADER_NAME = "X-API-KEY"


class _AllowAllScript:
    async def __call__(self, keys: list[str], args: list[object]) -> list[int]:
        return [1, 60]


class _FakeRedisClient:
    def register_script(self, script: str) -> _AllowAllScript:
        return _AllowAllScript()


def _override_settings() -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="dummy-gemini-key-for-testing",
        gemini_model="gemini-3.5-flash-lite",
        gemini_api_base_url="https://generativelanguage.googleapis.com/v1beta",
        llm_timeout_seconds=5.0,
        api_key=EXPECTED_API_KEY,
    )


def _patch_summarization_service(
    monkeypatch: pytest.MonkeyPatch,
    mock_fn: AsyncMock,
) -> None:
    """Patch summarize_text_with_gemini across service and any loaded app route module."""
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        if module_name == "app.services.summarization" or module_name.startswith("app."):  # noqa: SIM102
            if hasattr(module, "summarize_text_with_gemini"):
                monkeypatch.setattr(module, "summarize_text_with_gemini", mock_fn)


@pytest.fixture
def auth_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, AsyncMock]]:
    """Provide a TestClient with overridden settings, Redis, and mocked summarization service."""
    mock_summarize = AsyncMock(return_value="Mocked summary response.")
    fake_redis = _FakeRedisClient()
    _patch_summarization_service(monkeypatch, mock_summarize)

    app.dependency_overrides[get_settings] = _override_settings
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    client = TestClient(app)

    try:
        yield client, mock_summarize
    finally:
        app.dependency_overrides.clear()


def test_missing_api_key_returns_401_and_does_not_call_service(
    auth_client: tuple[TestClient, AsyncMock],
):
    client, mock_summarize = auth_client

    response = client.post(
        "/summarize",
        json={"text": "Summarize this paragraph."},
    )

    assert response.status_code == 401
    mock_summarize.assert_not_awaited()


def test_blank_api_key_returns_401_and_does_not_call_service(
    auth_client: tuple[TestClient, AsyncMock],
):
    client, mock_summarize = auth_client

    response = client.post(
        "/summarize",
        json={"text": "Summarize this paragraph."},
        headers={HEADER_NAME: "   "},
    )

    assert response.status_code == 401
    mock_summarize.assert_not_awaited()


def test_incorrect_api_key_returns_403_and_does_not_call_service(
    auth_client: tuple[TestClient, AsyncMock],
):
    client, mock_summarize = auth_client

    response = client.post(
        "/summarize",
        json={"text": "Summarize this paragraph."},
        headers={HEADER_NAME: "wrong-key"},
    )

    assert response.status_code == 403
    mock_summarize.assert_not_awaited()


def test_valid_api_key_succeeds_and_invokes_service(
    auth_client: tuple[TestClient, AsyncMock],
):
    client, mock_summarize = auth_client

    response = client.post(
        "/summarize",
        json={"text": "Summarize this paragraph."},
        headers={HEADER_NAME: EXPECTED_API_KEY},
    )

    assert response.status_code == 200
    assert response.json() == {"summary": "Mocked summary response."}
    mock_summarize.assert_awaited_once()


def test_health_endpoint_accessible_without_api_key(
    auth_client: tuple[TestClient, AsyncMock],
):
    client, mock_summarize = auth_client

    response = client.get("/health")

    assert response.status_code == 200
    mock_summarize.assert_not_awaited()