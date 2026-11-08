"""OAuth Token Model and Domain Schemas for Infinite Flight v3 (TASK-2.2)."""

import contextlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.upstream.database import DatabaseManager


def normalize_utc_datetime(value: Any) -> datetime:
    """Convert a datetime, string, or epoch timestamp to a timezone-aware UTC datetime.

    - If already a timezone-aware datetime, converts to UTC via astimezone.
    - If a naive datetime, assumes UTC and sets tzinfo=timezone.utc.
    - If a string, parses via fromisoformat or standard SQL datetime format.
    - If a float or int, converts from unix epoch timestamp in UTC.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)

    if isinstance(value, str):
        v = value.strip()
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            # Fallback for standard SQL 'YYYY-MM-DD HH:MM:SS' strings
            dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    raise ValueError(f"Cannot convert {type(value).__name__} to UTC datetime.")


class OAuthTokenRecord(BaseModel):
    """Domain model representing an Infinite Flight OAuth token record."""

    pilot_id: int = Field(..., description="Pilot ID (pilot_id = 1 is the Master/Admin token)")
    access_token: str = Field(..., description="OAuth access token or pending flow state")
    refresh_token: str = Field(default="", description="OAuth refresh token")
    expires_at: datetime = Field(..., description="Access token expiration UTC timestamp")
    scope: str = Field(default="", description="OAuth authorized scopes")
    if_user_id: str | None = Field(default=None, description="Infinite Flight user UUID")
    created_at: datetime | None = Field(default=None, description="Record creation UTC timestamp")
    updated_at: datetime | None = Field(
        default=None, description="Record last update UTC timestamp"
    )

    @field_validator("expires_at", "created_at", "updated_at", mode="before")
    @classmethod
    def _coerce_utc(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        return normalize_utc_datetime(v)

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """Return True if current UTC time is within buffer_seconds of expiration."""
        now_utc = datetime.now(UTC)
        return now_utc.timestamp() >= (self.expires_at.timestamp() - buffer_seconds)

    @property
    def is_pending(self) -> bool:
        """Return True if token row represents a pending PKCE authorization flow."""
        return self.access_token.startswith("pending:")

    @property
    def pending_state(self) -> str | None:
        """Extract PKCE state parameter if token is in pending state."""
        if not self.is_pending:
            return None
        parts = self.access_token.split(":")
        return parts[1] if len(parts) >= 2 else None

    @property
    def pending_verifier(self) -> str | None:
        """Extract PKCE code verifier if token is in pending state."""
        if not self.is_pending:
            return None
        parts = self.access_token.split(":")
        return parts[2] if len(parts) >= 3 else None


class IFLiveTokensModel:
    """Data access model for live_if_oauth_tokens MySQL table."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    @staticmethod
    def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        """Ensure all datetime columns in the retrieved row are timezone-aware UTC."""
        if not row:
            return None
        normalized = dict(row)
        for col in ("expires_at", "created_at", "updated_at"):
            val = normalized.get(col)
            if val is not None:
                with contextlib.suppress(ValueError, TypeError):
                    normalized[col] = normalize_utc_datetime(val)
        return normalized

    async def _write(self, query: str, args: tuple[Any, ...]) -> int:
        """Execute insert or update query, supporting both db.insert and db.execute."""
        if hasattr(self.db, "insert"):
            return await self.db.insert(query, args)
        return await self.db.execute(query, args)

    async def get_by_pilot_id(self, pilot_id: int) -> dict[str, Any] | None:
        """Fetch token record by pilot_id with timezone-aware UTC timestamps."""
        query = """
            SELECT * FROM live_if_oauth_tokens WHERE pilot_id = %s
        """
        args = (pilot_id,)
        row = await self.db.fetch_one(query, args)
        return self._normalize_row(row)

    async def get_by_if_user_id(self, if_user_id: str) -> dict[str, Any] | None:
        """Fetch token record by Infinite Flight user UUID with timezone-aware UTC timestamps."""
        query = """
            SELECT * FROM live_if_oauth_tokens WHERE if_user_id = %s
        """
        args = (if_user_id,)
        row = await self.db.fetch_one(query, args)
        return self._normalize_row(row)

    async def get_pending_by_state(self, state: str) -> dict[str, Any] | None:
        """Fetch pending authorization token row matching pending:<state>:%."""
        query = """
            SELECT * FROM live_if_oauth_tokens WHERE access_token LIKE %s
        """
        args = (f"pending:{state}:%",)
        row = await self.db.fetch_one(query, args)
        return self._normalize_row(row)

    async def save_token(
        self,
        pilot_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: Any,
        scope: str,
        if_user_id: str | None = None,
    ) -> int:
        """Insert or update token row, guaranteeing expires_at is stored in UTC."""
        normalized_expires = normalize_utc_datetime(expires_at)
        query = """
            INSERT INTO live_if_oauth_tokens (pilot_id, access_token, refresh_token, expires_at, scope, if_user_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                access_token = VALUES(access_token),
                refresh_token = VALUES(refresh_token),
                expires_at = VALUES(expires_at),
                scope = VALUES(scope),
                if_user_id = VALUES(if_user_id),
                updated_at = NOW()
        """
        args = (pilot_id, access_token, refresh_token, normalized_expires, scope, if_user_id)
        return await self._write(query, args)

    async def update_token(
        self,
        pilot_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: Any,
        scope: str,
    ) -> int:
        """Update token record for pilot_id with normalized UTC expires_at."""
        normalized_expires = normalize_utc_datetime(expires_at)
        query = """
            UPDATE live_if_oauth_tokens
            SET access_token = %s, refresh_token = %s, expires_at = %s, scope = %s, updated_at = NOW()
            WHERE pilot_id = %s
        """
        args = (access_token, refresh_token, normalized_expires, scope, pilot_id)
        return await self.db.execute(query, args)

    async def update_if_user_id(self, pilot_id: int, if_user_id: str) -> int:
        """Update if_user_id for a given pilot_id."""
        query = """
            UPDATE live_if_oauth_tokens
            SET if_user_id = %s, updated_at = NOW()
            WHERE pilot_id = %s
        """
        args = (if_user_id, pilot_id)
        return await self.db.execute(query, args)

    async def set_pending(self, pilot_id: int, state: str, verifier: str) -> int:
        """Store pending state and PKCE verifier for a pilot."""
        pending_value = f"pending:{state}:{verifier}"
        query = """
            INSERT INTO live_if_oauth_tokens (pilot_id, access_token, refresh_token, expires_at, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                access_token = VALUES(access_token),
                refresh_token = VALUES(refresh_token),
                expires_at = NOW(),
                updated_at = NOW()
        """
        args = (pilot_id, pending_value, "")
        return await self._write(query, args)

    async def delete_token(self, pilot_id: int) -> int:
        """Delete token row for a given pilot_id."""
        query = """
            DELETE FROM live_if_oauth_tokens WHERE pilot_id = %s
        """
        args = (pilot_id,)
        return await self.db.execute(query, args)

    async def get_token_record(self, pilot_id: int) -> OAuthTokenRecord | None:
        """Convenience method returning a validated OAuthTokenRecord or None."""
        row = await self.get_by_pilot_id(pilot_id)
        if not row:
            return None
        return OAuthTokenRecord.model_validate(row)
