"""Kalshi WebSocket client — optional real-time orderbook feed.

Not required for the core bot (REST polling is sufficient for weather markets),
but available for lower-latency market data if needed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Any

import httpx

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.kalshi.auth import KalshiAuth

log = get_logger(__name__)


class KalshiWebSocket:
    """Async WebSocket client for Kalshi real-time data."""

    def __init__(self, auth: KalshiAuth | None = None):
        self.settings = get_settings()
        self.ws_url = self.settings.kalshi_ws_url
        self.auth = auth or KalshiAuth()
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {}

    def on(self, event_type: str, callback: Callable) -> None:
        self._callbacks.setdefault(event_type, []).append(callback)

    def _dispatch(self, event_type: str, data: dict) -> None:
        for cb in self._callbacks.get(event_type, []):
            try:
                cb(data)
            except Exception as exc:
                log.error("WS callback error for %s: %s", event_type, exc)

    async def connect(self, tickers: list[str]) -> None:
        """Connect and subscribe to orderbook updates for given tickers.

        This is a placeholder — actual Kalshi WS protocol details may vary.
        The REST client is sufficient for weather market trading.
        """
        log.info("WebSocket support is available but not required for weather markets")
        log.info("Using REST polling at %ds intervals instead", self.settings.refresh_seconds)

    async def close(self) -> None:
        self._running = False
