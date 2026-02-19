"""Central configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # ── Kalshi API ──────────────────────────────────────────
    kalshi_env: Literal["prod", "demo"] = "prod"
    kalshi_rest_base: str = "https://api.elections.kalshi.com/trade-api/v2"
    kalshi_ws_url: str = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    kalshi_key_id: str = ""
    kalshi_private_key_path: str = ""

    live_trading: bool = False

    # ── Bot ─────────────────────────────────────────────────
    bot_mode: str = "weather"
    cities: str = "NYC,LA,CHI"

    refresh_seconds: int = 20
    no_trade_window_seconds: int = 21600
    exit_only_window_seconds: int = 10800

    # ── Market filters ──────────────────────────────────────
    min_spread_cents: int = 6
    min_24h_volume: int = 500
    max_markets: int = 8

    # ── Bankroll / exposure ─────────────────────────────────
    start_bankroll_dollars: float = 1400.0
    max_gross_exposure_dollars: float = 250.0
    max_net_exposure_dollars: float = 150.0
    max_exposure_per_city_dollars: float = 125.0
    max_exposure_per_market_dollars: float = 75.0
    max_order_size_contracts: int = 10

    # ── Edge / EV ───────────────────────────────────────────
    min_ev_dollars_per_contract: float = 0.02
    take_profit_cents: int = 4
    stop_loss_cents: int = 6

    # ── Forecast staleness ──────────────────────────────────
    forecast_stale_minutes_same_day: int = 30
    forecast_stale_minutes_next_day: int = 180

    # ── Daily P&L ───────────────────────────────────────────
    daily_stop_loss_dollars: float = 50.0
    daily_take_profit_dollars: float = 40.0

    # ── Execution ───────────────────────────────────────────
    maker_only: bool = True

    # ── Sigma (forecast uncertainty by horizon) ─────────────
    sigma_same_day: float = 1.25
    sigma_next_day: float = 2.0
    sigma_2plus_day: float = 3.0

    model_config = {
        "env_file": str(_ENV_FILE) if _ENV_FILE.exists() else None,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def city_list(self) -> list[str]:
        return [c.strip().upper() for c in self.cities.split(",") if c.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = Settings()
    return _settings
