"""Asynchronous MySQL connection pool and database manager using aiomysql."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import aiomysql

from app.config import Settings, get_settings

logger = logging.getLogger("oryxgate.upstream.database")

T = TypeVar("T")


class DatabaseManager:
    """Manages an asynchronous MySQL connection pool with self-healing reconnection."""

    def __init__(
        self,
        settings: Settings | None = None,
        minsize: int = 1,
        maxsize: int = 10,
        connect_timeout: int = 10,
        autocommit: bool = True,
        charset: str = "utf8mb4",
    ) -> None:
        self._settings = settings or get_settings()
        self._minsize = minsize
        self._maxsize = maxsize
        self._connect_timeout = connect_timeout
        self._autocommit = autocommit
        self._charset = charset
        self._pool: aiomysql.Pool | None = None
        self._lock = asyncio.Lock()

    @property
    def pool(self) -> aiomysql.Pool | None:
        """Return the current underlying aiomysql pool instance."""
        return self._pool

    @property
    def is_connected(self) -> bool:
        """Check whether the pool is initialized and open."""
        if self._pool is None:
            return False
        closed = getattr(self._pool, "closed", False)
        if isinstance(closed, bool):
            return not closed
        return True

    async def connect(self) -> None:
        """Initialize the aiomysql connection pool if not already active."""
        if self.is_connected:
            return

        async with self._lock:
            if self.is_connected:
                return

            logger.info(
                "Initializing MySQL connection pool to %s:%s (db=%s, min=%s, max=%s)",
                self._settings.db_host,
                self._settings.db_port,
                self._settings.db_name,
                self._minsize,
                self._maxsize,
            )

            self._pool = await aiomysql.create_pool(
                host=self._settings.db_host,
                port=self._settings.db_port,
                user=self._settings.db_user,
                password=self._settings.db_password.get_secret_value(),
                db=self._settings.db_name,
                minsize=self._minsize,
                maxsize=self._maxsize,
                autocommit=self._autocommit,
                charset=self._charset,
                cursorclass=aiomysql.DictCursor,
                connect_timeout=self._connect_timeout,
            )
            logger.info("MySQL connection pool established successfully.")

    async def close(self) -> None:
        """Close all connections and terminate the pool gracefully."""
        async with self._lock:
            if self._pool is not None:
                logger.info("Closing MySQL connection pool...")
                self._pool.close()
                await self._pool.wait_closed()
                self._pool = None
                logger.info("MySQL connection pool closed.")

    async def _reconnect(self) -> None:
        """Tear down severed pool and establish a fresh connection pool."""
        async with self._lock:
            if self._pool is not None:
                try:
                    self._pool.close()
                    await self._pool.wait_closed()
                except Exception as exc:
                    logger.debug("Error while closing stale pool: %s", exc)
                finally:
                    self._pool = None

            logger.warning("Re-establishing severed MySQL connection pool...")
            self._pool = await aiomysql.create_pool(
                host=self._settings.db_host,
                port=self._settings.db_port,
                user=self._settings.db_user,
                password=self._settings.db_password.get_secret_value(),
                db=self._settings.db_name,
                minsize=self._minsize,
                maxsize=self._maxsize,
                autocommit=self._autocommit,
                charset=self._charset,
                cursorclass=aiomysql.DictCursor,
                connect_timeout=self._connect_timeout,
            )
            logger.info("MySQL connection pool re-established successfully.")

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[aiomysql.Connection]:
        """Acquire a connection from the pool, releasing it safely on completion."""
        if not self.is_connected:
            await self.connect()

        assert self._pool is not None, "Connection pool is not initialized."

        async with self._pool.acquire() as conn:
            yield conn

    async def _execute_with_retry(
        self,
        operation: Callable[[], Coroutine[Any, Any, T]],
    ) -> T:
        """Execute a database operation with transparent pool reconnection on OperationalError."""
        if not self.is_connected:
            await self.connect()

        try:
            return await operation()
        except aiomysql.OperationalError as exc:
            logger.warning(
                "MySQL OperationalError encountered (%s). Reconnecting pool and retrying...",
                exc,
            )
            await self._reconnect()
            return await operation()

    async def fetch_one(
        self,
        query: str,
        params: Any = None,
    ) -> dict[str, Any] | None:
        """Execute query and fetch a single result row as a dictionary."""
        async def _query() -> dict[str, Any] | None:
            async with self.acquire() as conn, conn.cursor() as cur:
                if params is not None:
                    await cur.execute(query, params)
                else:
                    await cur.execute(query)
                row = await cur.fetchone()
                return row if row is not None else None

        return await self._execute_with_retry(_query)

    async def fetch_all(
        self,
        query: str,
        params: Any = None,
    ) -> list[dict[str, Any]]:
        """Execute query and fetch all result rows as a list of dictionaries."""
        async def _query() -> list[dict[str, Any]]:
            async with self.acquire() as conn, conn.cursor() as cur:
                if params is not None:
                    await cur.execute(query, params)
                else:
                    await cur.execute(query)
                rows = await cur.fetchall()
                return list(rows) if rows is not None else []

        return await self._execute_with_retry(_query)

    async def execute(
        self,
        query: str,
        params: Any = None,
    ) -> int:
        """Execute a query statement and return the number of affected rows."""
        async def _query() -> int:
            async with self.acquire() as conn, conn.cursor() as cur:
                if params is not None:
                    await cur.execute(query, params)
                else:
                    await cur.execute(query)
                return int(cur.rowcount)

        return await self._execute_with_retry(_query)

    async def ping(self) -> bool:
        """Check database health and reachability using SELECT 1."""
        try:
            res = await self.fetch_one("SELECT 1")
            return res is not None
        except Exception as exc:
            logger.warning("Database ping health check failed: %s", exc)
            return False


_global_db_manager: DatabaseManager | None = None


def get_db_manager(settings: Settings | None = None) -> DatabaseManager:
    """Return the global or a freshly instantiated DatabaseManager instance."""
    global _global_db_manager
    if _global_db_manager is None:
        _global_db_manager = DatabaseManager(settings=settings)
    return _global_db_manager
