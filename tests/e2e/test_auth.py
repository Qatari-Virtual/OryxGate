"""End-to-End tests for Gateway Bearer Authentication using httpx.AsyncClient (TASK-1.5)."""

from collections.abc import AsyncIterator
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.security import (
    CallerContext,
    get_current_token,
    require_admin,
    require_scope,
)
from app.main import create_app


@pytest.fixture
def auth_test_settings() -> Settings:
    """Provide Settings with isolated test tokens for E2E auth validation."""
    return Settings(
        gateway_api_tokens="gw_token_alpha, gw_token_beta, dual_token_gamma",
        admin_api_tokens="admin_token_master, dual_token_gamma",
        if_api_key="if_test_api_key",
        if_organization_id="e9b25123-0000-0000-0000-000000000000",
        cc_api_key="cc_test_api_key",
        cc_api_base_url="https://crew.qatarairwaysvirtual.com/api",
        db_host="127.0.0.1",
        db_user="test_user",
        db_password="test_password",
        db_name="test_db",
        _env_file=None,
    )


@pytest.fixture
async def auth_client(auth_test_settings: Settings) -> AsyncIterator[AsyncClient]:
    """Create an AsyncClient with protected test endpoints attached to the OryxGate app."""
    app = create_app(settings=auth_test_settings)

    # Attach test routes exercising security dependencies through the full gateway pipeline
    test_router = APIRouter(prefix="/api/v1/test/auth")

    custom_scope_checker = require_scope("custom_scope")
    read_scope_checker = require_scope("read")
    write_scope_checker = require_scope("write")

    @test_router.get("/standard")
    async def standard_route(
        caller: Annotated[CallerContext, Depends(get_current_token)],
    ) -> dict[str, Any]:
        return {
            "authenticated": True,
            "scopes": sorted(list(caller.scopes)),
            "is_admin": caller.is_admin,
        }

    @test_router.get("/admin-only")
    async def admin_route(
        caller: Annotated[CallerContext, Depends(require_admin)],
    ) -> dict[str, Any]:
        return {
            "admin_access": True,
            "scopes": sorted(list(caller.scopes)),
        }

    @test_router.get("/custom-scope")
    async def custom_scope_route(
        caller: Annotated[CallerContext, Depends(custom_scope_checker)],
    ) -> dict[str, Any]:
        return {"granted": True, "scope": "custom_scope"}

    @test_router.get("/read-only")
    async def read_scope_route(
        caller: Annotated[CallerContext, Depends(read_scope_checker)],
    ) -> dict[str, Any]:
        return {"granted": True, "scope": "read"}

    @test_router.get("/write-only")
    async def write_scope_route(
        caller: Annotated[CallerContext, Depends(write_scope_checker)],
    ) -> dict[str, Any]:
        return {"granted": True, "scope": "write"}

    app.include_router(test_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


# =============================================================================
# 1. Valid Token Scenarios (Happy Paths)
# =============================================================================


@pytest.mark.asyncio
async def test_valid_standard_gateway_token_returns_200(auth_client: AsyncClient) -> None:
    """AC: Valid standard gateway token returns 200 OK with read & write scopes."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer gw_token_alpha"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["scopes"] == ["read", "write"]
    assert data["is_admin"] is False


@pytest.mark.asyncio
async def test_second_valid_standard_gateway_token_returns_200(auth_client: AsyncClient) -> None:
    """AC: Multiple configured gateway tokens are independently valid."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer gw_token_beta"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["scopes"] == ["read", "write"]
    assert data["is_admin"] is False


@pytest.mark.asyncio
async def test_valid_standard_token_can_access_read_and_write_routes(
    auth_client: AsyncClient,
) -> None:
    """Standard token can access both read-only and write-only scoped routes."""
    read_res = await auth_client.get(
        "/api/v1/test/auth/read-only",
        headers={"Authorization": "Bearer gw_token_alpha"},
    )
    assert read_res.status_code == 200
    assert read_res.json()["scope"] == "read"

    write_res = await auth_client.get(
        "/api/v1/test/auth/write-only",
        headers={"Authorization": "Bearer gw_token_alpha"},
    )
    assert write_res.status_code == 200
    assert write_res.json()["scope"] == "write"


@pytest.mark.asyncio
async def test_valid_admin_token_succeeds_on_standard_and_admin_routes(
    auth_client: AsyncClient,
) -> None:
    """AC: Valid admin token accesses standard and admin-only endpoints."""
    # Standard route
    std_res = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer admin_token_master"},
    )
    assert std_res.status_code == 200
    std_data = std_res.json()
    assert std_data["is_admin"] is True
    assert std_data["scopes"] == ["admin", "read", "write"]

    # Admin-only route
    admin_res = await auth_client.get(
        "/api/v1/test/auth/admin-only",
        headers={"Authorization": "Bearer admin_token_master"},
    )
    assert admin_res.status_code == 200
    assert admin_res.json()["admin_access"] is True


