"""Tooling and environment configuration unit tests."""

import importlib
import sys


def test_python_version() -> None:
    """Ensure runtime Python version meets requirement >= 3.11."""
    assert sys.version_info >= (3, 11), f"Python >= 3.11 required, got {sys.version_info}"


def test_required_dependencies_importable() -> None:
    """Verify that all core and dev dependencies specified in TASK-1.1 are importable."""
    required_packages = [
        "fastapi",
        "uvicorn",
        "orjson",
        "pydantic",
        "pydantic_settings",
        "aiohttp",
        "aiomysql",
        "pytest",
        "pytest_asyncio",
        "respx",
        "ruff",
        "mypy",
    ]
    for package in required_packages:
        mod = importlib.import_module(package)
        assert mod is not None, f"Failed to import required package: {package}"


def test_app_package_structure() -> None:
    """Verify app package is importable and defines version."""
    import app

    assert hasattr(app, "__version__")
    assert app.__version__ == "0.1.0"
