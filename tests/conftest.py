"""Shared test fixtures."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    """Ensure tests don't load any real .env file and use safe defaults."""
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_KEY_ID", "test-key")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "/tmp/nonexistent.pem")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("CITIES", "NYC,LA,CHI")

    from src.bot.config import reload_settings
    reload_settings()
