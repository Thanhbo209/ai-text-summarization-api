import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services import summarization as summarization_module
from app.services.summarization import (
    SummarizationConnectionError,
    SummarizationProviderError,
    SummarizationResponseError,
    SummarizationTimeoutError,
    summarize_text_with_gemini,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

def _make_test_settings() -> Settings:
    return Settings(
        _env_file=None,  # Prevent reading any local .env file during tests
        gemini_api_key="test-dummy-key-not-real",
        gemini_model="gemini-3.5-flash-lite",
        gemini_api_base_url="https://generativelanguage.googleapis.com/v1beta",
        llm_timeout_seconds=5.0,
        api_key="test-client-api-key",
    )


def _patch_httpx_async_client(
    monkeypatch: pytest.MonkeyPatch,
    handler,
) -> None:
    """Replace httpx.AsyncClient so any instance created by the service uses MockTransport."""
    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    class MockedAsyncClient(original_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", MockedAsyncClient)
    monkeypatch.setattr(summarization_module.httpx, "AsyncClient", MockedAsyncClient)


# ---------------------------------------------------------------------------
# Service-Level Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_provider_success():
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "  Concise summary output.  "}]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    settings = _make_test_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        summary = await summarize_text_with_gemini(
            text="FastAPI and Pydantic v2 help build well-validated APIs.",
            length="short",
            style="bullet_points",
            settings=settings,
            client=client,
        )

    assert summary == "Concise summary output."
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.headers.get("x-goog-api-key") == "test-dummy-key-not-real"
    assert str(req.url).endswith("/models/gemini-3.5-flash-lite:generateContent")


@pytest.mark.asyncio
async def test_service_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated read timeout", request=request)

    settings = _make_test_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummarizationTimeoutError):
            await summarize_text_with_gemini(
                text="Some input text to summarize.",
                settings=settings,
                client=client,
            )


@pytest.mark.asyncio
async def test_service_connection_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Simulated DNS/connection failure", request=request)

    settings = _make_test_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummarizationConnectionError):
            await summarize_text_with_gemini(
                text="Some input text to summarize.",
                settings=settings,
                client=client,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_is_client_error"),
    [
        (400, True),
        (401, True),
        (429, True),
        (500, False),
        (503, False),
    ],
)
async def test_service_provider_http_errors(
    status_code: int,
    expected_is_client_error: bool,
):
    secret_leak_marker = "RAW_PROVIDER_SECRET_DETAIL"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json={"error": {"code": status_code, "message": secret_leak_marker}},
        )

    settings = _make_test_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummarizationProviderError) as exc_info:
            await summarize_text_with_gemini(
                text="Some input text to summarize.",
                settings=settings,
                client=client,
            )

    assert exc_info.value.status_code == status_code
    assert exc_info.value.is_client_error is expected_is_client_error
    assert secret_leak_marker not in str(exc_info.value)


@pytest.mark.asyncio
async def test_service_malformed_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"{not-valid-json",
            headers={"Content-Type": "application/json"},
        )

    settings = _make_test_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummarizationResponseError):
            await summarize_text_with_gemini(
                text="Some input text to summarize.",
                settings=settings,
                client=client,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_payload",
    [
        {},
        {"candidates": []},
        {"candidates": [{"content": {}}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]},
        {"candidates": [{"content": {"parts": [{"text": "   "}]}}]},
    ],
)
async def test_service_unexpected_response_structure(bad_payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=bad_payload)

    settings = _make_test_settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SummarizationResponseError):
            await summarize_text_with_gemini(
                text="Some input text to summarize.",
                settings=settings,
                client=client,
            )


# ---------------------------------------------------------------------------
# Route-Level Integration Tests
# ---------------------------------------------------------------------------


def test_route_integration_success(monkeypatch: pytest.MonkeyPatch):
    test_settings = _make_test_settings()
    app.dependency_overrides[get_settings] = lambda: test_settings

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Route-level mocked summary."}]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    _patch_httpx_async_client(monkeypatch, handler)

    try:
        client = TestClient(app)
        response = client.post(
            "/summarize",
            json={
                "text": "End-to-end test input for the FastAPI summarization route.",
                "length": "short",
                "style": "paragraph",
            },
            headers={"X-API-KEY": test_settings.api_key},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"summary": "Route-level mocked summary."}


def test_route_integration_maps_provider_failure_safely(monkeypatch: pytest.MonkeyPatch):
    test_settings = _make_test_settings()
    app.dependency_overrides[get_settings] = lambda: test_settings

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=503,
            json={"error": {"message": "Internal upstream failure details"}},
        )

    _patch_httpx_async_client(monkeypatch, handler)

    try:
        client = TestClient(app)
        response = client.post(
            "/summarize",
            json={"text": "Trigger upstream 503 failure through route."},
            headers={"X-API-KEY": test_settings.api_key},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    body = response.json()
    assert "detail" in body
    assert "Internal upstream failure details" not in str(body)
    assert "test-dummy-key-not-real" not in str(body)