"""End-to-End tests for GET /api/v1/health endpoint (TASK-1.4)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a TestClient with a fresh instance of the application."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint_returns_200_and_healthy_status(client: TestClient) -> None:
    """AC: GET /api/v1/health responds with 200 OK, status: 'healthy', and uptime."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert payload["success"] is True

    # Check top-level or data-level status
    assert payload["status"] == "healthy"
    assert payload["data"]["status"] == "healthy"

    # Check uptime
    assert "uptime" in payload
    assert isinstance(payload["uptime"], (int, float))
    assert payload["uptime"] >= 0.0

    assert "uptime_seconds" in payload["data"]
    assert isinstance(payload["data"]["uptime_seconds"], (int, float))
    assert payload["data"]["uptime_seconds"] >= 0.0

    # Check upstream_status
    assert "upstream_status" in payload["data"]
    upstream = payload["data"]["upstream_status"]
    assert isinstance(upstream, dict)
    assert "if_v3" in upstream
    assert "if_v2" in upstream
    assert "crew_center" in upstream
    assert "database" in upstream


def test_health_endpoint_no_authentication_required(client: TestClient) -> None:
    """AC: GET /api/v1/health requires no Authorization header."""
    # Ensure request explicitly passes no Authorization header
    response = client.get("/api/v1/health", headers={})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_health_endpoint_with_auth_header_still_succeeds(client: TestClient) -> None:
    """Health endpoint remains accessible even if a caller supplies auth headers."""
    response = client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer any_token_string"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_endpoint_includes_meta_envelope(client: TestClient) -> None:
    """Verify health endpoint includes request_id and timestamp in meta."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert "meta" in payload
    meta = payload["meta"]
    assert "timestamp" in meta
    assert "request_id" in meta
    assert meta["request_id"].startswith("req_")

    # X-Request-ID header should match meta
    assert response.headers.get("X-Request-ID") == meta["request_id"]
