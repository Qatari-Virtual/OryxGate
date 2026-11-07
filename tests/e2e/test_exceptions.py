"""End-to-End tests for Global Exception Handlers & ORJSONResponse (TASK-1.4)."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app


@pytest.fixture
def test_app() -> FastAPI:
    """Create test application and inject deliberate fault endpoints."""
    app = create_app()

    @app.get("/test/deliberate-crash")
    async def deliberate_crash() -> dict[str, str]:
        raise RuntimeError("Simulated catastrophic crash inside route")

    @app.get("/test/deliberate-http-error")
    async def deliberate_http_error() -> dict[str, str]:
        raise HTTPException(
            status_code=404,
            detail="The requested simulated resource was not found",
        )

    @app.get("/test/deliberate-401")
    async def deliberate_401() -> dict[str, str]:
        raise HTTPException(
            status_code=401,
            detail="Custom auth failure message",
            headers={"WWW-Authenticate": "Bearer"},
        )

    class SampleInput(BaseModel):
        count: int
        name: str

    @app.post("/test/deliberate-validation")
    async def deliberate_validation(body: SampleInput) -> dict[str, str]:
        return {"received": body.name}

    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Provide a TestClient for testing exception handling."""
    return TestClient(test_app, raise_server_exceptions=False)


def test_default_response_class_is_orjson() -> None:
    """Verify application uses ORJSONResponse as default response class."""
    app = create_app()
    assert app.router.default_response_class is ORJSONResponse
    assert getattr(app, "default_response_class", None) is ORJSONResponse


def test_unhandled_exception_returns_standard_json_error_envelope(client: TestClient) -> None:
    """AC: Unhandled exceptions return standard JSON error envelopes instead of HTML tracebacks."""
    response = client.get("/test/deliberate-crash")

    # Status must be 500
    assert response.status_code == 500

    # Content-Type must be application/json, NOT text/html
    assert response.headers["content-type"].startswith("application/json")

    # Body must not contain HTML tags
    text = response.text
    assert "<html>" not in text.lower()
    assert "<traceback" not in text.lower()
    assert "Traceback (most recent call last)" not in text

    payload = response.json()
    assert payload["success"] is False
    assert "error" in payload
    assert payload["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "internal server error" in payload["error"]["message"].lower()

    # Meta must contain timestamp and request_id
    assert "meta" in payload
    assert "request_id" in payload["meta"]
    assert "timestamp" in payload["meta"]
    assert response.headers.get("X-Request-ID") == payload["meta"]["request_id"]


def test_http_exception_returns_standard_json_error_envelope(client: TestClient) -> None:
    """HTTPException returns standard JSON envelope with appropriate status and code."""
    response = client.get("/test/deliberate-http-error")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "simulated resource was not found" in payload["error"]["message"]
    assert payload["meta"]["request_id"].startswith("req_")


def test_401_http_exception_preserves_www_authenticate_header(client: TestClient) -> None:
    """401 HTTPException preserves WWW-Authenticate header alongside JSON error envelope."""
    response = client.get("/test/deliberate-401")

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert payload["error"]["message"] == "Custom auth failure message"


def test_validation_error_returns_standard_json_error_envelope(client: TestClient) -> None:
    """RequestValidationError returns 422 with structured detail in error envelope."""
    response = client.post("/test/deliberate-validation", json={"count": "not-an-int"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "detail" in payload["error"]
    assert isinstance(payload["error"]["detail"], list)
    assert len(payload["error"]["detail"]) > 0
