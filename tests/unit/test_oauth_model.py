"""Unit tests for IFLiveTokensModel and OAuthTokenRecord (TASK-2.2)."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.models.oauth import IFLiveTokensModel, OAuthTokenRecord, normalize_utc_datetime

# =========================================================================
# Fixtures and Helpers
# =========================================================================


class MockDatabaseManager:
    """Mock DatabaseManager tracking queries and parameters."""

    def __init__(self) -> None:
        self.fetch_one = AsyncMock(return_value=None)
        self.fetch_all = AsyncMock(return_value=[])
        self.execute = AsyncMock(return_value=1)
        self.insert = AsyncMock(return_value=1)


@pytest.fixture
def mock_db() -> MockDatabaseManager:
    return MockDatabaseManager()


@pytest.fixture
def token_model(mock_db: MockDatabaseManager) -> IFLiveTokensModel:
    return IFLiveTokensModel(db_manager=mock_db)  # type: ignore[arg-type]


# =========================================================================
# Unit Tests: Datetime Normalization Helper
# =========================================================================


def test_normalize_utc_datetime_aware() -> None:
    """AC: Timezone-aware datetime converted to UTC."""
    plus_two = timezone(timedelta(hours=2))
    dt_aware = datetime(2026, 11, 8, 20, 0, 0, tzinfo=plus_two)
    normalized = normalize_utc_datetime(dt_aware)

    assert normalized.tzinfo == UTC
    assert normalized.hour == 18
    assert normalized.year == 2026
    assert normalized.month == 11
    assert normalized.day == 8


def test_normalize_utc_datetime_naive() -> None:
    """AC: Naive datetime assumed to be UTC and given tzinfo=timezone.utc."""
    dt_naive = datetime(2026, 11, 8, 18, 0, 0)
    normalized = normalize_utc_datetime(dt_naive)

    assert normalized.tzinfo == UTC
    assert normalized.hour == 18


def test_normalize_utc_datetime_iso_string() -> None:
    """AC: ISO-8601 strings normalized to UTC datetime."""
    iso_str = "2026-11-08T21:30:00+03:00"
    normalized = normalize_utc_datetime(iso_str)

    assert normalized.tzinfo == UTC
    assert normalized.hour == 18
    assert normalized.minute == 30


def test_normalize_utc_datetime_timestamp() -> None:
    """AC: Numeric unix timestamp converted to UTC datetime."""
    ts = 1762624800.0  # Represents a fixed epoch timestamp
    normalized = normalize_utc_datetime(ts)

    assert normalized.tzinfo == UTC
    assert normalized == datetime.fromtimestamp(ts, tz=UTC)


def test_normalize_utc_datetime_invalid() -> None:
    """Invalid input types raise ValueError."""
    with pytest.raises(ValueError, match="Cannot convert"):
        normalize_utc_datetime(["invalid"])


# =========================================================================
# Acceptance Criteria: Reads pilot_id = 1 Master Token with UTC Timestamps
# =========================================================================


@pytest.mark.asyncio
async def test_get_by_pilot_id_master_token_naive_datetime_converted(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """AC: Reading pilot_id = 1 master token converts MySQL naive datetimes to timezone-aware UTC."""
    raw_row: dict[str, Any] = {
        "pilot_id": 1,
        "access_token": "if_master_access_token_123",
        "refresh_token": "if_master_refresh_token_456",
        "expires_at": datetime(2026, 11, 8, 20, 0, 0),  # Naive from MySQL
        "scope": "openid profile offline_access live:schedules.read",
        "if_user_id": "e9b25123-0000-0000-0000-000000000000",
        "created_at": datetime(2026, 11, 8, 19, 0, 0),
        "updated_at": datetime(2026, 11, 8, 19, 0, 0),
    }
    mock_db.fetch_one.return_value = raw_row

    result = await token_model.get_by_pilot_id(1)

    assert result is not None
    assert result["pilot_id"] == 1
    assert result["access_token"] == "if_master_access_token_123"
    assert result["refresh_token"] == "if_master_refresh_token_456"

    # Verify timezone-aware UTC
    assert result["expires_at"].tzinfo == UTC
    assert result["expires_at"] == datetime(2026, 11, 8, 20, 0, 0, tzinfo=UTC)
    assert result["created_at"].tzinfo == UTC
    assert result["updated_at"].tzinfo == UTC

    # Verify query and args
    mock_db.fetch_one.assert_awaited_once()
    assert mock_db.fetch_one.await_args is not None
    query, args = mock_db.fetch_one.await_args[0]
    assert "pilot_id = %s" in query
    assert args == (1,)


@pytest.mark.asyncio
async def test_get_by_pilot_id_not_found(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify get_by_pilot_id returns None when token row does not exist."""
    mock_db.fetch_one.return_value = None

    result = await token_model.get_by_pilot_id(999)

    assert result is None
    mock_db.fetch_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_by_if_user_id(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify get_by_if_user_id fetches by UUID and normalizes timestamps."""
    raw_row = {
        "pilot_id": 42,
        "access_token": "token_xyz",
        "refresh_token": "refresh_xyz",
        "expires_at": "2026-11-08 20:00:00",  # String formatted
        "scope": "read",
        "if_user_id": "uuid-1234",
        "created_at": "2026-11-08 19:00:00",
        "updated_at": "2026-11-08 19:00:00",
    }
    mock_db.fetch_one.return_value = raw_row

    result = await token_model.get_by_if_user_id("uuid-1234")

    assert result is not None
    assert result["pilot_id"] == 42
    assert result["expires_at"].tzinfo == UTC
    mock_db.fetch_one.assert_awaited_once()
    assert mock_db.fetch_one.await_args is not None
    query, args = mock_db.fetch_one.await_args[0]
    assert "if_user_id = %s" in query
    assert args == ("uuid-1234",)


@pytest.mark.asyncio
async def test_get_pending_by_state(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify get_pending_by_state matches pending state prefix."""
    raw_row = {
        "pilot_id": 1,
        "access_token": "pending:secret_state_123:code_verifier_456",
        "refresh_token": "",
        "expires_at": datetime(2026, 11, 8, 19, 0, 0, tzinfo=UTC),
        "scope": "",
        "if_user_id": None,
        "created_at": None,
        "updated_at": None,
    }
    mock_db.fetch_one.return_value = raw_row

    result = await token_model.get_pending_by_state("secret_state_123")

    assert result is not None
    assert result["pilot_id"] == 1
    mock_db.fetch_one.assert_awaited_once()
    assert mock_db.fetch_one.await_args is not None
    query, args = mock_db.fetch_one.await_args[0]
    assert "access_token LIKE %s" in query
    assert args == ("pending:secret_state_123:%",)


# =========================================================================
# Acceptance Criteria: Writes pilot_id = 1 Master Token with UTC Timestamps
# =========================================================================


@pytest.mark.asyncio
async def test_save_token_master_token_with_timezone_aware_input(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """AC: Writing pilot_id = 1 master token converts non-UTC timezone-aware input into UTC."""
    plus_four = timezone(timedelta(hours=4))
    # 22:00 at +04:00 is 18:00 UTC
    expires_at_aware = datetime(2026, 11, 8, 22, 0, 0, tzinfo=plus_four)

    res = await token_model.save_token(
        pilot_id=1,
        access_token="new_access_token_abc",
        refresh_token="new_refresh_token_def",
        expires_at=expires_at_aware,
        scope="openid live:aircraft.read",
        if_user_id="e9b25123-0000-0000-0000-000000000000",
    )

    assert res == 1
    # Verify execute / insert was called
    mock_db.insert.assert_awaited_once()
    assert mock_db.insert.await_args is not None
    query, args = mock_db.insert.await_args[0]
    assert "INSERT INTO live_if_oauth_tokens" in query
    assert "ON DUPLICATE KEY UPDATE" in query

    # args: (pilot_id, access_token, refresh_token, expires_at, scope, if_user_id)
    assert args[0] == 1
    assert args[1] == "new_access_token_abc"
    assert args[2] == "new_refresh_token_def"
    # expires_at in args must be normalized to UTC datetime
    saved_expires_at = args[3]
    assert isinstance(saved_expires_at, datetime)
    assert saved_expires_at.tzinfo == UTC
    assert saved_expires_at.hour == 18
    assert args[4] == "openid live:aircraft.read"
    assert args[5] == "e9b25123-0000-0000-0000-000000000000"


@pytest.mark.asyncio
async def test_save_token_fallback_when_db_has_no_insert(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify save_token falls back cleanly to db.execute if db.insert is not present."""
    # Delete insert method from mock
    delattr(mock_db, "insert")

    res = await token_model.save_token(
        pilot_id=1,
        access_token="tok",
        refresh_token="ref",
        expires_at=datetime(2026, 11, 8, 20, 0, 0, tzinfo=UTC),
        scope="read",
    )

    assert res == 1
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_token_master_token_utc_conversion(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """AC: update_token writes UTC normalized expires_at for pilot_id = 1."""
    expires_iso = "2026-11-08T23:00:00+03:00"  # 20:00 UTC

    res = await token_model.update_token(
        pilot_id=1,
        access_token="rotated_access_token",
        refresh_token="rotated_refresh_token",
        expires_at=expires_iso,
        scope="openid profile offline_access",
    )

    assert res == 1
    mock_db.execute.assert_awaited_once()
    assert mock_db.execute.await_args is not None
    query, args = mock_db.execute.await_args[0]
    assert "UPDATE live_if_oauth_tokens" in query
    assert "SET access_token = %s, refresh_token = %s, expires_at = %s, scope = %s" in query
    assert "WHERE pilot_id = %s" in query

    assert args[0] == "rotated_access_token"
    assert args[1] == "rotated_refresh_token"
    saved_expires_at = args[2]
    assert isinstance(saved_expires_at, datetime)
    assert saved_expires_at.tzinfo == UTC
    assert saved_expires_at.hour == 20
    assert args[3] == "openid profile offline_access"
    assert args[4] == 1


@pytest.mark.asyncio
async def test_update_if_user_id(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify update_if_user_id executes UPDATE query."""
    res = await token_model.update_if_user_id(pilot_id=1, if_user_id="new-uuid-5678")

    assert res == 1
    mock_db.execute.assert_awaited_once()
    assert mock_db.execute.await_args is not None
    query, args = mock_db.execute.await_args[0]
    assert "UPDATE live_if_oauth_tokens" in query
    assert "SET if_user_id = %s" in query
    assert args == ("new-uuid-5678", 1)


@pytest.mark.asyncio
async def test_set_pending(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify set_pending saves state:verifier pattern in access_token column."""
    res = await token_model.set_pending(
        pilot_id=1,
        state="auth_state_xyz",
        verifier="code_verifier_123",
    )

    assert res == 1
    mock_db.insert.assert_awaited_once()
    assert mock_db.insert.await_args is not None
    query, args = mock_db.insert.await_args[0]
    assert "INSERT INTO live_if_oauth_tokens" in query
    assert "ON DUPLICATE KEY UPDATE" in query
    assert args == (1, "pending:auth_state_xyz:code_verifier_123", "")


@pytest.mark.asyncio
async def test_delete_token(
    mock_db: MockDatabaseManager,
    token_model: IFLiveTokensModel,
) -> None:
    """Verify delete_token deletes row for given pilot_id."""
    res = await token_model.delete_token(pilot_id=1)

    assert res == 1
    mock_db.execute.assert_awaited_once()
    assert mock_db.execute.await_args is not None
    query, args = mock_db.execute.await_args[0]
    assert "DELETE FROM live_if_oauth_tokens WHERE pilot_id = %s" in query
    assert args == (1,)


# =========================================================================
# Domain Model: OAuthTokenRecord Pydantic Tests
# =========================================================================


def test_oauth_token_record_model() -> None:
    """Verify OAuthTokenRecord parsing, timezone enforcement, and helper methods."""
    now_utc = datetime.now(UTC)
    future_utc = now_utc + timedelta(hours=1)

    record = OAuthTokenRecord(
        pilot_id=1,
        access_token="tok_123",
        refresh_token="ref_456",
        expires_at=future_utc,
        scope="openid live:aircraft.read",
    )

    assert record.pilot_id == 1
    assert record.expires_at.tzinfo == UTC
    assert record.is_expired(buffer_seconds=60) is False
    assert record.is_pending is False


def test_oauth_token_record_expired() -> None:
    """Verify is_expired returns True when expires_at within buffer."""
    now_utc = datetime.now(UTC)
    soon = now_utc + timedelta(seconds=30)  # expires in 30 seconds

    record = OAuthTokenRecord(
        pilot_id=1,
        access_token="tok_123",
        refresh_token="ref_456",
        expires_at=soon,
        scope="read",
    )

    # With default 60s buffer, expires in 30s is considered expired
    assert record.is_expired(buffer_seconds=60) is True
    # With 10s buffer, not yet expired
    assert record.is_expired(buffer_seconds=10) is False


def test_oauth_token_record_pending() -> None:
    """Verify is_pending identifies pending PKCE flow states."""
    record = OAuthTokenRecord(
        pilot_id=1,
        access_token="pending:state123:verifier456",
        refresh_token="",
        expires_at=datetime.now(UTC),
        scope="",
    )

    assert record.is_pending is True
    assert record.pending_state == "state123"
    assert record.pending_verifier == "verifier456"
