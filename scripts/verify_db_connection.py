"""Verification script to test live MySQL database connectivity using DatabaseManager."""

import asyncio
import sys

from app.config import get_settings
from app.upstream.database import DatabaseManager


async def verify() -> None:
    print("=" * 60)
    print(" OryxGate Live MySQL Connection Verification")
    print("=" * 60)

    try:
        get_settings.cache_clear()
        settings = get_settings()
    except Exception as exc:
        print(f"\n[ERROR] Failed to load configuration from .env: {exc}")
        sys.exit(1)

    print(f"Host:     {settings.db_host}:{settings.db_port}")
    print(f"User:     {settings.db_user}")
    print(f"Database: {settings.db_name}")
    print(f"Password: {'*' * len(settings.db_password.get_secret_value())}")
    print("-" * 60)

    db = DatabaseManager(settings=settings)
    try:
        print("[1/3] Establishing connection pool...")
        await db.connect()
        print("  -> Connected successfully!")

        print("[2/3] Testing ping (SELECT 1)...")
        ping_ok = await db.ping()
        if ping_ok:
            print("  -> Ping successful: Database is alive and responsive.")
        else:
            print("  -> Ping failed!")
            sys.exit(1)

        print("[3/3] Inspecting available database tables...")
        tables = await db.fetch_all("SHOW TABLES")
        table_names = [list(t.values())[0] for t in tables]
        print(f"  -> Found {len(table_names)} table(s):")
        for name in sorted(table_names):
            marker = " [Expected]" if name in ("pilots", "live_if_oauth_tokens", "pireps") else ""
            print(f"     - {name}{marker}")

        print("=" * 60)
        print(" SUCCESS: Database connection verified and ready!")
        print("=" * 60)
    except Exception as exc:
        print(f"\n[FAILURE] Database connection failed: {exc}")
        sys.exit(1)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(verify())
