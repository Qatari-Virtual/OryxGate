"""Integration tests for DatabaseManager against live MySQL database."""

import os

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.upstream.database import DatabaseManager


@pytest.mark.asyncio
async def test_live_database_connection() -> None:
    """Attempt live database connection if DB_HOST and DB_PASSWORD are configured in environment."""
    try:
        # Clear lru_cache to ensure freshly loaded .env settings
        get_settings.cache_clear()
        settings = get_settings()
    except (ValidationError, Exception) as exc:
        pytest.skip(f"Environment settings invalid or missing required variables: {exc}")

    if (
        not settings.db_host
        or settings.db_host in ("127.0.0.1", "localhost")
        and not os.environ.get("RUN_LOCAL_DB_TESTS")
    ):
        # If DB_HOST is set to default and no flag is present, skip
        pytest.skip("Live database credentials not configured in environment.")

    db = DatabaseManager(settings=settings)
    try:
        await db.connect()
        assert db.is_connected is True

        # Test SELECT 1
        is_healthy = await db.ping()
        assert is_healthy is True

        # Test basic schema query
        tables = await db.fetch_all("SHOW TABLES")
        assert isinstance(tables, list)
    finally:
        await db.close()
