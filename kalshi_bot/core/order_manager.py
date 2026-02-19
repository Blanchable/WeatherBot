"""Order lifecycle management - tracks and manages bot orders."""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from kalshi_bot.core.api import KalshiApiClient

logger = logging.getLogger(__name__)


@dataclass
class ManagedOrder:
    order_id: str
    client_order_id: str
    ticker: str
    side: str  # 'yes' or 'no'
    action: str  # 'buy' or 'sell'
    price: int
    size: int
    filled: int = 0
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    is_bid: bool = True  # True = bid for YES, False = ask for YES (bid for NO)


class OrderManager:
    """Manages the bot's order lifecycle."""

    def __init__(self, api: KalshiApiClient):
        self.api = api
        self.active_orders: dict[str, ManagedOrder] = {}
        self.order_history: list[ManagedOrder] = []
        self._lock = threading.RLock()
        self.total_fills = 0
        self.total_volume_cents = 0

    def _gen_client_id(self) -> str:
        return f"mm_{uuid.uuid4().hex[:12]}"

    def place_bid(self, ticker: str, price: int, size: int) -> Optional[ManagedOrder]:
        """Place a YES bid (buy YES at price)."""
        client_id = self._gen_client_id()
        result = self.api.place_order(
            ticker=ticker,
            side="yes",
            action="buy",
            order_type="limit",
            count=size,
            yes_price=price,
        )
        if result:
            order = ManagedOrder(
                order_id=result.get("order_id", client_id),
                client_order_id=client_id,
                ticker=ticker,
                side="yes",
                action="buy",
                price=price,
                size=size,
                status=result.get("status", "resting"),
                is_bid=True,
            )
            with self._lock:
                self.active_orders[order.order_id] = order
            logger.info("Placed bid: %s YES@%dc x%d (id=%s)", ticker, price, size, order.order_id)
            return order
        return None

    def place_ask(self, ticker: str, price: int, size: int) -> Optional[ManagedOrder]:
        """Place a YES ask (buy NO at 100-price, which is equivalent to selling YES)."""
        client_id = self._gen_client_id()
        no_price = 100 - price
        result = self.api.place_order(
            ticker=ticker,
            side="no",
            action="buy",
            order_type="limit",
            count=size,
            no_price=no_price,
        )
        if result:
            order = ManagedOrder(
                order_id=result.get("order_id", client_id),
                client_order_id=client_id,
                ticker=ticker,
                side="no",
                action="buy",
                price=price,
                size=size,
                status=result.get("status", "resting"),
                is_bid=False,
            )
            with self._lock:
                self.active_orders[order.order_id] = order
            logger.info("Placed ask: %s YES@%dc x%d (id=%s)", ticker, price, size, order.order_id)
            return order
        return None

    def cancel_order(self, order_id: str) -> bool:
        result = self.api.cancel_order(order_id)
        if result is not None:
            with self._lock:
                if order_id in self.active_orders:
                    self.active_orders[order_id].status = "cancelled"
                    self.order_history.append(self.active_orders.pop(order_id))
            return True
        return False

    def cancel_all(self, ticker: Optional[str] = None) -> int:
        """Cancel all active orders, optionally for a specific ticker."""
        with self._lock:
            orders_to_cancel = list(self.active_orders.values())
            if ticker:
                orders_to_cancel = [o for o in orders_to_cancel if o.ticker == ticker]

        cancelled = 0
        for order in orders_to_cancel:
            if self.cancel_order(order.order_id):
                cancelled += 1
        return cancelled

    def cancel_and_replace(self, ticker: str, bid_price: int, bid_size: int,
                           ask_price: int, ask_size: int) -> tuple[Optional[ManagedOrder], Optional[ManagedOrder]]:
        """Cancel existing orders for ticker and place new bid/ask pair."""
        self.cancel_all(ticker)
        time.sleep(0.1)

        bid_order = self.place_bid(ticker, bid_price, bid_size)
        ask_order = self.place_ask(ticker, ask_price, ask_size)

        return bid_order, ask_order

    def sync_orders(self):
        """Sync local order state with exchange."""
        try:
            exchange_orders = self.api.get_orders(status="resting")
            exchange_ids = {o.get("order_id") for o in exchange_orders}

            with self._lock:
                stale = [oid for oid in self.active_orders if oid not in exchange_ids]
                for oid in stale:
                    order = self.active_orders.pop(oid)
                    order.status = "filled_or_cancelled"
                    self.order_history.append(order)

        except Exception as e:
            logger.error("Failed to sync orders: %s", e)

    def get_active_orders(self, ticker: Optional[str] = None) -> list[ManagedOrder]:
        with self._lock:
            orders = list(self.active_orders.values())
            if ticker:
                orders = [o for o in orders if o.ticker == ticker]
            return orders

    @property
    def active_order_count(self) -> int:
        with self._lock:
            return len(self.active_orders)
