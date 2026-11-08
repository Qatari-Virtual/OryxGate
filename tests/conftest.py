"""Shared pytest fixtures and test configuration for OryxGate."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    """Fixture to configure anyio/asyncio backend."""
    return "asyncio"


@pytest.fixture
def test_settings() -> Settings:
    """Provide standard test Settings instance with preconfigured keys and tokens."""
    return Settings(
        gateway_api_tokens="gw_test_token_alpha, gw_test_token_beta",
        admin_api_tokens="admin_test_token_master",
        if_api_key="if_test_key_12345",
        if_organization_id="e9b25123-0000-0000-0000-000000000000",
        cc_api_key="cc_test_key_67890",
        cc_api_base_url="https://crew.qatarairwaysvirtual.com/api",
        db_host="127.0.0.1",
        db_user="test_user",
        db_password="test_password",
        db_name="test_db",
        _env_file=None,
    )


@pytest.fixture
def test_app(test_settings: Settings) -> FastAPI:
    """Create a FastAPI application configured with test settings."""
    return create_app(settings=test_settings)


@pytest.fixture
async def async_client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Provide an httpx.AsyncClient bound to test_app via ASGITransport."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as client:
        yield client

