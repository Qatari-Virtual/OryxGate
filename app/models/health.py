"""Health check response models and schemas."""

from pydantic import BaseModel, Field


class UpstreamStatus(BaseModel):
    """Upstream service connectivity states."""

    if_v3: str = Field(default="connected", description="Infinite Flight API v3 connectivity")
    if_v2: str = Field(default="connected", description="Infinite Flight API v2 connectivity")
    crew_center: str = Field(default="connected", description="Crew Center PHP API connectivity")
    database: str = Field(default="connected", description="MySQL persistence pool connectivity")


class HealthData(BaseModel):
    """Health diagnostic payload data."""

    status: str = Field(default="healthy", description="Gateway health status indicator")
    uptime: float = Field(..., description="Gateway service uptime in seconds")
    uptime_seconds: float = Field(..., description="Gateway service uptime in seconds")
    upstream_status: UpstreamStatus = Field(
        default_factory=UpstreamStatus,
        description="Upstream dependencies connection status",
    )


class ResponseMeta(BaseModel):
    """Standard OryxGate response metadata envelope."""

    timestamp: str = Field(..., description="UTC ISO 8601 generation timestamp")
    request_id: str = Field(..., description="Unique request tracing identifier")
    cached: bool = Field(default=False, description="Whether payload was served from cache")
    cache_age_seconds: float | None = Field(
        default=None, description="Age of cached payload in seconds"
    )


class HealthResponse(BaseModel):
    """Standard health check API response envelope."""

    success: bool = Field(default=True, description="Request execution success flag")
    status: str = Field(default="healthy", description="Top-level status alias")
    uptime: float = Field(..., description="Top-level uptime alias in seconds")
    data: HealthData = Field(..., description="Health check details")
    meta: ResponseMeta = Field(..., description="Response metadata")
