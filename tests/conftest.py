"""Pytest configuration and fixtures."""
import pytest


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure async backend for pytest-asyncio."""
    return "asyncio"
