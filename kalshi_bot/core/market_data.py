"""Market data management - order book, trade history, and market metadata."""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    price: int  # cents
    quantity: int


@dataclass
class OrderBook:
    ticker: str
    yes_bids: list[OrderBookLevel] = field(default_factory=list)
    yes_asks: list[OrderBookLevel] = field(default_factory=list)
    no_bids: list[OrderBookLevel] = field(default_factory=list)
    no_asks: list[OrderBookLevel] = field(default_factory=list)
    timestamp: float = 0.0

    @property
    def best_bid(self) -> Optional[int]:
        if self.yes_bids:
            return max(level.price for level in self.yes_bids)
        return None

    @property
    def best_ask(self) -> Optional[int]:
        if self.yes_asks:
            return min(level.price for level in self.yes_asks)
        return None

    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2.0
        return None

    @property
    def spread(self) -> Optional[int]:
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    @property
    def bid_depth(self) -> int:
        return sum(level.quantity for level in self.yes_bids)

    @property
    def ask_depth(self) -> int:
        return sum(level.quantity for level in self.yes_asks)


@dataclass
class Trade:
    price: int
    count: int
    taker_side: str
    timestamp: float


@dataclass
class MarketInfo:
    ticker: str
    event_ticker: str
    title: str = ""
    subtitle: str = ""
    status: str = ""
    yes_bid: int = 0
    yes_ask: int = 0
    last_price: int = 0
    volume: int = 0
    open_interest: int = 0
    close_time: Optional[datetime] = None
    expiration_time: Optional[datetime] = None

    @property
    def hours_to_expiry(self) -> Optional[float]:
        if self.expiration_time:
            delta = self.expiration_time - datetime.now(timezone.utc)
            return max(0, delta.total_seconds() / 3600)
        return None

    @property
    def is_active(self) -> bool:
        return self.status in ("open", "active")


class MarketDataManager:
    """Manages market data for multiple markets."""

    def __init__(self):
        self.order_books: dict[str, OrderBook] = {}
        self.trade_history: dict[str, deque] = {}
        self.market_info: dict[str, MarketInfo] = {}
        self._lock = threading.RLock()
        self._max_trade_history = 200

    def update_orderbook(self, ticker: str, raw_data: dict):
        with self._lock:
            ob = self.order_books.get(ticker, OrderBook(ticker=ticker))
            ob.yes_bids = []
            ob.yes_asks = []
            ob.no_bids = []
            ob.no_asks = []

            for side_key, target in [("yes", "yes_bids"), ("no", "no_bids")]:
                raw_bids = raw_data.get(side_key, [])
                if isinstance(raw_bids, list):
                    for entry in raw_bids:
                        if isinstance(entry, list) and len(entry) >= 2:
                            level = OrderBookLevel(price=entry[0], quantity=entry[1])
                        elif isinstance(entry, dict):
                            level = OrderBookLevel(
                                price=entry.get("price", 0),
                                quantity=entry.get("quantity", 0),
                            )
                        else:
                            continue
                        getattr(ob, target).append(level)

            # Derive asks from the opposite side
            for bid_level in ob.no_bids:
                ask_price = 100 - bid_level.price
                ob.yes_asks.append(OrderBookLevel(price=ask_price, quantity=bid_level.quantity))
            for bid_level in ob.yes_bids:
                ask_price = 100 - bid_level.price
                ob.no_asks.append(OrderBookLevel(price=ask_price, quantity=bid_level.quantity))

            ob.timestamp = time.time()
            self.order_books[ticker] = ob

    def update_market_info(self, ticker: str, raw_data: dict):
        with self._lock:
            info = self.market_info.get(ticker, MarketInfo(
                ticker=ticker,
                event_ticker=raw_data.get("event_ticker", ""),
            ))
            info.title = raw_data.get("title", info.title)
            info.subtitle = raw_data.get("subtitle", info.subtitle)
            info.status = raw_data.get("status", info.status)
            info.yes_bid = raw_data.get("yes_bid", info.yes_bid)
            info.yes_ask = raw_data.get("yes_ask", info.yes_ask)
            info.last_price = raw_data.get("last_price", info.last_price)
            info.volume = raw_data.get("volume", info.volume) or 0
            info.open_interest = raw_data.get("open_interest", info.open_interest) or 0
            info.event_ticker = raw_data.get("event_ticker", info.event_ticker)

            for time_field in ("close_time", "expiration_time"):
                raw_time = raw_data.get(time_field)
                if raw_time and isinstance(raw_time, str):
                    try:
                        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                        setattr(info, time_field, dt)
                    except ValueError:
                        pass

            self.market_info[ticker] = info

    def add_trades(self, ticker: str, trades: list[dict]):
        with self._lock:
            if ticker not in self.trade_history:
                self.trade_history[ticker] = deque(maxlen=self._max_trade_history)
            for t in trades:
                trade = Trade(
                    price=t.get("yes_price", t.get("price", 50)),
                    count=t.get("count", 1),
                    taker_side=t.get("taker_side", "unknown"),
                    timestamp=time.time(),
                )
                self.trade_history[ticker].append(trade)

    def get_orderbook(self, ticker: str) -> Optional[OrderBook]:
        with self._lock:
            return self.order_books.get(ticker)

    def get_market_info(self, ticker: str) -> Optional[MarketInfo]:
        with self._lock:
            return self.market_info.get(ticker)

    def get_recent_trades(self, ticker: str, n: int = 50) -> list[Trade]:
        with self._lock:
            history = self.trade_history.get(ticker, deque())
            return list(history)[-n:]

    def estimate_volatility(self, ticker: str, lookback: int = 50) -> float:
        """Estimate volatility from recent trade prices (as proportion)."""
        trades = self.get_recent_trades(ticker, lookback)
        if len(trades) < 5:
            return 0.15  # default moderate volatility
        prices = np.array([t.price / 100.0 for t in trades])
        returns = np.diff(prices)
        if len(returns) < 2:
            return 0.15
        vol = float(np.std(returns))
        return max(0.02, min(0.50, vol * np.sqrt(len(returns))))

    def get_microprice(self, ticker: str) -> Optional[float]:
        """Volume-weighted mid price (microprice) for better fair value estimation."""
        ob = self.get_orderbook(ticker)
        if not ob or ob.best_bid is None or ob.best_ask is None:
            return None
        bid_qty = ob.yes_bids[0].quantity if ob.yes_bids else 1
        ask_qty = ob.yes_asks[0].quantity if ob.yes_asks else 1
        total = bid_qty + ask_qty
        if total == 0:
            return ob.mid_price
        return (ob.best_bid * ask_qty + ob.best_ask * bid_qty) / total
