"""Shared test fixtures for the harness-agent test suite."""

import pytest


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for all async tests."""
    return "asyncio"
