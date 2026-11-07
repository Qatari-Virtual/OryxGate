"""Application configuration and environment settings schema."""

import json
from collections.abc import Iterable
from functools import lru_cache
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_token_input(value: Any) -> list[SecretStr]:
    """Parse comma-separated, JSON-encoded, or iterable token strings into a list of SecretStr."""
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return []
        if v.startswith("[") or v.endswith("]") or v.startswith("{") or v.endswith("}"):
            if not (v.startswith("[") and v.endswith("]")):
                raise ValueError(
                    "Malformed bracketed token list, expected matching '[' and ']'."
                )
            try:
                parsed = json.loads(v)
            except Exception:
                raise ValueError(
                    "Invalid JSON array syntax for token list."
                ) from None
            if not isinstance(parsed, list):
                raise ValueError(
                    f"Token list JSON must be an array, got {type(parsed).__name__}."
                )
            parsed_tokens: list[SecretStr] = []
            for item in parsed:
                if isinstance(item, (dict, list, set)):
                    raise ValueError(
                        f"Token list elements must be scalar token strings, got {type(item).__name__}."
                    )
                item_str = str(item).strip()
                if item_str:
                    parsed_tokens.append(SecretStr(item_str))
            return parsed_tokens
        return [
            SecretStr(tok.strip())
            for tok in v.split(",")
            if tok.strip()
        ]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, str)):
        tokens: list[SecretStr] = []
        for item in value:
            if isinstance(item, SecretStr):
                if item.get_secret_value().strip():
                    tokens.append(item)
            elif str(item).strip():
                tokens.append(SecretStr(str(item).strip()))
        return tokens
    return []


class Settings(BaseSettings):
    """Central configuration schema for OryxGate gateway microservice."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        hide_input_in_errors=True,
        extra="ignore",
    )

    # Downstream Authentication & Gateway Security
    gateway_api_tokens: Annotated[list[SecretStr], NoDecode] = Field(
        ...,
        description="List of Bearer tokens permitted to access OryxGate REST endpoints.",
    )
    admin_api_tokens: Annotated[list[SecretStr], NoDecode] = Field(
        ...,
        description="List of privileged Bearer tokens permitted for admin actions and force_refresh.",
    )

    # Infinite Flight Upstream Integration
    if_api_key: SecretStr = Field(
        ...,
        description="Infinite Flight Live API v2 user key (used in query param ?apikey=).",
    )
    if_organization_id: str = Field(
        ...,
        description="Infinite Flight Live API v3 organization UUID.",
    )

    # Crew Center Upstream Integration
    cc_api_key: SecretStr = Field(
        ...,
        description="Crew Center PHP API secret key.",
    )
    cc_api_base_url: str = Field(
        ...,
        description="Base URL for the Crew Center PHP API (e.g. https://crew.qatarairwaysvirtual.com/api).",
    )

    # MySQL Database Connection
    db_host: str = Field(
        ...,
        description="MySQL database hostname or IP address.",
    )
    db_port: int = Field(
        default=3306,
        description="MySQL database connection port.",
    )
    db_user: str = Field(
        ...,
        description="MySQL database username.",
    )
    db_password: SecretStr = Field(
        ...,
        description="MySQL database password.",
    )
    db_name: str = Field(
        ...,
        description="MySQL database schema name.",
    )

    # Application & Environment Runtime
    environment: str = Field(
        default="development",
        description="Deployment environment (development, staging, production, testing).",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode and verbose log outputs.",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Server host address.",
    )
    port: int = Field(
        default=8000,
        description="Server listening port.",
    )

    # Caching Layer TTLs (Seconds)
    cache_ttl_sessions: int = Field(
        default=600,
        description="Cache TTL for IF v2 multiplayer sessions list (10m).",
    )
    cache_ttl_flights: int = Field(
        default=20,
        description="Cache TTL for IF v2 multiplayer active flights list (20s).",
    )
    cache_ttl_route: int = Field(
        default=60,
        description="Cache TTL for IF v2 flight breadcrumb routes (60s).",
    )
    cache_ttl_roster: int = Field(
        default=300,
        description="Cache TTL for IF v3 organization aircraft roster (5m).",
    )
    cache_ttl_positions: int = Field(
        default=30,
        description="Cache TTL for IF v3 persistent aircraft positions (30s).",
    )
    cache_ttl_schedules: int = Field(
        default=60,
        description="Cache TTL for IF v3 organization schedules (60s).",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @field_validator("gateway_api_tokens", "admin_api_tokens", mode="before")
    @classmethod
    def validate_token_list(cls, value: Any) -> list[SecretStr]:
        """Normalize token inputs from strings or lists into SecretStr collections."""
        return _parse_token_input(value)

    @field_validator("gateway_api_tokens")
    @classmethod
    def validate_gateway_tokens_non_empty(
        cls, value: list[SecretStr]
    ) -> list[SecretStr]:
        """Ensure at least one valid gateway token is configured."""
        if not value:
            raise ValueError(
                "GATEWAY_API_TOKENS cannot be empty. At least one Bearer token is required."
            )
        return value

    @field_validator("cc_api_base_url")
    @classmethod
    def validate_and_normalize_cc_url(cls, value: str) -> str:
        """Validate URL scheme and strip trailing slashes."""
        v = value.strip()
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"CC_API_BASE_URL must be a valid HTTP/HTTPS URL, got: '{value}'"
            )
        return v.rstrip("/")

    @property
    def raw_gateway_api_tokens(self) -> list[str]:
        """Return unmasked list of gateway API token strings for constant-time comparisons."""
        return [t.get_secret_value() for t in self.gateway_api_tokens]

    @property
    def raw_admin_api_tokens(self) -> list[str]:
        """Return unmasked list of admin API token strings for constant-time comparisons."""
        return [t.get_secret_value() for t in self.admin_api_tokens]

    def __getattr__(self, name: str) -> Any:
        """Support case-insensitive / uppercase attribute access (e.g. settings.DB_HOST)."""
        lower = name.lower()
        if lower in self.__dict__:
            return self.__dict__[lower]
        if lower in self.model_fields:
            return getattr(self, lower)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


@lru_cache
def get_settings() -> Settings:
    """Dependency provider returning cached Settings singleton."""
    return Settings()
