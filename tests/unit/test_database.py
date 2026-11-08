"""Unit tests for DatabaseManager asynchronous MySQL connection pool."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiomysql
import pytest

from app.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Provide standard test settings for MySQL tests."""
    return Settings(
        gateway_api_tokens="gw_test_token_alpha",
        admin_api_tokens="admin_test_token_master",
        if_api_key="if_test_key_12345",
        if_organization_id="e9b25123-0000-0000-0000-000000000000",
        cc_api_key="cc_test_key_67890",
        cc_api_base_url="https://crew.qatarairwaysvirtual.com/api",
        db_host="127.0.0.1",
        db_port=3306,
        db_user="oryx_user",
        db_password="oryx_password",
        db_name="oryx_db",
        _env_file=None,
    )


def create_mock_cursor(
    fetchone_result: Any = None,
    fetchall_result: Any = None,
    rowcount: int = 1,
) -> AsyncMock:
    """Create a mock aiomysql DictCursor."""
    cursor = AsyncMock()
    cursor.execute = AsyncMock(return_value=None)
    cursor.fetchone = AsyncMock(return_value=fetchone_result)
    cursor.fetchall = AsyncMock(return_value=fetchall_result if fetchall_result is not None else [])
    cursor.rowcount = rowcount
    cursor.close = AsyncMock()
    return cursor


def create_mock_connection(cursor: AsyncMock) -> AsyncMock:
    """Create a mock aiomysql connection that returns the mock cursor as an async context manager."""
    conn = AsyncMock()

    @asynccontextmanager
    async def mock_cursor_ctx(*args: Any, **kwargs: Any) -> AsyncIterator[AsyncMock]:
        yield cursor

    conn.cursor = MagicMock(side_effect=mock_cursor_ctx)
    return conn


def create_mock_pool(conn: AsyncMock) -> MagicMock:
    """Create a mock aiomysql Pool."""
    pool = MagicMock()
    pool.closed = False

    def close_mock() -> None:
        pool.closed = True

    pool.close = MagicMock(side_effect=close_mock)
    pool.wait_closed = AsyncMock()

    @asynccontextmanager
    async def mock_acquire_ctx() -> AsyncIterator[AsyncMock]:
        yield conn

    pool.acquire = MagicMock(side_effect=mock_acquire_ctx)
    return pool


