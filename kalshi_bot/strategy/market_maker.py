"""Avellaneda-Stoikov market making strategy adapted for Kalshi binary event markets.

The strategy:
1. Estimates fair value from microprice (volume-weighted mid)
2. Computes optimal spread using Avellaneda-Stoikov framework
3. Adjusts quotes for inventory risk (skews away from accumulated position)
4. Widens spread near expiry or during high volatility
5. Places bid/ask quotes around the reservation price
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


class MarketMakingStrategy:
    """Avellaneda-Stoikov market maker for binary event contracts."""

    def __init__(self, config: StrategyConfig, market_data: MarketDataManager):
        self.config = config
        self.market_data = market_data
        self.positions: dict[str, int] = {}  # ticker -> net position (positive = long YES)

    def update_position(self, ticker: str, position: int):
        self.positions[ticker] = position

    def compute_quote(self, ticker: str) -> Optional[Quote]:
        """Compute optimal bid/ask quote for a market."""
        ob = self.market_data.get_orderbook(ticker)
        info = self.market_data.get_market_info(ticker)

        if not ob or ob.best_bid is None or ob.best_ask is None:
            return None

        # 1. Fair value estimation via microprice
        fair_value = self.market_data.get_microprice(ticker)
        if fair_value is None:
            fair_value = ob.mid_price
        if fair_value is None:
            return None

        # Don't quote on extreme prices (too close to 0 or 100)
        if fair_value < 3 or fair_value > 97:
            return Quote(
                ticker=ticker, bid_price=0, ask_price=0,
                bid_size=0, ask_size=0, fair_value=fair_value,
                spread=0, inventory_skew=0, reason="Price too extreme"
            )

        # 2. Volatility estimation
        sigma = self.market_data.estimate_volatility(ticker, self.config.volatility_lookback)
        sigma = max(self.config.volatility_floor, min(self.config.volatility_cap, sigma))

        # 3. Time to close factor (use close_time, not settlement expiry)
        T = 1.0  # normalized time remaining
        if info and info.hours_to_close is not None:
            hours = info.hours_to_close
            if hours < self.config.time_decay_start_hours:
                T = max(0.01, hours / self.config.time_decay_start_hours)

        # 4. Inventory risk (Avellaneda-Stoikov)
        gamma = self.config.inventory_risk_aversion
        q = self.positions.get(ticker, 0)

        # Reservation price: r = s - q * gamma * sigma^2 * T
        # In cents, sigma is in price-space
        sigma_cents = sigma * 100
        reservation_price = fair_value - q * gamma * (sigma_cents ** 2) * T / 100

        # Clamp reservation price
        reservation_price = max(2, min(98, reservation_price))

        # 5. Optimal spread: delta = gamma * sigma^2 * T + (2/gamma) * ln(1 + gamma/k)
        # k is order arrival intensity, approximate from volume
        k = self._estimate_arrival_intensity(ticker)
        spread_component = gamma * (sigma_cents ** 2) * T / 100
        liquidity_component = (2 / max(gamma, 0.01)) * math.log(1 + gamma / max(k, 0.1))
        optimal_half_spread = (spread_component + liquidity_component) / 2

        # Apply spread bounds
        half_spread_cents = max(
            self.config.min_spread_cents / 2,
            min(self.config.max_spread_cents / 2, optimal_half_spread)
        )

        # 6. Inventory skew - shift quotes to reduce position
        inventory_skew = q * gamma * sigma_cents * T / 100
        inventory_skew = max(-5, min(5, inventory_skew))

        # 7. Compute final bid/ask
        bid_price = int(round(reservation_price - half_spread_cents))
        ask_price = int(round(reservation_price + half_spread_cents))

        # Ensure minimum spread
        if ask_price - bid_price < self.config.min_spread_cents:
            mid = (bid_price + ask_price) / 2
            half = self.config.min_spread_cents / 2
            bid_price = int(math.floor(mid - half))
            ask_price = int(math.ceil(mid + half))

        # Clamp to valid range
        bid_price = max(1, min(98, bid_price))
        ask_price = max(2, min(99, ask_price))

        if bid_price >= ask_price:
            ask_price = bid_price + 1

        # 8. Order sizing - reduce size when inventory is large
        position_ratio = abs(q) / max(self.config.max_position, 1)
        size_multiplier = max(0.2, 1.0 - position_ratio * 0.8)

        base_size = self.config.order_size
        bid_size = max(1, int(base_size * size_multiplier))
        ask_size = max(1, int(base_size * size_multiplier))

        # Skew sizes: offer more on the side that reduces inventory
        if q > 0:  # long, want to sell more
            ask_size = max(1, int(ask_size * 1.3))
            bid_size = max(1, int(bid_size * 0.7))
        elif q < 0:  # short, want to buy more
            bid_size = max(1, int(bid_size * 1.3))
            ask_size = max(1, int(ask_size * 0.7))

        # Cap order sizes
        bid_size = min(bid_size, self.config.max_order_size)
        ask_size = min(ask_size, self.config.max_order_size)

        # 9. Check min edge
        existing_spread = ob.spread or 100
        our_spread = ask_price - bid_price
        if our_spread <= 0:
            return Quote(
                ticker=ticker, bid_price=0, ask_price=0,
                bid_size=0, ask_size=0, fair_value=fair_value,
                spread=our_spread, inventory_skew=inventory_skew,
                reason="Negative spread"
            )

        return Quote(
            ticker=ticker,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=bid_size,
            ask_size=ask_size,
            fair_value=fair_value,
            spread=ask_price - bid_price,
            inventory_skew=inventory_skew,
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

        price_threshold = max(1, self.config.min_spread_cents // 2)
        bid_diff = abs(new_quote.bid_price - current_quote.bid_price)
        ask_diff = abs(new_quote.ask_price - current_quote.ask_price)

        return bid_diff >= price_threshold or ask_diff >= price_threshold
