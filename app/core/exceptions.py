"""Global exception handlers, error envelopes, and exception registration."""

import http
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("oryxgate.exceptions")

HTTP_422: int = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)

_STATUS_CODE_TO_ERROR_CODE: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_408_REQUEST_TIMEOUT: "REQUEST_TIMEOUT",
    status.HTTP_409_CONFLICT: "CONFLICT",
    HTTP_422: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    status.HTTP_502_BAD_GATEWAY: "BAD_GATEWAY",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    status.HTTP_504_GATEWAY_TIMEOUT: "GATEWAY_TIMEOUT",
}


def get_request_id(request: Request) -> str:
    """Extract or lazily create a request identifier for the given request."""
    if hasattr(request, "state") and hasattr(request.state, "request_id"):
        return str(request.state.request_id)
    return f"req_{uuid.uuid4().hex[:12]}"


def current_iso_timestamp() -> str:
    """Return formatted UTC ISO 8601 timestamp string ending in Z."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_error_envelope(
    *,
    code: str,
    message: str,
    detail: Any = None,
    request_id: str,
) -> dict[str, Any]:
    """Construct standard RFC/OryxGate error response dictionary."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
        },
        "meta": {
            "timestamp": current_iso_timestamp(),
            "request_id": request_id,
        },
    }


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> ORJSONResponse:
    """Global handler for Starlette and FastAPI HTTPExceptions."""
    request_id = get_request_id(request)
    status_code = exc.status_code
    error_code = _STATUS_CODE_TO_ERROR_CODE.get(
        status_code,
        f"HTTP_{status_code}",
    )

    detail_content: Any = None
    message: str
    if isinstance(exc.detail, str):
        message = exc.detail
    elif isinstance(exc.detail, dict):
        message = str(exc.detail.get("message", http.HTTPStatus(status_code).phrase))
        detail_content = exc.detail
    elif isinstance(exc.detail, list):
        message = http.HTTPStatus(status_code).phrase
        detail_content = exc.detail
    else:
        message = http.HTTPStatus(status_code).phrase

    headers = dict(exc.headers) if exc.headers else {}
    headers["X-Request-ID"] = request_id

    content = build_error_envelope(
        code=error_code,
        message=message,
        detail=detail_content,
        request_id=request_id,
    )
    return ORJSONResponse(
        status_code=status_code,
        content=content,
        headers=headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> ORJSONResponse:
    """Global handler for FastAPI / Pydantic RequestValidationErrors."""
    request_id = get_request_id(request)
    headers = {"X-Request-ID": request_id}

    content = build_error_envelope(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        detail=exc.errors(),
        request_id=request_id,
    )
    return ORJSONResponse(
        status_code=HTTP_422,
        content=content,
        headers=headers,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> ORJSONResponse:
    """Catch-all global handler for unhandled exceptions to prevent HTML tracebacks."""
    request_id = get_request_id(request)
    logger.exception(
        "Unhandled server exception occurred during request %s: %s",
        request_id,
        exc,
    )
    headers = {"X-Request-ID": request_id}

    content = build_error_envelope(
        code="INTERNAL_SERVER_ERROR",
        message="An internal server error occurred.",
        detail=None,
        request_id=request_id,
    )
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers onto the FastAPI application instance."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