@pytest.mark.asyncio
async def test_database_manager_pool_creation(mock_settings: Settings) -> None:
    """Test that DatabaseManager properly initializes the pool with expected parameters."""
    from app.upstream.database import DatabaseManager

    mock_cursor = create_mock_cursor(fetchone_result={"test": 1})
    mock_conn = create_mock_connection(mock_cursor)
    mock_pool = create_mock_pool(mock_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        db_mgr = DatabaseManager(settings=mock_settings, minsize=2, maxsize=8)

        await db_mgr.connect()

        mock_create_pool.assert_awaited_once_with(
            host="127.0.0.1",
            port=3306,
            user="oryx_user",
            password="oryx_password",
            db="oryx_db",
            minsize=2,
            maxsize=8,
            autocommit=True,
            charset="utf8mb4",
            cursorclass=aiomysql.DictCursor,
            connect_timeout=10,
        )
        assert db_mgr.is_connected

        # Multiple connect calls should be idempotent
        await db_mgr.connect()
        assert mock_create_pool.await_count == 1

        await db_mgr.close()
        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_awaited_once()
        assert not db_mgr.is_connected


@pytest.mark.asyncio
async def test_acquire_connection_context_manager(mock_settings: Settings) -> None:
    """Test acquiring and releasing connection via async context manager."""
    from app.upstream.database import DatabaseManager

    mock_cursor = create_mock_cursor()
    mock_conn = create_mock_connection(mock_cursor)
    mock_pool = create_mock_pool(mock_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        db_mgr = DatabaseManager(settings=mock_settings)

        async with db_mgr.acquire() as conn:
            assert conn is mock_conn
            mock_pool.acquire.assert_called_once()

        # Connection should be safely released when exiting context manager
        await db_mgr.close()


@pytest.mark.asyncio
async def test_fetch_one_query(mock_settings: Settings) -> None:
    """Test fetch_one executes query with parameters and returns dictionary."""
    from app.upstream.database import DatabaseManager

    expected_row = {"id": 1, "callsign": "QRV101", "name": "Al Thani"}
    mock_cursor = create_mock_cursor(fetchone_result=expected_row)
    mock_conn = create_mock_connection(mock_cursor)
    mock_pool = create_mock_pool(mock_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        db_mgr = DatabaseManager(settings=mock_settings)

        result = await db_mgr.fetch_one(
            "SELECT id, callsign, name FROM pilots WHERE id = %s",
            (1,),
        )

        assert result == expected_row
        mock_cursor.execute.assert_awaited_once_with(
            "SELECT id, callsign, name FROM pilots WHERE id = %s",
            (1,),
        )
        mock_cursor.fetchone.assert_awaited_once()

        await db_mgr.close()


@pytest.mark.asyncio
async def test_fetch_all_query(mock_settings: Settings) -> None:
    """Test fetch_all executes query and returns list of dictionaries."""
    from app.upstream.database import DatabaseManager

    expected_rows = [
        {"id": 1, "callsign": "QRV101"},
        {"id": 2, "callsign": "QRV102"},
    ]
    mock_cursor = create_mock_cursor(fetchall_result=expected_rows)
    mock_conn = create_mock_connection(mock_cursor)
    mock_pool = create_mock_pool(mock_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        db_mgr = DatabaseManager(settings=mock_settings)

        results = await db_mgr.fetch_all("SELECT id, callsign FROM pilots")

        assert results == expected_rows
        mock_cursor.fetchall.assert_awaited_once()

        await db_mgr.close()


@pytest.mark.asyncio
async def test_execute_query(mock_settings: Settings) -> None:
    """Test execute runs statement with parameters and returns rowcount."""
    from app.upstream.database import DatabaseManager

    mock_cursor = create_mock_cursor(rowcount=3)
    mock_conn = create_mock_connection(mock_cursor)
    mock_pool = create_mock_pool(mock_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        db_mgr = DatabaseManager(settings=mock_settings)

        rows_affected = await db_mgr.execute(
            "UPDATE pilots SET status = %s WHERE status = %s",
            (1, 0),
        )

        assert rows_affected == 3
        mock_cursor.execute.assert_awaited_once_with(
            "UPDATE pilots SET status = %s WHERE status = %s",
            (1, 0),
        )

        await db_mgr.close()


@pytest.mark.asyncio
async def test_execute_does_not_retry_write_on_operational_error(mock_settings: Settings) -> None:
    """AC: execute() reconnects severed pool but does not re-run write statements to prevent duplicate side effects."""
    from app.upstream.database import DatabaseManager

    failing_cursor = AsyncMock()
    failing_cursor.execute.side_effect = aiomysql.OperationalError(2006, "MySQL server has gone away")
    failing_conn = create_mock_connection(failing_cursor)
    failing_pool = create_mock_pool(failing_conn)

    fresh_cursor = create_mock_cursor()
    fresh_conn = create_mock_connection(fresh_cursor)
    fresh_pool = create_mock_pool(fresh_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.side_effect = [failing_pool, fresh_pool]
        db_mgr = DatabaseManager(settings=mock_settings)

        with pytest.raises(aiomysql.OperationalError):
            await db_mgr.execute("INSERT INTO pilots (callsign) VALUES (%s)", ("QRV101",))

        # Statement must only be executed once, never retried blindly
        failing_cursor.execute.assert_awaited_once_with(
            "INSERT INTO pilots (callsign) VALUES (%s)",
            ("QRV101",),
        )
        fresh_cursor.execute.assert_not_awaited()

        # Pool should have been reconnected to heal subsequent queries
        assert mock_create_pool.await_count == 2
        assert db_mgr.pool is fresh_pool

        await db_mgr.close()


@pytest.mark.asyncio
async def test_concurrent_reconnect_stampede_protection(mock_settings: Settings) -> None:
    """AC: Concurrent failing queries do not trigger sequential pool rebuilds and do not discard healthy pools."""
    import asyncio

    from app.upstream.database import DatabaseManager

    # Initial pool with failing cursor
    failing_cursor = AsyncMock()
    failing_cursor.execute.side_effect = aiomysql.OperationalError(2006, "MySQL server has gone away")
    failing_conn = create_mock_connection(failing_cursor)
    failing_pool = create_mock_pool(failing_conn)

    # Reconnected fresh pool with successful cursor
    success_cursor = create_mock_cursor(fetchone_result={"status": "ok"})
    success_conn = create_mock_connection(success_cursor)
    success_pool = create_mock_pool(success_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.side_effect = [failing_pool, success_pool]
        db_mgr = DatabaseManager(settings=mock_settings)

        # First connect to establish failing pool
        await db_mgr.connect()
        assert mock_create_pool.await_count == 1

        # Run two concurrent fetch_one calls that encounter the failing pool at the same generation
        results = await asyncio.gather(
            db_mgr.fetch_one("SELECT status FROM config WHERE id = 1"),
            db_mgr.fetch_one("SELECT status FROM config WHERE id = 2"),
        )

        assert list(results) == [{"status": "ok"}, {"status": "ok"}]
        # Pool must be rebuilt exactly once, NOT twice
        assert mock_create_pool.await_count == 2
        assert db_mgr.pool is success_pool
        failing_pool.close.assert_called_once()
        success_pool.close.assert_not_called()

        await db_mgr.close()


@pytest.mark.asyncio
async def test_ping_success_and_failure(mock_settings: Settings) -> None:
    """Test ping returns True on responsive database and False on error."""
    from app.upstream.database import DatabaseManager

    mock_cursor = create_mock_cursor(fetchone_result={"1": 1})
    mock_conn = create_mock_connection(mock_cursor)
    mock_pool = create_mock_pool(mock_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = mock_pool
        db_mgr = DatabaseManager(settings=mock_settings)

        assert await db_mgr.ping() is True

        # When execution raises an unhandled error during ping
        mock_cursor.execute.side_effect = aiomysql.OperationalError(2006, "MySQL server has gone away")
        # On retry also raises error
        assert await db_mgr.ping() is False

        await db_mgr.close()


@pytest.mark.asyncio
async def test_reconnect_on_operational_error(mock_settings: Settings) -> None:
    """Test transparent reconnection and retry when an OperationalError occurs."""
    from app.upstream.database import DatabaseManager

    # First pool fails with OperationalError
    failing_cursor = AsyncMock()
    failing_cursor.execute.side_effect = aiomysql.OperationalError(2006, "MySQL server has gone away")
    failing_conn = create_mock_connection(failing_cursor)
    failing_pool = create_mock_pool(failing_conn)

    # Second pool succeeds
    success_cursor = create_mock_cursor(fetchone_result={"id": 1, "status": "reconnected"})
    success_conn = create_mock_connection(success_cursor)
    success_pool = create_mock_pool(success_conn)

    pools = [failing_pool, success_pool]

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.side_effect = pools
        db_mgr = DatabaseManager(settings=mock_settings)

        result = await db_mgr.fetch_one("SELECT id, status FROM pilots WHERE id = %s", (1,))

        assert result == {"id": 1, "status": "reconnected"}
        assert mock_create_pool.await_count == 2
        failing_pool.close.assert_called_once()

        await db_mgr.close()
        success_pool.close.assert_called_once()


@pytest.mark.asyncio
async def test_operational_error_raises_if_retry_fails(mock_settings: Settings) -> None:
    """Test that if retry also raises OperationalError, it bubbles up to caller."""
    from app.upstream.database import DatabaseManager

    failing_cursor = AsyncMock()
    failing_cursor.execute.side_effect = aiomysql.OperationalError(2006, "MySQL server has gone away")
    failing_conn = create_mock_connection(failing_cursor)
    pool_1 = create_mock_pool(failing_conn)
    pool_2 = create_mock_pool(failing_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.side_effect = [pool_1, pool_2]
        db_mgr = DatabaseManager(settings=mock_settings)

        with pytest.raises(aiomysql.OperationalError):
            await db_mgr.fetch_one("SELECT 1")

        assert mock_create_pool.await_count == 2
        await db_mgr.close()


@pytest.mark.asyncio
async def test_non_operational_error_does_not_retry(mock_settings: Settings) -> None:
    """Test that syntax/programming errors fail immediately without reconnecting."""
    from app.upstream.database import DatabaseManager

    syntax_cursor = AsyncMock()
    syntax_cursor.execute.side_effect = aiomysql.ProgrammingError(1064, "You have an error in your SQL syntax")
    syntax_conn = create_mock_connection(syntax_cursor)
    pool = create_mock_pool(syntax_conn)

    with patch("aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_create_pool.return_value = pool
        db_mgr = DatabaseManager(settings=mock_settings)

        with pytest.raises(aiomysql.ProgrammingError):
            await db_mgr.fetch_one("BAD SYNTAX")

        # Must not have created a second pool
        assert mock_create_pool.await_count == 1
        await db_mgr.close()
