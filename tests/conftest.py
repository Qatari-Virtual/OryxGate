"""Shared pytest fixtures and test configuration for OryxGate."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Fixture to configure anyio/asyncio backend."""
    return "asyncio"
