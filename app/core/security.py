"""Gateway Bearer token authentication middleware and security dependencies."""

import secrets
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

http_bearer = HTTPBearer(auto_error=False)


class CallerContext:
    """Represents an authenticated downstream caller and their granted permission scopes."""

    def __init__(self, token: str, scopes: set[str] | list[str]) -> None:
        self._token: str = token
        self.scopes: set[str] = set(scopes)

    @property
    def token(self) -> str:
        """Return the caller's raw token."""
        return self._token

    @property
    def is_admin(self) -> bool:
        """Check if caller possesses administrative privileges."""
        return "admin" in self.scopes

    def has_scope(self, scope: str) -> bool:
        """Check if a specific permission scope is granted."""
        return scope in self.scopes

    def __repr__(self) -> str:
        masked = f"{self._token[:3]}***{self._token[-2:]}" if len(self._token) >= 6 else "***"
        sorted_scopes = sorted(list(self.scopes))
        return f"CallerContext(token='{masked}', scopes={sorted_scopes})"

    def __str__(self) -> str:
        return self.__repr__()


async def get_current_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CallerContext:
    """Validate incoming Authorization: Bearer <TOKEN> and yield caller context.

    Performs constant-time token comparison against configured tokens to eliminate
    timing side-channel attacks.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme; Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip() if credentials.credentials else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty Bearer token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison sweep across all configured tokens
    matched_admin = False
    for admin_tok in settings.raw_admin_api_tokens:
        if secrets.compare_digest(token, admin_tok):
            matched_admin = True

    matched_gateway = False
    for gw_tok in settings.raw_gateway_api_tokens:
        if secrets.compare_digest(token, gw_tok):
            matched_gateway = True

    if not (matched_admin or matched_gateway):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scopes: set[str] = {"read", "write"}
    if matched_admin:
        scopes.add("admin")

    return CallerContext(token=token, scopes=scopes)


async def require_admin(
    caller: Annotated[CallerContext, Depends(get_current_token)],
) -> CallerContext:
    """FastAPI dependency asserting caller holds the 'admin' permission scope."""
    if not caller.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin scope required for this operation",
        )
    return caller


def require_scope(
    required_scope: str,
) -> Callable[[CallerContext], Coroutine[Any, Any, CallerContext]]:
    """FastAPI dependency factory enforcing that caller holds the specified scope."""

    async def _scope_checker(
        caller: Annotated[CallerContext, Depends(get_current_token)],
    ) -> CallerContext:
        if not caller.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' required for this operation",
            )
        return caller

    return _scope_checker
