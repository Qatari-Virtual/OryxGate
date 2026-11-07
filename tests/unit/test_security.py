"""Unit tests for Gateway Bearer Authentication and Security Dependencies (TASK-1.3)."""

import contextlib
import time
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.security import (
    CallerContext,
    get_current_token,
    require_admin,
    require_scope,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Provide a mock Settings instance with known gateway and admin tokens."""
    settings = MagicMock(spec=Settings)
    settings.raw_gateway_api_tokens = ["gateway_token_1", "gateway_token_2"]
    settings.raw_admin_api_tokens = ["admin_token_1"]
    return settings


@pytest.fixture
def app(mock_settings: MagicMock) -> FastAPI:
    """Create a test FastAPI application with protected endpoints."""
    test_app = FastAPI()

    async def get_test_settings() -> Settings:
        return mock_settings

    write_checker = require_scope("write")
    custom_checker = require_scope("custom_scope")

    @test_app.get("/test/protected")
    async def protected_endpoint(
        caller: Annotated[CallerContext, Depends(get_current_token)],
    ) -> dict[str, Any]:
        return {
            "authenticated": True,
            "scopes": sorted(list(caller.scopes)),
            "is_admin": caller.is_admin,
        }

    @test_app.get("/test/admin")
    async def admin_endpoint(
        caller: Annotated[CallerContext, Depends(require_admin)],
    ) -> dict[str, Any]:
        return {
            "admin": True,
            "scopes": sorted(list(caller.scopes)),
        }

    @test_app.get("/test/write-only")
    async def write_endpoint(
        caller: Annotated[CallerContext, Depends(write_checker)],
    ) -> dict[str, Any]:
        return {"scope": "write"}

    @test_app.get("/test/super-custom")
    async def custom_endpoint(
        caller: Annotated[CallerContext, Depends(custom_checker)],
    ) -> dict[str, Any]:
        return {"scope": "custom_scope"}

    # Override the settings dependency
    from app.config import get_settings

    test_app.dependency_overrides[get_settings] = get_test_settings

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Provide a TestClient for making requests to the test FastAPI app."""
    return TestClient(app)


# =========================================================================
# Acceptance Criteria 1: Valid token returns caller context with scopes
# =========================================================================


@pytest.mark.asyncio
async def test_valid_standard_gateway_token_returns_caller_context(
    mock_settings: MagicMock,
) -> None:
    """AC: Valid standard token returns caller context with read & write scopes."""
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="gateway_token_1"
    )
    caller = await get_current_token(credentials=credentials, settings=mock_settings)

    assert isinstance(caller, CallerContext)
    assert caller.scopes == {"read", "write"}
    assert caller.is_admin is False
    assert caller.has_scope("read") is True
    assert caller.has_scope("write") is True
    assert caller.has_scope("admin") is False


@pytest.mark.asyncio
async def test_valid_admin_token_returns_caller_context_with_admin_scope(
    mock_settings: MagicMock,
) -> None:
    """AC: Valid admin token returns caller context with read, write, and admin scopes."""
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="admin_token_1"
    )
    caller = await get_current_token(credentials=credentials, settings=mock_settings)

    assert isinstance(caller, CallerContext)
    assert caller.scopes == {"read", "write", "admin"}
    assert caller.is_admin is True
    assert caller.has_scope("read") is True
    assert caller.has_scope("write") is True
    assert caller.has_scope("admin") is True


@pytest.mark.asyncio
async def test_token_in_both_gateway_and_admin_gets_all_scopes(
    mock_settings: MagicMock,
) -> None:
    """Verify that a token configured as both gateway and admin receives union of scopes."""
    mock_settings.raw_gateway_api_tokens = ["dual_token"]
    mock_settings.raw_admin_api_tokens = ["dual_token"]

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="dual_token"
    )
    caller = await get_current_token(credentials=credentials, settings=mock_settings)

    assert caller.scopes == {"read", "write", "admin"}
    assert caller.is_admin is True


