from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.dependencies.auth import verify_api_key
from app.dependencies.redis import get_redis_client
from app.main import app


class _AllowAllScript:
    async def __call__(self, keys: list[str], args: list[object]) -> list[int]:
        return [1, 60]


class _FakeRedis:
    def register_script(self, script: str) -> _AllowAllScript:
        return _AllowAllScript()


@pytest.fixture(autouse=True)
def _bypass_dependencies() -> Generator[None]:
    fake_redis = _FakeRedis()
    app.dependency_overrides[verify_api_key] = lambda: "test-api-key"
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    try:
        yield
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_redis_client, None)


client = TestClient(app)


def test_valid_request_with_all_fields():
    response = client.post(
        "/summarize",
        json={
            "text": "FastAPI makes building APIs fast and clean.",
            "length": "short",
            "style": "bullet_points",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, dict)
    assert "summary" in result
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 0


def test_valid_request_with_default_fields():
    response = client.post(
        "/summarize",
        json={"text": "Hello World!"},
    )

    assert response.status_code == 200
    result = response.json()
    assert isinstance(result, dict)
    assert "summary" in result
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 0


def test_missing_text():
    response = client.post(
        "/summarize",
        json={"length": "short", "style": "paragraph"},
    )

    assert response.status_code == 422


def test_empty_text():
    response = client.post(
        "/summarize",
        json={"text": "", "length": "short", "style": "paragraph"},
    )

    assert response.status_code == 422


def test_whitespace_only_text():
    response = client.post(
        "/summarize",
        json={"text": "\n\t"},
    )

    assert response.status_code == 422


def test_invalid_style():
    response = client.post(
        "/summarize",
        json={"text": "Valid text", "style": "haiku"},
    )

    assert response.status_code == 422


def test_wrong_type_for_text():
    response = client.post(
        "/summarize",
        json={"text": ["not", "a", "string"]},
    )

    assert response.status_code == 422