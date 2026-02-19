"""Configuration management for the Kalshi Market Making Bot."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".kalshi_bot"
CONFIG_FILE = CONFIG_DIR / "config.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"


@dataclass
class ApiConfig:
    base_url: str = "https://demo-api.kalshi.co/trade-api/v2"
    ws_url: str = "wss://demo-api.kalshi.co/trade-api/ws/v2"
    use_demo: bool = True

    def set_environment(self, demo: bool):
        self.use_demo = demo
        if demo:
            self.base_url = "https://demo-api.kalshi.co/trade-api/v2"
            self.ws_url = "wss://demo-api.kalshi.co/trade-api/ws/v2"
        else:
            self.base_url = "https://trading-api.kalshi.com/trade-api/v2"
            self.ws_url = "wss://trading-api.kalshi.com/trade-api/ws/v2"


@dataclass
class StrategyConfig:
    # Spread parameters
    min_spread_cents: int = 3
    max_spread_cents: int = 15
    base_spread_cents: int = 5

    # Inventory management (Avellaneda-Stoikov gamma parameter)
    inventory_risk_aversion: float = 0.3
    max_position: int = 50
    target_position: int = 0

    # Order sizing
    order_size: int = 5
    max_order_size: int = 20

    # Timing
    quote_refresh_seconds: float = 5.0
    order_lifetime_seconds: float = 30.0

    # Volatility estimation
    volatility_lookback: int = 50
    volatility_floor: float = 0.05
    volatility_cap: float = 0.50

    # Edge thresholds - don't quote if spread would be negative edge
    min_edge_cents: int = 1

    # Time decay: widen spread as expiry approaches (hours)
    time_decay_start_hours: float = 2.0


@dataclass
class RiskConfig:
    max_daily_loss_cents: int = 5000  # $50
    max_position_value_cents: int = 25000  # $250
    max_open_orders: int = 20
    kill_switch_loss_cents: int = 10000  # $100 hard stop
    max_single_market_position: int = 100


@dataclass
class MarketConfig:
    # Which series/event tickers to trade
    target_series: list = field(default_factory=lambda: ["KXHIGHNY"])
    auto_select_markets: bool = True
    min_market_volume: int = 50
    min_market_open_interest: int = 20
    # Only trade markets expiring within this window (hours)
    max_hours_to_expiry: float = 72.0
    min_hours_to_expiry: float = 0.5


@dataclass
class BotConfig:
    api: ApiConfig = field(default_factory=ApiConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    market: MarketConfig = field(default_factory=MarketConfig)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "BotConfig":
        if not CONFIG_FILE.exists():
            return cls()
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            config = cls()
            if "api" in data:
                for k, v in data["api"].items():
                    if hasattr(config.api, k):
                        setattr(config.api, k, v)
            if "strategy" in data:
                for k, v in data["strategy"].items():
                    if hasattr(config.strategy, k):
                        setattr(config.strategy, k, v)
            if "risk" in data:
                for k, v in data["risk"].items():
                    if hasattr(config.risk, k):
                        setattr(config.risk, k, v)
            if "market" in data:
                for k, v in data["market"].items():
                    if hasattr(config.market, k):
                        setattr(config.market, k, v)
            return config
        except (json.JSONDecodeError, KeyError):
            return cls()


@dataclass
class Credentials:
    api_key_id: str = ""
    private_key_path: str = ""

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(asdict(self), f)
        os.chmod(CREDENTIALS_FILE, 0o600)

    @classmethod
    def load(cls) -> "Credentials":
        if not CREDENTIALS_FILE.exists():
            return cls()
        try:
            with open(CREDENTIALS_FILE) as f:
                data = json.load(f)
            # Ignore legacy email/password fields
            filtered = {k: v for k, v in data.items() if k in ("api_key_id", "private_key_path")}
            return cls(**filtered)
        except (json.JSONDecodeError, KeyError, TypeError):
            return cls()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key_id and self.private_key_path)

    def load_private_key(self):
        """Load and return the RSA private key object, or None on failure."""
        if not self.private_key_path:
            return None
        key_path = Path(self.private_key_path)
        if not key_path.exists():
            return None
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            with open(key_path, "rb") as f:
                return load_pem_private_key(f.read(), password=None)
        except Exception:
            return None
