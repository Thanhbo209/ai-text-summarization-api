from fastapi.testclient import TestClient

from app.main import app
from app.schemas.summarize import SummarizeResponse

client = TestClient(app)

def test_valid_request_with_all_fields():
    response = client.post("/summarize", 
        json={
            "text": "FastAPI makes building APIs fast and clean.",
            "length": "short",
            "style": "bullet_points"
        }
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
        json={"text": "Hello World!"}
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
        json={"length": "short", "style": "paragraph"}
    )

    assert response.status_code == 422

def test_empty_text():
    response = client.post(
        "/summarize", 
        json={"text": "", "length": "short", "style": "paragraph"}
    )

    assert response.status_code == 422

def test_whitespace_only_text():
    response = client.post(
        "/summarize", 
        json={"text": "\n\t"}
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