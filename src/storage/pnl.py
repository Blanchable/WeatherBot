"""P&L calculation helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.storage.db import Database
from src.bot.logging import get_logger

log = get_logger(__name__)


class PnLTracker:
    def __init__(self, db: Database, is_paper: bool = True):
        self.db = db
        self.is_paper = is_paper

    def compute_daily_realized(self) -> float:
        fills = self.db.get_fills_today(self.is_paper)
        total = 0.0
        for f in fills:
            price = f["price_cents"] / 100.0
            qty = f["quantity"]
            fee = f["fee_dollars"]
            if f["action"] == "buy":
                total -= price * qty + fee
            else:
                total += price * qty - fee
        return total

    def compute_unrealized(self, mark_prices: dict[str, float]) -> float:
        """mark_prices: ticker -> mid price in cents."""
        positions = self.db.get_positions(self.is_paper)
        total = 0.0
        for p in positions:
            ticker = p["ticker"]
            if ticker not in mark_prices:
                continue
            mark = mark_prices[ticker] / 100.0
            avg = p["avg_price_cents"] / 100.0
            qty = p["quantity"]
            if p["side"] == "yes":
                total += (mark - avg) * qty
            else:
                total += ((1.0 - mark) - (1.0 - avg)) * qty
        return total

    def total_fees_today(self) -> float:
        fills = self.db.get_fills_today(self.is_paper)
        return sum(f["fee_dollars"] for f in fills)

    def sync_daily(self, mark_prices: dict[str, float] | None = None) -> dict:
        realized = self.compute_daily_realized()
        fees = self.total_fees_today()
        fills = self.db.get_fills_today(self.is_paper)
        positions = self.db.get_positions(self.is_paper)
        self.db.update_daily_pnl(
            realized_pnl=realized,
            fees_paid=fees,
            num_trades=len(fills),
            num_markets=len(set(f["ticker"] for f in fills)),
            is_paper=self.is_paper,
        )
        return {
            "realized_pnl": realized,
            "unrealized_pnl": self.compute_unrealized(mark_prices or {}),
            "fees": fees,
            "num_fills": len(fills),
            "num_positions": len(positions),
        }
