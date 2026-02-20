"""Risk management - position limits, P&L tracking, and kill switch."""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from kalshi_bot.core.config import RiskConfig
from kalshi_bot.core.api import KalshiApiClient

logger = logging.getLogger(__name__)


@dataclass
class PositionEntry:
    ticker: str
    net_position: int = 0  # positive = long YES
    avg_cost: float = 0.0
    realized_pnl_cents: int = 0
    unrealized_pnl_cents: int = 0


class RiskManager:
    """Monitors and enforces risk limits."""

    def __init__(self, config: RiskConfig, api: KalshiApiClient):
        self.config = config
        self.api = api
        self.positions: dict[str, PositionEntry] = {}
        self.daily_pnl_cents: int = 0
        self.starting_balance: Optional[int] = None
        self.current_balance: Optional[int] = None
        self.kill_switch_triggered = False
        self.kill_switch_reason: str = ""
        self._lock = threading.RLock()
        self._callbacks: list = []

    def register_kill_switch_callback(self, callback):
        self._callbacks.append(callback)

    def sync_positions(self):
        """Sync positions from exchange."""
        try:
            api_positions = self.api.get_positions()
            balance = self.api.get_balance()

            with self._lock:
                if self.starting_balance is None and balance is not None:
                    self.starting_balance = balance
                self.current_balance = balance

                new_positions = {}
                for pos in api_positions:
                    ticker = pos.get("ticker", "")
                    if not ticker:
                        continue
                    entry = PositionEntry(
                        ticker=ticker,
                        net_position=pos.get("position", 0),
                        realized_pnl_cents=pos.get("realized_pnl", 0),
                    )
                    # Estimate unrealized P&L
                    market_price = pos.get("market_price")
                    if market_price and entry.net_position != 0:
                        entry.unrealized_pnl_cents = int(
                            entry.net_position * (market_price - pos.get("average_price", market_price))
                        )
                    new_positions[ticker] = entry
                self.positions = new_positions

                if self.starting_balance and balance:
                    self.daily_pnl_cents = balance - self.starting_balance

        except Exception as e:
            logger.error("Failed to sync positions: %s", e)

    def check_limits(self) -> tuple[bool, str]:
        """Check if any risk limits are breached. Returns (is_ok, reason)."""
        with self._lock:
            # Kill switch already triggered
            if self.kill_switch_triggered:
                return False, self.kill_switch_reason

            # Max daily loss
            if self.daily_pnl_cents < -self.config.max_daily_loss_cents:
                reason = f"Daily loss limit breached: {self.daily_pnl_cents}c < -{self.config.max_daily_loss_cents}c"
                self._trigger_kill_switch(reason)
                return False, reason

            # Hard kill switch
            if self.daily_pnl_cents < -self.config.kill_switch_loss_cents:
                reason = f"Kill switch loss: {self.daily_pnl_cents}c"
                self._trigger_kill_switch(reason)
                return False, reason

            # Position limits
            for ticker, entry in self.positions.items():
                if abs(entry.net_position) > self.config.max_single_market_position:
                    reason = f"Position limit on {ticker}: {entry.net_position} > {self.config.max_single_market_position}"
                    return False, reason

            # Total position value
            total_position_value = sum(
                abs(e.net_position) * 50  # rough estimate: avg 50c per contract
                for e in self.positions.values()
            )
            if total_position_value > self.config.max_position_value_cents:
                reason = f"Total position value {total_position_value}c > {self.config.max_position_value_cents}c"
                return False, reason

        return True, "OK"

    def can_place_order(self, ticker: str, size: int, is_bid: bool) -> tuple[bool, str]:
        """Check if a new order is allowed given current risk state."""
        with self._lock:
            if self.kill_switch_triggered:
                return False, "Kill switch active"

            pos = self.positions.get(ticker, PositionEntry(ticker=ticker))
            projected = pos.net_position + (size if is_bid else -size)

            if abs(projected) > self.config.max_single_market_position:
                return False, f"Would exceed position limit: {projected}"

        ok, reason = self.check_limits()
        return ok, reason

    def get_net_position(self, ticker: str) -> int:
        with self._lock:
            entry = self.positions.get(ticker)
            return entry.net_position if entry else 0

    def get_total_pnl(self) -> int:
        with self._lock:
            return self.daily_pnl_cents

    def get_total_position_count(self) -> int:
        with self._lock:
            return sum(abs(e.net_position) for e in self.positions.values())

    def _trigger_kill_switch(self, reason: str):
        self.kill_switch_triggered = True
        self.kill_switch_reason = reason
        logger.critical("KILL SWITCH TRIGGERED: %s", reason)
        for cb in self._callbacks:
            try:
                cb(reason)
            except Exception:
                pass

    def reset_kill_switch(self):
        with self._lock:
            self.kill_switch_triggered = False
            self.kill_switch_reason = ""
            logger.info("Kill switch reset")

    def reset_daily(self):
        with self._lock:
            self.starting_balance = self.current_balance
            self.daily_pnl_cents = 0
