"""End-to-End tests for GET /api/v1/health endpoint using httpx.AsyncClient (TASK-1.5)."""

from datetime import datetime

import pytest
from httpx import AsyncClient

from app.models.health import HealthData, HealthResponse, ResponseMeta, UpstreamStatus


@pytest.mark.asyncio
async def test_health_endpoint_returns_200_and_healthy_status(
    async_client: AsyncClient,
) -> None:
    """AC: GET /api/v1/health responds with 200 OK, status: 'healthy', and uptime."""
    response = await async_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    payload = response.json()
    assert payload["success"] is True

    # Validate against strict Pydantic model schema
    validated = HealthResponse.model_validate(payload)
    assert validated.success is True
    assert validated.status == "healthy"
    assert validated.uptime >= 0.0

    # Check data payload fields
    assert isinstance(validated.data, HealthData)
    assert validated.data.status == "healthy"
    assert validated.data.uptime >= 0.0
    assert validated.data.uptime_seconds >= 0.0

    # Check upstream connectivity diagnostics
    assert isinstance(validated.data.upstream_status, UpstreamStatus)
    assert validated.data.upstream_status.if_v3 == "connected"
    assert validated.data.upstream_status.if_v2 == "connected"
    assert validated.data.upstream_status.crew_center == "connected"
    assert validated.data.upstream_status.database == "connected"


@pytest.mark.asyncio
async def test_health_endpoint_no_authentication_required(
    async_client: AsyncClient,
) -> None:
    """AC: GET /api/v1/health requires no Authorization header."""
    # Ensure request explicitly passes no Authorization header
    response = await async_client.get("/api/v1/health", headers={})
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_endpoint_with_auth_header_still_succeeds(
    async_client: AsyncClient,
) -> None:
    """Health endpoint remains accessible even if a caller supplies auth headers."""
    response = await async_client.get(
        "/api/v1/health",
        headers={"Authorization": "Bearer any_token_string"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_endpoint_with_invalid_auth_header_still_succeeds(
    async_client: AsyncClient,
) -> None:
    """Health endpoint remains completely open and accessible even with malformed or invalid auth."""
    response = await async_client.get(
        "/api/v1/health",
        headers={"Authorization": "MalformedNonBearerScheme"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_endpoint_includes_meta_envelope(
    async_client: AsyncClient,
) -> None:
    """Verify health endpoint includes request_id and timestamp in meta envelope."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    payload = response.json()
    assert "meta" in payload
    meta_dict = payload["meta"]

    validated_meta = ResponseMeta.model_validate(meta_dict)
    assert validated_meta.request_id.startswith("req_")
    assert validated_meta.cached is False

    # Timestamp must be valid UTC ISO 8601 ending in Z
    assert validated_meta.timestamp.endswith("Z")
    parsed_dt = datetime.fromisoformat(validated_meta.timestamp.replace("Z", "+00:00"))
    assert parsed_dt is not None

    # X-Request-ID response header must match meta.request_id
    assert response.headers.get("X-Request-ID") == validated_meta.request_id


@pytest.mark.asyncio
async def test_health_endpoint_custom_request_id_propagation(
    async_client: AsyncClient,
) -> None:
    """Verify incoming X-Request-ID is propagated through the meta envelope."""
    custom_id = "req_custom_trace_9876543210"
    response = await async_client.get(
        "/api/v1/health",
        headers={"X-Request-ID": custom_id},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["request_id"] == custom_id
    assert response.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_health_endpoint_disallows_invalid_methods(
    async_client: AsyncClient,
) -> None:
    """Verify POST, PUT, DELETE on /api/v1/health return 405 Method Not Allowed."""
    post_res = await async_client.post("/api/v1/health", json={"data": "test"})
    assert post_res.status_code == 405
    post_payload = post_res.json()
    assert post_payload["success"] is False
    assert post_payload["error"]["code"] == "METHOD_NOT_ALLOWED"

    put_res = await async_client.put("/api/v1/health")
    assert put_res.status_code == 405

    delete_res = await async_client.delete("/api/v1/health")
    assert delete_res.status_code == 405
