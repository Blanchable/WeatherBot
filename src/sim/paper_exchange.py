"""Paper trading exchange simulator based on top-of-book conditions."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from execution.fills import FillEvent


@dataclass(slots=True)
class BookSnapshot:
    ticker: str
    best_yes_bid: int
    best_yes_ask: int
    volume_24h: int = 0


@dataclass(slots=True)
class PaperOrder:
    order_id: str
    ticker: str
    city_id: str
    side: str
    action: str
    price_cents: int
    contracts: int
    remaining: int
    created_at_utc: datetime
    status: str = "open"


@dataclass(slots=True)
class PaperExchange:
    rng_seed: int = 7
    books: dict[str, BookSnapshot] = field(default_factory=dict)
    open_orders: dict[str, PaperOrder] = field(default_factory=dict)
    fills: list[FillEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.rng_seed)

    def update_book(self, snapshot: BookSnapshot) -> None:
        self.books[snapshot.ticker] = snapshot

    def place_limit_order(
        self,
        *,
        ticker: str,
        side: str,
        action: str,
        price_cents: int,
        contracts: int,
        city_id: str = "",
    ) -> str:
        order_id = str(uuid.uuid4())
        order = PaperOrder(
            order_id=order_id,
            ticker=ticker,
            city_id=city_id,
            side=side,
            action=action,
            price_cents=price_cents,
            contracts=contracts,
            remaining=contracts,
            created_at_utc=datetime.now(UTC),
        )
        self.open_orders[order_id] = order
        self._try_crossing_fill(order)
        return order_id

    def list_open_orders(self) -> list[dict]:
        return [
            {
                "order_id": order.order_id,
                "ticker": order.ticker,
                "city_id": order.city_id,
                "side": order.side,
                "action": order.action,
                "price_cents": order.price_cents,
                "remaining": order.remaining,
                "status": order.status,
            }
            for order in self.open_orders.values()
            if order.status == "open"
        ]

    def cancel_order(self, order_id: str) -> None:
        order = self.open_orders.get(order_id)
        if order is None:
            return
        order.status = "cancelled"
        self.open_orders.pop(order_id, None)

    def _record_fill(self, order: PaperOrder, contracts: int) -> None:
        if contracts <= 0:
            return
        fill = FillEvent(
            order_id=order.order_id,
            ticker=order.ticker,
            city_id=order.city_id,
            action=order.action,
            side=order.side,
            price_cents=order.price_cents,
            contracts=contracts,
            mode="paper",
            filled_at_utc=datetime.now(UTC),
        )
        self.fills.append(fill)
        order.remaining -= contracts
        if order.remaining <= 0:
            order.status = "filled"
            self.open_orders.pop(order.order_id, None)

    def _try_crossing_fill(self, order: PaperOrder) -> None:
        book = self.books.get(order.ticker)
        if book is None or order.status != "open":
            return
        if order.action == "buy" and order.price_cents >= book.best_yes_ask:
            self._record_fill(order, contracts=order.remaining)
        elif order.action == "sell" and order.price_cents <= book.best_yes_bid:
            self._record_fill(order, contracts=order.remaining)

    def step(self) -> list[FillEvent]:
        for order in list(self.open_orders.values()):
            if order.status != "open":
                continue
            book = self.books.get(order.ticker)
            if book is None:
                continue

            if order.action == "buy" and order.price_cents < book.best_yes_ask:
                queue_priority = max(0.05, (order.price_cents - book.best_yes_bid + 1) / 10.0)
            elif order.action == "sell" and order.price_cents > book.best_yes_bid:
                queue_priority = max(0.05, (book.best_yes_ask - order.price_cents + 1) / 10.0)
            else:
                queue_priority = 0.7

            activity = min(1.0, max(0.05, book.volume_24h / 1000.0))
            fill_prob = min(0.95, queue_priority * activity)
            if self.rng.random() <= fill_prob:
                max_fill = max(1, int(order.remaining * fill_prob))
                partial = min(order.remaining, self.rng.randint(1, max_fill))
                self._record_fill(order, contracts=partial)

        fills = list(self.fills)
        self.fills.clear()
        return fills

    def mark_prices(self) -> dict[str, int]:
        return {
            ticker: (book.best_yes_bid + book.best_yes_ask) // 2
            for ticker, book in self.books.items()
        }

