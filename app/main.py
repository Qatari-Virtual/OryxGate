"""FastAPI Application Factory and Lifecycle Management."""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app import __version__
from app.api.v1 import v1_router
from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers, unhandled_exception_handler


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensure every HTTP request has a unique tracing request_id attached."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("X-Request-ID")
        if not req_id or not req_id.strip():
            req_id = f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id

        try:
            response = await call_next(request)
        except Exception as exc:
            response = await unhandled_exception_handler(request, exc)

        response.headers["X-Request-ID"] = req_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager for startup and shutdown hooks."""
    if not hasattr(app.state, "start_time") or app.state.start_time is None:
        app.state.start_time = time.monotonic()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure an OryxGate FastAPI application instance."""
    app = FastAPI(
        title="OryxGate API Gateway",
        description="Asynchronous API Gateway, state fusion engine, and caching microservice for virtual aviation operations.",
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # Initial start time fallback for immediate test client execution
    app.state.start_time = time.monotonic()
    app.default_response_class = ORJSONResponse  # type: ignore[attr-defined]
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    # Middlewares
    app.add_middleware(RequestIdMiddleware)

    # Global Exception Handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(v1_router)

    return app


app = create_app()