@pytest.mark.asyncio
async def test_dual_configured_token_receives_union_of_scopes(auth_client: AsyncClient) -> None:
    """Token present in both gateway and admin configurations receives union of scopes."""
    response = await auth_client.get(
        "/api/v1/test/auth/admin-only",
        headers={"Authorization": "Bearer dual_token_gamma"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["admin_access"] is True
    assert data["scopes"] == ["admin", "read", "write"]


@pytest.mark.asyncio
async def test_bearer_scheme_case_insensitivity(auth_client: AsyncClient) -> None:
    """AC: Scheme name in Authorization header is case-insensitive (bearer, BEARER, Bearer)."""
    schemes = ["bearer", "BEARER", "Bearer", "bEaReR"]
    for scheme in schemes:
        response = await auth_client.get(
            "/api/v1/test/auth/standard",
            headers={"Authorization": f"{scheme} gw_token_alpha"},
        )
        assert response.status_code == 200, f"Scheme {scheme} failed"
        assert response.json()["authenticated"] is True


@pytest.mark.asyncio
async def test_valid_token_with_surrounding_whitespace_trimmed(auth_client: AsyncClient) -> None:
    """Authorization header credentials with leading/trailing whitespace are trimmed properly."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer   gw_token_alpha   "},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


# =============================================================================
# 2. Missing Token Scenarios (401 Unauthorized)
# =============================================================================


@pytest.mark.asyncio
async def test_missing_authorization_header_returns_401(auth_client: AsyncClient) -> None:
    """AC: Request lacking Authorization header returns 401 with standard error envelope."""
    response = await auth_client.get("/api/v1/test/auth/standard")

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert "missing or malformed" in payload["error"]["message"].lower()

    # Meta tracing envelope
    assert "meta" in payload
    assert payload["meta"]["request_id"].startswith("req_")
    assert payload["meta"]["timestamp"].endswith("Z")
    assert response.headers.get("X-Request-ID") == payload["meta"]["request_id"]


@pytest.mark.asyncio
async def test_empty_authorization_header_returns_401(auth_client: AsyncClient) -> None:
    """AC: Request with empty Authorization header returns 401 Unauthorized."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": ""},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"


# =============================================================================
# 3. Malformed Header Scenarios (401 Unauthorized)
# =============================================================================


@pytest.mark.asyncio
async def test_non_bearer_basic_auth_returns_401(auth_client: AsyncClient) -> None:
    """AC: Non-Bearer scheme (e.g. Basic) returns 401 with WWW-Authenticate: Bearer."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert "authorization header" in payload["error"]["message"].lower()


@pytest.mark.asyncio
async def test_non_bearer_custom_scheme_returns_401(auth_client: AsyncClient) -> None:
    """AC: Unsupported custom scheme returns 401 Unauthorized."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Token some_api_token_value"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    payload = response.json()
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert "authorization header" in payload["error"]["message"].lower()


@pytest.mark.asyncio
async def test_bearer_header_without_token_returns_401(auth_client: AsyncClient) -> None:
    """AC: 'Authorization: Bearer' with no token returns 401 Unauthorized."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert "authorization header" in payload["error"]["message"].lower()


@pytest.mark.asyncio
async def test_bearer_header_with_whitespace_only_returns_401(auth_client: AsyncClient) -> None:
    """AC: 'Authorization: Bearer    ' with whitespace-only token returns 401 Unauthorized."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer    "},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_bearer_header_with_multiple_token_parts_returns_401(
    auth_client: AsyncClient,
) -> None:
    """AC: Space-separated token chunks in Bearer header return 401 Unauthorized."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer gw_token_alpha extra_garbage"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# =============================================================================
# 4. Invalid Token Scenarios (401 Unauthorized)
# =============================================================================


@pytest.mark.asyncio
async def test_invalid_unrecognized_token_returns_401(auth_client: AsyncClient) -> None:
    """AC: Unrecognized token returns 401 Unauthorized with WWW-Authenticate header."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer completely_bogus_token_xyz_999"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert "invalid api token" in payload["error"]["message"].lower()


