"""Avellaneda-Stoikov market making strategy adapted for Kalshi binary event markets.

The strategy:
1. Estimates fair value from microprice (volume-weighted mid)
2. Computes optimal spread using Avellaneda-Stoikov framework
3. Adjusts quotes for inventory risk (skews away from accumulated position)
4. Widens spread near expiry or during high volatility
5. Places bid/ask quotes around the reservation price

SAFETY: Bid is always below fair value, ask is always above fair value.
The bot never buys above or sells below what it thinks the contract is worth.
"""

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

from kalshi_bot.core.config import StrategyConfig
from kalshi_bot.core.market_data import MarketDataManager, MarketInfo

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    """A proposed bid/ask quote pair."""
    ticker: str
    bid_price: int  # cents, YES side
    ask_price: int  # cents, YES side (maps to a NO bid at 100 - ask_price)
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
    """Avellaneda-Stoikov market maker for binary event contracts."""

    def __init__(self, config: StrategyConfig, market_data: MarketDataManager):
        self.config = config
        self.market_data = market_data
        self.positions: dict[str, int] = {}

    def update_position(self, ticker: str, position: int):
        self.positions[ticker] = position

    def compute_quote(self, ticker: str) -> Optional[Quote]:
        """Compute optimal bid/ask quote for a market."""
        ob = self.market_data.get_orderbook(ticker)
        info = self.market_data.get_market_info(ticker)

        if not ob or ob.best_bid is None or ob.best_ask is None:
            return None

        fair_value = self.market_data.get_microprice(ticker)
        if fair_value is None:
            fair_value = ob.mid_price
        if fair_value is None:
            return None

        if fair_value < 5 or fair_value > 95:
            return _reject(ticker, fair_value, "Price too extreme")

        # ── Volatility ──────────────────────────────────────
        sigma = self.market_data.estimate_volatility(ticker, self.config.volatility_lookback)
        sigma = max(self.config.volatility_floor, min(self.config.volatility_cap, sigma))

        # ── Time factor ─────────────────────────────────────
        T = 1.0
        if info and info.hours_to_close is not None:
            hours = info.hours_to_close
            if hours < self.config.time_decay_start_hours:
                T = max(0.01, hours / self.config.time_decay_start_hours)

        # ── Spread calculation ──────────────────────────────
        gamma = self.config.inventory_risk_aversion
        sigma_cents = sigma * 100
        k = self._estimate_arrival_intensity(ticker)

        spread_component = gamma * (sigma_cents ** 2) * T / 200
        liquidity_component = (1 / max(gamma, 0.01)) * math.log(1 + gamma / max(k, 0.1))
        optimal_half_spread = spread_component + liquidity_component

        half_spread = max(
            self.config.min_spread_cents / 2,
            min(self.config.max_spread_cents / 2, optimal_half_spread),
        )

        # ── Inventory skew (bounded) ────────────────────────
        # Shift the mid-point away from inventory to encourage fills
        # that reduce position. Capped to never exceed half the spread
        # so bid stays below fair value and ask stays above.
        q = self.positions.get(ticker, 0)

        max_skew = half_spread * 0.8
        raw_skew = q * gamma * sigma_cents * T / 100
        skew = max(-max_skew, min(max_skew, raw_skew))

        # ── Quote prices ────────────────────────────────────
        mid = fair_value - skew
        raw_bid = mid - half_spread
        raw_ask = mid + half_spread

        # SAFETY: bid must be below fair value, ask must be above
        bid_price = int(math.floor(min(raw_bid, fair_value - 1)))
        ask_price = int(math.ceil(max(raw_ask, fair_value + 1)))

        # Enforce minimum spread
        if ask_price - bid_price < self.config.min_spread_cents:
            bid_price = int(math.floor(fair_value - self.config.min_spread_cents / 2))
            ask_price = int(math.ceil(fair_value + self.config.min_spread_cents / 2))

        # Hard cap: never quote more than max_spread_cents from fair value
        max_dev = self.config.max_spread_cents
        bid_price = max(bid_price, int(math.floor(fair_value - max_dev)))
        ask_price = min(ask_price, int(math.ceil(fair_value + max_dev)))

        # Clamp to valid Kalshi range
        bid_price = max(1, min(98, bid_price))
        ask_price = max(2, min(99, ask_price))

        if bid_price >= ask_price:
            return _reject(ticker, fair_value, "Spread collapsed")

        # Final safety: reject if bid >= fair_value (should never happen after above)
        if bid_price >= fair_value or ask_price <= fair_value:
            return _reject(ticker, fair_value, "Quote crosses fair value")

        # ── Order sizing ────────────────────────────────────
        position_ratio = abs(q) / max(self.config.max_position, 1)
        size_multiplier = max(0.2, 1.0 - position_ratio * 0.8)
        base_size = self.config.order_size

        bid_size = max(1, int(base_size * size_multiplier))
        ask_size = max(1, int(base_size * size_multiplier))

        # Skew sizes to reduce inventory
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

    def _estimate_arrival_intensity(self, ticker: str) -> float:
        """Estimate order arrival intensity from recent trade frequency."""
        trades = self.market_data.get_recent_trades(ticker, 20)
        if len(trades) < 2:
            return 1.0
        timestamps = [t.timestamp for t in trades]
        time_span = timestamps[-1] - timestamps[0]
        if time_span <= 0:
            return 1.0
        return len(trades) / time_span

    def should_requote(self, ticker: str, current_quote: Optional[Quote]) -> bool:
        """Check if we should update our quotes."""
        if current_quote is None:
            return True

        new_quote = self.compute_quote(ticker)
        if new_quote is None:
            return False

        price_threshold = max(2, self.config.min_spread_cents)
        bid_diff = abs(new_quote.bid_price - current_quote.bid_price)
        ask_diff = abs(new_quote.ask_price - current_quote.ask_price)

        return bid_diff >= price_threshold or ask_diff >= price_threshold
