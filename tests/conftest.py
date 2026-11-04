"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from .helpers import FakeOllama, register_feeds


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/briefly in every test."""


@pytest.fixture(autouse=True)
def image_cache_tmp(tmp_path) -> Generator[None]:
    """Keep the image cache inside the test's temp dir."""
    with patch(
        "custom_components.briefly.image_proxy.image_cache_dir",
        return_value=tmp_path / "images",
    ), patch(
        "custom_components.briefly.coordinator.image_cache_dir",
        return_value=tmp_path / "images",
    ):
        yield


@pytest.fixture
def feeds(aioclient_mock):
    """Register the standard feeds and articles."""
    register_feeds(aioclient_mock)
    return aioclient_mock


@pytest.fixture
def ollama(aioclient_mock) -> FakeOllama:
    """A fake Ollama server."""
    return FakeOllama(aioclient_mock)

