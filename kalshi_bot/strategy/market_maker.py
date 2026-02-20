"""Trend-aware market making strategy for Kalshi binary event markets.

Key principles:
- Don't buy into a falling market, don't sell into a rising market
- EWMA-smoothed fair value resists chasing sudden moves
- Spread widens with inventory to penalize holding risk
- Bid always below fair value, ask always above
- Asymmetric quoting: skip the side that's getting adversely selected
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
    skip_bid: bool = False
    skip_ask: bool = False
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        if self.skip_bid and self.skip_ask:
            return False
        if self.skip_bid:
            return 2 <= self.ask_price <= 99 and self.ask_size > 0
        if self.skip_ask:
            return 1 <= self.bid_price <= 98 and self.bid_size > 0
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
        self._fair_value_history: dict[str, list[float]] = {}

    def update_position(self, ticker: str, position: int):
        self.positions[ticker] = position

    def _detect_trend(self, ticker: str, current_fv: float) -> str:
        """Detect short-term price trend. Returns 'up', 'down', or 'flat'."""
        history = self._fair_value_history.get(ticker, [])
        history.append(current_fv)
        if len(history) > 10:
            history = history[-10:]
        self._fair_value_history[ticker] = history

        if len(history) < 4:
            return "flat"

        # Compare current to average of older values
        old_avg = sum(history[:-2]) / len(history[:-2])
        move = current_fv - old_avg

        # Threshold: 2c move counts as a trend
        if move > 2.0:
            return "up"
        elif move < -2.0:
            return "down"
        return "flat"

    def _get_book_imbalance(self, ticker: str) -> float:
        """Order book imbalance: >0 means buy pressure, <0 means sell pressure."""
        ob = self.market_data.get_orderbook(ticker)
        if not ob:
            return 0.0
        bid_depth = ob.bid_depth or 1
        ask_depth = ob.ask_depth or 1
        return (bid_depth - ask_depth) / (bid_depth + ask_depth)

    def compute_quote(self, ticker: str) -> Optional[Quote]:
        ob = self.market_data.get_orderbook(ticker)
        info = self.market_data.get_market_info(ticker)

        if not ob or ob.best_bid is None or ob.best_ask is None:
            return None

        fair_value = self.market_data.get_smoothed_fair_value(ticker, alpha=0.3)
        if fair_value is None:
            return None

        if fair_value < 5 or fair_value > 95:
            return _reject(ticker, fair_value, "Price too extreme")

        # ── Trend detection ─────────────────────────────────
        trend = self._detect_trend(ticker, fair_value)
        imbalance = self._get_book_imbalance(ticker)

        skip_bid = False
        skip_ask = False

        # Don't buy into a falling market
        if trend == "down":
            skip_bid = True
        # Don't sell into a rising market
        elif trend == "up":
            skip_ask = True

        # Also use order book imbalance as confirmation
        # Strong sell imbalance (lots on ask side) → don't bid
        if imbalance < -0.4:
            skip_bid = True
        # Strong buy imbalance → don't ask
        elif imbalance > 0.4:
            skip_ask = True

        # But always allow the side that REDUCES inventory
        q = self.positions.get(ticker, 0)
        if q > 2 and skip_ask:
            skip_ask = False  # need to sell to reduce long
        if q < -2 and skip_bid:
            skip_bid = False  # need to buy to reduce short

        # ── Base half-spread ────────────────────────────────
        base_half = self.config.min_spread_cents / 2

        market_spread = ob.spread or self.config.min_spread_cents
        if market_spread > self.config.min_spread_cents:
            base_half = max(base_half, market_spread / 2 - 1)

        # ── Time decay ──────────────────────────────────────
        if info and info.hours_to_close is not None:
            hours = info.hours_to_close
            if hours < self.config.time_decay_start_hours:
                T = max(0.01, hours / self.config.time_decay_start_hours)
                base_half = base_half / max(T, 0.3)

        # ── Inventory spread penalty ────────────────────────
        position_ratio = abs(q) / max(self.config.max_position, 1)
        inventory_widen = position_ratio * self.config.max_spread_cents / 2
        half_spread = base_half + inventory_widen

        half_spread = max(
            self.config.min_spread_cents / 2,
            min(self.config.max_spread_cents / 2, half_spread),
        )

        # ── Inventory skew ──────────────────────────────────
        max_skew = half_spread * 0.6
        gamma = self.config.inventory_risk_aversion
        raw_skew = q * gamma * 0.5
        skew = max(-max_skew, min(max_skew, raw_skew))

        # ── Quote prices ────────────────────────────────────
        mid = fair_value - skew
        raw_bid = mid - half_spread
        raw_ask = mid + half_spread

        bid_price = int(math.floor(min(raw_bid, fair_value - 1)))
        ask_price = int(math.ceil(max(raw_ask, fair_value + 1)))

        if ask_price - bid_price < self.config.min_spread_cents:
            bid_price = int(math.floor(fair_value - self.config.min_spread_cents / 2))
            ask_price = int(math.ceil(fair_value + self.config.min_spread_cents / 2))

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
            skip_bid=skip_bid,
            skip_ask=skip_ask,
        )

    def should_requote(self, ticker: str, current_quote: Optional[Quote]) -> bool:
        if current_quote is None:
            return True

        new_quote = self.compute_quote(ticker)
        if new_quote is None:
            return False

        # Requote if trend changed (need to add/remove a side)
        if new_quote.skip_bid != current_quote.skip_bid:
            return True
        if new_quote.skip_ask != current_quote.skip_ask:
            return True

        threshold = max(2, current_quote.spread // 2)
        bid_diff = abs(new_quote.bid_price - current_quote.bid_price)
        ask_diff = abs(new_quote.ask_price - current_quote.ask_price)

        return bid_diff >= threshold or ask_diff >= threshold
