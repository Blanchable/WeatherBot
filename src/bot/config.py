"""Configuration loading for the weather bot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _parse_float(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _parse_list(value: str | None, default: list[str]) -> list[str]:
    if value is None or value.strip() == "":
        return default
    return [part.strip().upper() for part in value.split(",") if part.strip()]


@dataclass(slots=True)
class BotConfig:
    kalshi_env: str = "prod"
    kalshi_rest_base: str = "https://api.elections.kalshi.com/trade-api/v2"
    kalshi_ws_url: str = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    kalshi_key_id: str = ""
    kalshi_private_key_path: str = ""
    live_trading: bool = False

    bot_mode: str = "weather"
    cities: list[str] = field(default_factory=lambda: ["NYC", "LA", "CHI"])

    refresh_seconds: int = 20
    no_trade_window_seconds: int = 21600
    exit_only_window_seconds: int = 10800

    min_spread_cents: int = 6
    min_24h_volume: int = 500
    max_markets: int = 8

    start_bankroll_dollars: float = 1400.0
    max_gross_exposure_dollars: float = 250.0
    max_net_exposure_dollars: float = 150.0
    max_exposure_per_city_dollars: float = 125.0
    max_exposure_per_market_dollars: float = 75.0
    max_order_size_contracts: int = 10

    min_ev_dollars_per_contract: float = 0.02
    take_profit_cents: int = 4
    stop_loss_cents: int = 6
    edge_buffer_cents: int = 2
    model_flip_ev_threshold: float = -0.02

    forecast_stale_minutes_same_day: int = 30
    forecast_stale_minutes_next_day: int = 180

    daily_stop_loss_dollars: float = 50.0
    daily_take_profit_dollars: float = 40.0
    maker_only: bool = True

    api_error_limit: int = 10
    api_error_window_seconds: int = 300

    sqlite_path: str = "weather_bot.db"
    log_level: str = "INFO"

    sigma_same_day: float = 1.25
    sigma_next_day: float = 2.0
    sigma_two_plus_day: float = 2.8

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "BotConfig":
        load_dotenv(env_file)
        return cls(
            kalshi_env=os.getenv("KALSHI_ENV", "prod"),
            kalshi_rest_base=os.getenv(
                "KALSHI_REST_BASE",
                "https://api.elections.kalshi.com/trade-api/v2",
            ),
            kalshi_ws_url=os.getenv(
                "KALSHI_WS_URL",
                "wss://api.elections.kalshi.com/trade-api/ws/v2",
            ),
            kalshi_key_id=os.getenv("KALSHI_KEY_ID", ""),
            kalshi_private_key_path=os.getenv("KALSHI_PRIVATE_KEY_PATH", ""),
            live_trading=_parse_bool(os.getenv("LIVE_TRADING"), False),
            bot_mode=os.getenv("BOT_MODE", "weather"),
            cities=_parse_list(os.getenv("CITIES"), ["NYC", "LA", "CHI"]),
            refresh_seconds=_parse_int(os.getenv("REFRESH_SECONDS"), 20),
            no_trade_window_seconds=_parse_int(
                os.getenv("NO_TRADE_WINDOW_SECONDS"),
                21600,
            ),
            exit_only_window_seconds=_parse_int(
                os.getenv("EXIT_ONLY_WINDOW_SECONDS"),
                10800,
            ),
            min_spread_cents=_parse_int(os.getenv("MIN_SPREAD_CENTS"), 6),
            min_24h_volume=_parse_int(os.getenv("MIN_24H_VOLUME"), 500),
            max_markets=_parse_int(os.getenv("MAX_MARKETS"), 8),
            start_bankroll_dollars=_parse_float(
                os.getenv("START_BANKROLL_DOLLARS"),
                1400.0,
            ),
            max_gross_exposure_dollars=_parse_float(
                os.getenv("MAX_GROSS_EXPOSURE_DOLLARS"),
                250.0,
            ),
            max_net_exposure_dollars=_parse_float(
                os.getenv("MAX_NET_EXPOSURE_DOLLARS"),
                150.0,
            ),
            max_exposure_per_city_dollars=_parse_float(
                os.getenv("MAX_EXPOSURE_PER_CITY_DOLLARS"),
                125.0,
            ),
            max_exposure_per_market_dollars=_parse_float(
                os.getenv("MAX_EXPOSURE_PER_MARKET_DOLLARS"),
                75.0,
            ),
            max_order_size_contracts=_parse_int(
                os.getenv("MAX_ORDER_SIZE_CONTRACTS"),
                10,
            ),
            min_ev_dollars_per_contract=_parse_float(
                os.getenv("MIN_EV_DOLLARS_PER_CONTRACT"),
                0.02,
            ),
            take_profit_cents=_parse_int(os.getenv("TAKE_PROFIT_CENTS"), 4),
            stop_loss_cents=_parse_int(os.getenv("STOP_LOSS_CENTS"), 6),
            forecast_stale_minutes_same_day=_parse_int(
                os.getenv("FORECAST_STALE_MINUTES_SAME_DAY"),
                30,
            ),
            forecast_stale_minutes_next_day=_parse_int(
                os.getenv("FORECAST_STALE_MINUTES_NEXT_DAY"),
                180,
            ),
            daily_stop_loss_dollars=_parse_float(
                os.getenv("DAILY_STOP_LOSS_DOLLARS"),
                50.0,
            ),
            daily_take_profit_dollars=_parse_float(
                os.getenv("DAILY_TAKE_PROFIT_DOLLARS"),
                40.0,
            ),
            maker_only=_parse_bool(os.getenv("MAKER_ONLY"), True),
            sqlite_path=os.getenv("SQLITE_PATH", "weather_bot.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            sigma_same_day=_parse_float(os.getenv("SIGMA_SAME_DAY"), 1.25),
            sigma_next_day=_parse_float(os.getenv("SIGMA_NEXT_DAY"), 2.0),
            sigma_two_plus_day=_parse_float(
                os.getenv("SIGMA_TWO_PLUS_DAY"),
                2.8,
            ),
        )

    def with_overrides(self, **kwargs: Any) -> "BotConfig":
        data = {field_name: getattr(self, field_name) for field_name in self.__dataclass_fields__}  # type: ignore[attr-defined]
        data.update({k: v for k, v in kwargs.items() if v is not None})
        return BotConfig(**data)

    def horizon_sigma(self, days_out: int) -> float:
        if days_out <= 0:
            return self.sigma_same_day
        if days_out == 1:
            return self.sigma_next_day
        return self.sigma_two_plus_day

