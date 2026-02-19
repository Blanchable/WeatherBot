"""Fill processing — updates positions and P&L on fills."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.bot.logging import get_logger
from src.pricing.fees import maker_fee_per_contract
from src.storage.db import Database

log = get_logger(__name__)


class FillProcessor:
    def __init__(self, db: Database, is_paper: bool = True):
        self.db = db
        self.is_paper = is_paper

    def process_fill(
        self,
        order_id: str,
        ticker: str,
        side: str,
        action: str,
        price_cents: int,
        quantity: int,
    ) -> None:
        fee = maker_fee_per_contract(price_cents, quantity)

        fill_id = f"fill-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        self.db.save_fill({
            "fill_id": fill_id,
            "order_id": order_id,
            "ticker": ticker,
            "side": side,
            "action": action,
            "price_cents": price_cents,
            "quantity": quantity,
            "fee_dollars": fee,
            "filled_at": now,
            "is_paper": 1 if self.is_paper else 0,
        })

        self._update_position(ticker, side, action, price_cents, quantity)

        log.info(
            "[FILL] %s %s %s@%dc x%d fee=$%.4f",
            ticker, action, side, price_cents, quantity, fee,
        )

    def _update_position(
        self,
        ticker: str,
        side: str,
        action: str,
        price_cents: int,
        quantity: int,
    ) -> None:
        positions = self.db.get_all_positions(self.is_paper)
        existing = None
        for p in positions:
            if p["ticker"] == ticker and p["side"] == side:
                existing = p
                break

        now = datetime.now(timezone.utc).isoformat()

        if action == "buy":
            if existing and existing["quantity"] > 0:
                old_qty = existing["quantity"]
                old_avg = existing["avg_price_cents"]
                new_qty = old_qty + quantity
                new_avg = (old_avg * old_qty + price_cents * quantity) / new_qty
                self.db.upsert_position({
                    "ticker": ticker,
                    "side": side,
                    "quantity": new_qty,
                    "avg_price_cents": new_avg,
                    "realized_pnl": existing.get("realized_pnl", 0),
                    "opened_at": existing.get("opened_at", now),
                    "is_paper": 1 if self.is_paper else 0,
                })
            else:
                self.db.upsert_position({
                    "ticker": ticker,
                    "side": side,
                    "quantity": quantity,
                    "avg_price_cents": float(price_cents),
                    "realized_pnl": 0,
                    "opened_at": now,
                    "is_paper": 1 if self.is_paper else 0,
                })
        elif action == "sell":
            if existing and existing["quantity"] > 0:
                sell_qty = min(quantity, existing["quantity"])
                avg_cost = existing["avg_price_cents"]
                if side == "yes":
                    pnl_per = (price_cents - avg_cost) / 100.0
                else:
                    pnl_per = ((100 - price_cents) - (100 - avg_cost)) / 100.0
                realized = pnl_per * sell_qty
                new_qty = existing["quantity"] - sell_qty
                self.db.upsert_position({
                    "ticker": ticker,
                    "side": side,
                    "quantity": new_qty,
                    "avg_price_cents": avg_cost if new_qty > 0 else 0,
                    "realized_pnl": existing.get("realized_pnl", 0) + realized,
                    "opened_at": existing.get("opened_at", now),
                    "is_paper": 1 if self.is_paper else 0,
                })
