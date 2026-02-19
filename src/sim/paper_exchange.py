"""Paper trading exchange — simulates fills against live orderbook snapshots."""

from __future__ import annotations

import random
from datetime import datetime, timezone

from src.bot.logging import get_logger
from src.execution.fills import FillProcessor
from src.storage.db import Database

log = get_logger(__name__)


class PaperExchange:
    """Simulates order fills for paper trading mode.

    Fill logic:
    - Buy orders fill if our bid >= current best ask
    - Sell orders fill if our ask <= current best bid
    - Partial fills simulated with probability based on volume
    """

    def __init__(self, db: Database):
        self.db = db
        self.fill_processor = FillProcessor(db, is_paper=True)

    def check_fills(
        self,
        orderbook_snapshots: dict[str, dict],
    ) -> list[dict]:
        """Check all resting paper orders against current orderbook snapshots.

        orderbook_snapshots: {ticker: {"yes_bid": int, "yes_ask": int, "volume": int}}
        """
        orders = self.db.get_open_orders(is_paper=True)
        fills: list[dict] = []

        for order in orders:
            ticker = order["ticker"]
            if ticker not in orderbook_snapshots:
                continue

            snap = orderbook_snapshots[ticker]
            yes_bid = snap.get("yes_bid", 0)
            yes_ask = snap.get("yes_ask", 100)
            volume = snap.get("volume", 0)

            filled = False
            remaining = order["quantity"] - order.get("filled_qty", 0)
            if remaining <= 0:
                continue

            fill_prob = min(1.0, volume / 2000.0) if volume > 0 else 0.3

            if order["action"] == "buy":
                if order["side"] == "yes":
                    if order["price_cents"] >= yes_ask:
                        filled = True
                elif order["side"] == "no":
                    implied_no_ask = 100 - yes_bid
                    if order["price_cents"] >= implied_no_ask:
                        filled = True
            elif order["action"] == "sell":
                if order["side"] == "yes":
                    if order["price_cents"] <= yes_bid:
                        filled = True
                elif order["side"] == "no":
                    implied_no_bid = 100 - yes_ask
                    if order["price_cents"] <= implied_no_bid:
                        filled = True

            if filled and random.random() < fill_prob:
                fill_qty = remaining
                if fill_prob < 0.8:
                    fill_qty = max(1, int(remaining * random.uniform(0.3, 1.0)))

                self.fill_processor.process_fill(
                    order_id=order["order_id"],
                    ticker=ticker,
                    side=order["side"],
                    action=order["action"],
                    price_cents=order["price_cents"],
                    quantity=fill_qty,
                )

                new_filled = order.get("filled_qty", 0) + fill_qty
                if new_filled >= order["quantity"]:
                    self.db.update_order_status(order["order_id"], "filled", new_filled)
                else:
                    self.db.update_order_status(order["order_id"], "resting", new_filled)

                fills.append({
                    "order_id": order["order_id"],
                    "ticker": ticker,
                    "side": order["side"],
                    "action": order["action"],
                    "price_cents": order["price_cents"],
                    "quantity": fill_qty,
                })

        return fills
