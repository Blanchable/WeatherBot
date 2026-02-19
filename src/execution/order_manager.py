"""Order manager — places, cancels, and refreshes maker orders."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.kalshi.models import OrderRequest, OrderResponse
from src.kalshi.rest import KalshiClient
from src.storage.db import Database
from src.strategy.weather_strategy import TradeSignal

log = get_logger(__name__)


class OrderManager:
    """Manages resting maker orders on Kalshi."""

    def __init__(self, client: KalshiClient, db: Database, is_paper: bool = True):
        self.client = client
        self.db = db
        self.is_paper = is_paper
        self._active_orders: dict[str, dict] = {}

    async def place_signal(self, signal: TradeSignal) -> str | None:
        """Place a maker limit order from a trade signal. Returns order_id."""
        settings = get_settings()
        if settings.maker_only and signal.action != "buy":
            log.warning("Maker-only mode; skipping non-buy signal for %s", signal.meta.ticker)

        order_id = f"paper-{uuid.uuid4().hex[:12]}" if self.is_paper else None

        if not self.is_paper and settings.live_trading:
            req = OrderRequest(
                ticker=signal.meta.ticker,
                action=signal.action,
                side=signal.side,
                type="limit",
                count=signal.quantity,
                yes_price=signal.price_cents if signal.side == "yes" else None,
                no_price=signal.price_cents if signal.side == "no" else None,
            )
            try:
                resp = await self.client.place_order(req)
                order_id = resp.order_id
                log.info(
                    "[LIVE] Placed order %s: %s %s %s@%dc x%d",
                    order_id, signal.meta.ticker, signal.action, signal.side,
                    signal.price_cents, signal.quantity,
                )
            except Exception as exc:
                log.error("Failed to place live order: %s", exc)
                return None
        else:
            log.info(
                "[PAPER] Placed order %s: %s %s %s@%dc x%d (prob=%.3f ev=$%.4f)",
                order_id, signal.meta.ticker, signal.action, signal.side,
                signal.price_cents, signal.quantity, signal.model_prob, signal.model_ev,
            )

        order_dict = {
            "order_id": order_id,
            "ticker": signal.meta.ticker,
            "side": signal.side,
            "action": signal.action,
            "price_cents": signal.price_cents,
            "quantity": signal.quantity,
            "filled_qty": 0,
            "status": "resting",
            "is_paper": 1 if self.is_paper else 0,
            "model_prob": signal.model_prob,
            "model_ev": signal.model_ev,
        }
        self.db.save_order(order_dict)
        self._active_orders[order_id] = order_dict
        return order_id

    async def cancel_order(self, order_id: str) -> bool:
        if not self.is_paper:
            settings = get_settings()
            if settings.live_trading:
                success = await self.client.cancel_order(order_id)
                if not success:
                    log.warning("Failed to cancel live order %s", order_id)
                    return False

        self.db.update_order_status(order_id, "cancelled")
        self._active_orders.pop(order_id, None)
        log.info("Cancelled order %s", order_id)
        return True

    async def cancel_all_for_ticker(self, ticker: str) -> int:
        cancelled = 0
        for oid, order in list(self._active_orders.items()):
            if order["ticker"] == ticker:
                if await self.cancel_order(oid):
                    cancelled += 1
        return cancelled

    async def cancel_all(self) -> int:
        cancelled = 0
        for oid in list(self._active_orders.keys()):
            if await self.cancel_order(oid):
                cancelled += 1
        return cancelled

    async def refresh_orders(self) -> None:
        """Sync local state with exchange state (live mode only)."""
        if self.is_paper:
            return

        try:
            live_orders = await self.client.get_orders(status="resting")
            live_ids = {o.order_id for o in live_orders}

            for oid in list(self._active_orders.keys()):
                if oid not in live_ids:
                    self.db.update_order_status(oid, "filled_or_cancelled")
                    self._active_orders.pop(oid, None)
                    log.info("Order %s no longer resting on exchange", oid)

        except Exception as exc:
            log.error("Error refreshing orders: %s", exc)

    @property
    def active_order_count(self) -> int:
        return len(self._active_orders)

    def get_active_orders(self) -> list[dict]:
        return list(self._active_orders.values())