def test_http_endpoint_with_valid_gateway_token(client: TestClient) -> None:
    """Verify HTTP GET /test/protected succeeds with 200 OK for valid gateway token."""
    response = client.get(
        "/test/protected",
        headers={"Authorization": "Bearer gateway_token_1"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["authenticated"] is True
    assert data["scopes"] == ["read", "write"]
    assert data["is_admin"] is False


def test_http_endpoint_with_valid_admin_token(client: TestClient) -> None:
    """Verify HTTP GET /test/protected succeeds with 200 OK for valid admin token."""
    response = client.get(
        "/test/protected",
        headers={"Authorization": "Bearer admin_token_1"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["authenticated"] is True
    assert data["scopes"] == ["admin", "read", "write"]
    assert data["is_admin"] is True


# =========================================================================
# Acceptance Criteria 2: Missing header returns 401 Unauthorized
# =========================================================================


@pytest.mark.asyncio
async def test_missing_credentials_raises_401(mock_settings: MagicMock) -> None:
    """AC: Missing header raises 401 with WWW-Authenticate header."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_token(credentials=None, settings=mock_settings)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers is not None
    assert "WWW-Authenticate" in exc_info.value.headers
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


def test_http_request_missing_auth_header_returns_401(client: TestClient) -> None:
    """AC: Missing header returns 401 Unauthorized via HTTP test client."""
    response = client.get("/test/protected")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_http_request_non_bearer_scheme_returns_401(client: TestClient) -> None:
    """AC: Non-Bearer scheme (e.g. Basic) returns 401 Unauthorized."""
    response = client.get(
        "/test/protected",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_http_request_empty_bearer_returns_401(client: TestClient) -> None:
    """AC: Bearer header with empty or whitespace-only token returns 401 Unauthorized."""
    response = client.get(
        "/test/protected",
        headers={"Authorization": "Bearer "},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers.get("WWW-Authenticate") == "Bearer"


# =========================================================================
# Acceptance Criteria 3: Invalid token returns 401 Unauthorized in < 1ms
# =========================================================================


@pytest.mark.asyncio
async def test_invalid_token_raises_401(mock_settings: MagicMock) -> None:
    """AC: Invalid token raises 401 Unauthorized with WWW-Authenticate."""
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="completely_invalid_token"
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_token(credentials=credentials, settings=mock_settings)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"


def test_http_request_invalid_token_returns_401(client: TestClient) -> None:
    """AC: Invalid token returns 401 Unauthorized via HTTP test client."""
    response = client.get(
        "/test/protected",
        headers={"Authorization": "Bearer fake_token_9999"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_invalid_token_verification_latency_under_1ms(
    mock_settings: MagicMock,
) -> None:
    """AC: Invalid token returns 401 Unauthorized in < 1ms."""
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="invalid_timing_test_token"
    )

    # Warmup
    with contextlib.suppress(HTTPException):
        await get_current_token(credentials=credentials, settings=mock_settings)

    # Measure 100 consecutive invocations
    durations: list[float] = []
    for _ in range(100):
        start = time.perf_counter()
        with contextlib.suppress(HTTPException):
            await get_current_token(credentials=credentials, settings=mock_settings)
        duration_ms = (time.perf_counter() - start) * 1000.0
        durations.append(duration_ms)

    avg_ms = sum(durations) / len(durations)
    max_ms = max(durations)

    # Both average and worst-case should comfortably be under 1ms (typically < 0.05ms)
    assert avg_ms < 1.0, f"Average invalid token verification too slow: {avg_ms:.4f}ms"
    assert max_ms < 1.0, f"Max invalid token verification exceeded 1ms: {max_ms:.4f}ms"


# =========================================================================
# Acceptance Criteria 4: Non-admin token attempting admin dependency returns 403
# =========================================================================


@pytest.mark.asyncio
async def test_non_admin_token_attempting_require_admin_raises_403() -> None:
    """AC: Non-admin token attempting admin-scoped dependency returns 403 Forbidden."""
    caller = CallerContext(token="gateway_token_1", scopes={"read", "write"})

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(caller=caller)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "admin" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_admin_token_attempting_require_admin_succeeds() -> None:
    """Admin token passes require_admin without error."""
    caller = CallerContext(token="admin_token_1", scopes={"read", "write", "admin"})
    result = await require_admin(caller=caller)
    assert result is caller


def test_http_non_admin_token_attempting_admin_endpoint_returns_403(
    client: TestClient,
) -> None:
    """AC: HTTP non-admin token attempting admin endpoint returns 403 Forbidden."""
    response = client.get(
        "/test/admin",
        headers={"Authorization": "Bearer gateway_token_1"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_http_admin_token_attempting_admin_endpoint_returns_200(
    client: TestClient,
) -> None:
    """HTTP admin token attempting admin endpoint returns 200 OK."""
    response = client.get(
        "/test/admin",
        headers={"Authorization": "Bearer admin_token_1"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["admin"] is True


# =========================================================================
# Additional Scopes & Security Guarantees
# =========================================================================


@pytest.mark.asyncio
async def test_require_scope_dependency() -> None:
    """Verify require_scope grants access when scope is present and denies when missing."""
    caller = CallerContext(token="test_tok", scopes={"read", "write"})

    # Check existing scope passes
    checker = require_scope("write")
    res = await checker(caller)
    assert res is caller

    # Check missing scope raises 403
    admin_checker = require_scope("admin")
    with pytest.raises(HTTPException) as exc_info:
        await admin_checker(caller)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_http_require_scope_enforcement(client: TestClient) -> None:
    """Verify arbitrary scope enforcement through test endpoints."""
    # /test/write-only with gateway token (has write) -> 200
    res1 = client.get(
        "/test/write-only",
        headers={"Authorization": "Bearer gateway_token_1"},
    )
    assert res1.status_code == status.HTTP_200_OK

    # /test/super-custom with gateway token (lacks custom_scope) -> 403
    res2 = client.get(
        "/test/super-custom",
        headers={"Authorization": "Bearer gateway_token_1"},
    )
    assert res2.status_code == status.HTTP_403_FORBIDDEN


def test_caller_context_masks_token_in_string_representations() -> None:
    """Verify CallerContext does not leak raw tokens when printed or represented."""
    raw_token = "ultra_secret_bearer_token_xyz"
    caller = CallerContext(token=raw_token, scopes={"read", "write"})

    assert raw_token not in repr(caller)
    assert raw_token not in str(caller)
