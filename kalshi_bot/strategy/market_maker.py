"""Avellaneda-Stoikov market making strategy adapted for Kalshi binary event markets.

Key defenses against adverse selection:
- EWMA-smoothed fair value (doesn't chase sudden microprice jumps)
- Spread widens with inventory (holding risk costs money)
- Bid always below fair value, ask always above (never buy above value)
- Requote only when price moves significantly (reduces getting picked off
  during cancel-replace window)
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

from kalshi_bot.core.config import StrategyConfig
from kalshi_bot.core.market_data import MarketDataManager, MarketInfo

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    ticker: str
    bid_price: int
    ask_price: int
    bid_size: int
    ask_size: int
    fair_value: float
    spread: float
    inventory_skew: float
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        return (
            1 <= self.bid_price <= 98
            and 2 <= self.ask_price <= 99
            and self.bid_price < self.ask_price
            and self.bid_size > 0
            and self.ask_size > 0
        )


def _reject(ticker, fair_value, reason):
    return Quote(
        ticker=ticker, bid_price=0, ask_price=0,
        bid_size=0, ask_size=0, fair_value=fair_value,
        spread=0, inventory_skew=0, reason=reason,
    )


class MarketMakingStrategy:

    def __init__(self, config: StrategyConfig, market_data: MarketDataManager):
        self.config = config
        self.market_data = market_data
        self.positions: dict[str, int] = {}

    def update_position(self, ticker: str, position: int):
        self.positions[ticker] = position

    def compute_quote(self, ticker: str) -> Optional[Quote]:
        ob = self.market_data.get_orderbook(ticker)
        info = self.market_data.get_market_info(ticker)

        if not ob or ob.best_bid is None or ob.best_ask is None:
            return None

        # Use EWMA-smoothed fair value to avoid chasing
        fair_value = self.market_data.get_smoothed_fair_value(ticker, alpha=0.3)
        if fair_value is None:
            return None

        if fair_value < 5 or fair_value > 95:
            return _reject(ticker, fair_value, "Price too extreme")

        # ── Base half-spread ────────────────────────────────
        # Start from the configured minimum and widen based on conditions
        base_half = self.config.min_spread_cents / 2

        # Widen based on market spread (don't undercut the market too aggressively)
        market_spread = ob.spread or self.config.min_spread_cents
        if market_spread > self.config.min_spread_cents:
            base_half = max(base_half, market_spread / 2 - 1)

        # ── Time decay ──────────────────────────────────────
        if info and info.hours_to_close is not None:
            hours = info.hours_to_close
            if hours < self.config.time_decay_start_hours:
                T = max(0.01, hours / self.config.time_decay_start_hours)
                base_half = base_half / max(T, 0.3)  # widen as close approaches

        # ── Inventory penalty: widen spread with position size ──
        q = self.positions.get(ticker, 0)
        position_ratio = abs(q) / max(self.config.max_position, 1)
        inventory_widen = position_ratio * self.config.max_spread_cents / 2
        half_spread = base_half + inventory_widen

        # Clamp the half-spread
        half_spread = max(
            self.config.min_spread_cents / 2,
            min(self.config.max_spread_cents / 2, half_spread),
        )

        # ── Inventory skew (shift mid toward reducing position) ──
        # Bounded to never push bid above fv or ask below fv
        max_skew = half_spread * 0.6
        gamma = self.config.inventory_risk_aversion
        raw_skew = q * gamma * 0.5  # simple linear skew: 0.5c per contract * gamma
        skew = max(-max_skew, min(max_skew, raw_skew))

        # ── Quote prices ────────────────────────────────────
        mid = fair_value - skew
        raw_bid = mid - half_spread
        raw_ask = mid + half_spread

        # SAFETY: bid < fair_value, ask > fair_value
        bid_price = int(math.floor(min(raw_bid, fair_value - 1)))
        ask_price = int(math.ceil(max(raw_ask, fair_value + 1)))

        # Enforce minimum spread
        if ask_price - bid_price < self.config.min_spread_cents:
            bid_price = int(math.floor(fair_value - self.config.min_spread_cents / 2))
            ask_price = int(math.ceil(fair_value + self.config.min_spread_cents / 2))

        # Max deviation cap
        max_dev = self.config.max_spread_cents
        bid_price = max(bid_price, int(math.floor(fair_value - max_dev)))
        ask_price = min(ask_price, int(math.ceil(fair_value + max_dev)))

        bid_price = max(1, min(98, bid_price))
        ask_price = max(2, min(99, ask_price))

        if bid_price >= ask_price:
            return _reject(ticker, fair_value, "Spread collapsed")
        if bid_price >= fair_value or ask_price <= fair_value:
            return _reject(ticker, fair_value, "Quote crosses fair value")

        # ── Order sizing ────────────────────────────────────
        size_multiplier = max(0.2, 1.0 - position_ratio * 0.8)
        base_size = self.config.order_size

        bid_size = max(1, int(base_size * size_multiplier))
        ask_size = max(1, int(base_size * size_multiplier))

        if q > 0:
            ask_size = max(1, int(ask_size * 1.3))
            bid_size = max(1, int(bid_size * 0.7))
        elif q < 0:
            bid_size = max(1, int(bid_size * 1.3))
            ask_size = max(1, int(ask_size * 0.7))

        bid_size = min(bid_size, self.config.max_order_size)
        ask_size = min(ask_size, self.config.max_order_size)

        return Quote(
            ticker=ticker,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=bid_size,
            ask_size=ask_size,
            fair_value=fair_value,
            spread=ask_price - bid_price,
            inventory_skew=skew,
        )

    def should_requote(self, ticker: str, current_quote: Optional[Quote]) -> bool:
        if current_quote is None:
            return True

        new_quote = self.compute_quote(ticker)
        if new_quote is None:
            return False

        # Only requote if price moved significantly (at least half the spread)
        # This reduces cancel-replace churn which creates adverse selection windows
        threshold = max(2, current_quote.spread // 2)
        bid_diff = abs(new_quote.bid_price - current_quote.bid_price)
        ask_diff = abs(new_quote.ask_price - current_quote.ask_price)

        return bid_diff >= threshold or ask_diff >= threshold