@pytest.mark.asyncio
async def test_token_prefix_match_fails_with_401(auth_client: AsyncClient) -> None:
    """Token that is a prefix of a valid token fails with 401 (constant-time full match)."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer gw_token_alph"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_token_suffix_match_fails_with_401(auth_client: AsyncClient) -> None:
    """Token that is a suffix of a valid token fails with 401."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer w_token_alpha"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_admin_token_substring_fails_with_401(auth_client: AsyncClient) -> None:
    """Substring of admin token fails with 401."""
    response = await auth_client.get(
        "/api/v1/test/auth/admin-only",
        headers={"Authorization": "Bearer admin_token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_null_byte_or_special_chars_in_token_returns_401(auth_client: AsyncClient) -> None:
    """Token containing injected null bytes or control characters fails cleanly with 401."""
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": "Bearer gw_token_alpha\x00malicious"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# =============================================================================
# 5. Authorization Scope Failures (403 Forbidden)
# =============================================================================


@pytest.mark.asyncio
async def test_standard_token_attempting_admin_endpoint_returns_403(
    auth_client: AsyncClient,
) -> None:
    """AC: Standard gateway token attempting admin-scoped route returns 403 Forbidden."""
    response = await auth_client.get(
        "/api/v1/test/auth/admin-only",
        headers={"Authorization": "Bearer gw_token_alpha"},
    )
    assert response.status_code == 403

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FORBIDDEN"
    assert "admin" in payload["error"]["message"].lower()

    # 403 Forbidden must NOT prompt for authentication credentials
    assert "WWW-Authenticate" not in response.headers


@pytest.mark.asyncio
async def test_standard_token_attempting_unassigned_custom_scope_returns_403(
    auth_client: AsyncClient,
) -> None:
    """AC: Valid token lacking required custom scope returns 403 Forbidden."""
    response = await auth_client.get(
        "/api/v1/test/auth/custom-scope",
        headers={"Authorization": "Bearer gw_token_alpha"},
    )
    assert response.status_code == 403
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FORBIDDEN"
    assert "custom_scope" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_admin_token_attempting_unassigned_custom_scope_returns_403(
    auth_client: AsyncClient,
) -> None:
    """Admin token also receives 403 if route requires a scope outside of admin/read/write."""
    response = await auth_client.get(
        "/api/v1/test/auth/custom-scope",
        headers={"Authorization": "Bearer admin_token_master"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# =============================================================================
# 6. Security Invariants (No Secret Leakage & Timing)
# =============================================================================


@pytest.mark.asyncio
async def test_error_responses_never_leak_provided_tokens(auth_client: AsyncClient) -> None:
    """Verify that supplied secret tokens never leak into error message or payload body."""
    secret_candidate = "my_highly_sensitive_secret_candidate_12345"
    response = await auth_client.get(
        "/api/v1/test/auth/standard",
        headers={"Authorization": f"Bearer {secret_candidate}"},
    )
    assert response.status_code == 401
    assert secret_candidate not in response.text
