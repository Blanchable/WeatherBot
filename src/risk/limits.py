"""Risk limit checks — exposure caps, daily P&L stops."""

from __future__ import annotations

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.storage.db import Database
from src.storage.pnl import PnLTracker

log = get_logger(__name__)


class RiskLimits:
    def __init__(self, db: Database, is_paper: bool = True):
        self.db = db
        self.is_paper = is_paper
        self.settings = get_settings()
        self.pnl_tracker = PnLTracker(db, is_paper)

    def check_daily_stop(self) -> bool:
        """Returns True if daily stop-loss has been hit."""
        realized = self.pnl_tracker.compute_daily_realized()
        if realized <= -self.settings.daily_stop_loss_dollars:
            log.warning("DAILY STOP-LOSS hit: realized=$%.2f", realized)
            return True
        return False

    def check_daily_take_profit(self) -> bool:
        """Returns True if daily take-profit has been hit."""
        realized = self.pnl_tracker.compute_daily_realized()
        if realized >= self.settings.daily_take_profit_dollars:
            log.info("DAILY TAKE-PROFIT hit: realized=$%.2f", realized)
            return True
        return False

    def check_gross_exposure(self) -> float:
        """Return current gross exposure in dollars."""
        positions = self.db.get_positions(self.is_paper)
        orders = self.db.get_open_orders(self.is_paper)
        total = 0.0
        for p in positions:
            total += abs(p["quantity"] * p["avg_price_cents"] / 100.0)
        for o in orders:
            total += abs(o["quantity"] * o["price_cents"] / 100.0)
        return total

    def is_within_limits(self) -> bool:
        """Check all risk limits. Returns True if OK to trade."""
        if self.check_daily_stop():
            return False
        if self.check_daily_take_profit():
            return False
        gross = self.check_gross_exposure()
        if gross >= self.settings.max_gross_exposure_dollars:
            log.warning("Gross exposure $%.2f >= limit $%.2f", gross, self.settings.max_gross_exposure_dollars)
            return False
        return True

    def exposure_summary(self) -> dict:
        """Return a summary of current exposure."""
        positions = self.db.get_positions(self.is_paper)
        orders = self.db.get_open_orders(self.is_paper)

        gross = 0.0
        net = 0.0
        by_city: dict[str, float] = {}
        by_market: dict[str, float] = {}

        for p in positions:
            exp = p["quantity"] * p["avg_price_cents"] / 100.0
            gross += abs(exp)
            net += exp if p["side"] == "yes" else -exp

            mkt = self.db.conn.execute(
                "SELECT city FROM weather_markets WHERE ticker = ?", (p["ticker"],)
            ).fetchone()
            city = mkt["city"] if mkt else "unknown"
            by_city[city] = by_city.get(city, 0) + abs(exp)
            by_market[p["ticker"]] = by_market.get(p["ticker"], 0) + abs(exp)

        return {
            "gross_exposure": gross,
            "net_exposure": net,
            "by_city": by_city,
            "by_market": by_market,
            "open_orders": len(orders),
            "open_positions": len(positions),
        }
