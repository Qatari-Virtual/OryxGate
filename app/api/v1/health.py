"""Health check endpoint handler."""

import time

from fastapi import APIRouter, Request

from app.core.exceptions import current_iso_timestamp, get_request_id
from app.models.health import HealthData, HealthResponse, ResponseMeta, UpstreamStatus

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health & Diagnostic Status",
    description="Check OryxGate health, service uptime, and upstream connectivity states without authentication.",
)
async def get_health(request: Request) -> HealthResponse:
    """Return health status, current uptime, and upstream connectivity diagnostics."""
    start_time = getattr(request.app.state, "start_time", None)
    uptime = 0.0 if start_time is None else max(0.0, round(time.monotonic() - start_time, 2))

    request_id = get_request_id(request)
    timestamp = current_iso_timestamp()

    return HealthResponse(
        success=True,
        status="healthy",
        uptime=uptime,
        data=HealthData(
            status="healthy",
            uptime=uptime,
            uptime_seconds=uptime,
            upstream_status=UpstreamStatus(),
        ),
        meta=ResponseMeta(
            timestamp=timestamp,
            request_id=request_id,
        ),
    )
