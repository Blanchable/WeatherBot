"""Exit strategy management — time-based, model-based, and P&L-based exits."""

from __future__ import annotations

from datetime import datetime, timezone

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.strategy.market_discovery import WeatherMarketMeta

log = get_logger(__name__)


def is_exit_only_mode(meta: WeatherMarketMeta) -> bool:
    """Check if market is in exit-only window (no new positions)."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    try:
        close_dt = datetime.fromisoformat(meta.close_time.replace("Z", "+00:00"))
        secs_to_close = (close_dt - now).total_seconds()
        return secs_to_close < settings.exit_only_window_seconds
    except (ValueError, TypeError):
        return False


def is_no_trade_window(meta: WeatherMarketMeta) -> bool:
    """Check if within the no-new-trade window."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    try:
        close_dt = datetime.fromisoformat(meta.close_time.replace("Z", "+00:00"))
        secs_to_close = (close_dt - now).total_seconds()
        return secs_to_close < settings.no_trade_window_seconds
    except (ValueError, TypeError):
        return False


def force_flat_check(meta: WeatherMarketMeta) -> bool:
    """Return True if we should force-flatten all positions (1h before close)."""
    now = datetime.now(timezone.utc)
    try:
        close_dt = datetime.fromisoformat(meta.close_time.replace("Z", "+00:00"))
        secs_to_close = (close_dt - now).total_seconds()
        return secs_to_close < 3600
    except (ValueError, TypeError):
        return False
