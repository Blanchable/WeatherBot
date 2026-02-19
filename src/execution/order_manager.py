"""Maker-first order manager with slow cancel/replace policy."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from bot.config import BotConfig
from strategy.sizing import ExposureSnapshot, recommend_contracts
from strategy.weather_strategy import TradeCandidate

LOGGER = logging.getLogger(__name__)


class ExchangeLike(Protocol):
    def place_limit_order(
        self,
        *,
        ticker: str,
        side: str,
        action: str,
        price_cents: int,
        contracts: int,
        city_id: str = "",
    ) -> str: ...

    def cancel_order(self, order_id: str) -> None: ...

    def list_open_orders(self) -> list[dict]: ...


@dataclass(slots=True)
class ManagedOrder:
    order_id: str
    ticker: str
    city_id: str
    side: str
    action: str
    price_cents: int
    contracts: int
    created_at_utc: datetime


class MakerOrderManager:
    def __init__(self, config: BotConfig, exchange: ExchangeLike, db: object | None = None) -> None:
        self.config = config
        self.exchange = exchange
        self.db = db
        self.open_orders: dict[str, ManagedOrder] = {}

    def place_manual_order(
        self,
        *,
        ticker: str,
        city_id: str,
        side: str,
        action: str,
        price_cents: int,
        contracts: int,
        status: str = "open",
    ) -> ManagedOrder | None:
        if contracts <= 0:
            return None
        order_id = self.exchange.place_limit_order(
            ticker=ticker,
            side=side,
            action=action,
            price_cents=price_cents,
            contracts=contracts,
            city_id=city_id,
        )
        managed = ManagedOrder(
            order_id=order_id,
            ticker=ticker,
            city_id=city_id,
            side=side,
            action=action,
            price_cents=price_cents,
            contracts=contracts,
            created_at_utc=datetime.now(UTC),
        )
        self.open_orders[order_id] = managed
        if self.db and hasattr(self.db, "record_order"):
            self.db.record_order(
                order_id=order_id,
                ticker=ticker,
                city_id=city_id,
                side=side,
                action=action,
                price_cents=price_cents,
                contracts=contracts,
                status=status,
            )
        return managed

    def place_candidates(
        self,
        candidates: list[TradeCandidate],
        exposure: ExposureSnapshot,
    ) -> list[ManagedOrder]:
        placed: list[ManagedOrder] = []
        for candidate in candidates:
            contracts = recommend_contracts(candidate, exposure=exposure, config=self.config)
            if contracts <= 0:
                continue
            order_id = self.exchange.place_limit_order(
                ticker=candidate.ticker,
                side=candidate.side,
                action=candidate.action,
                price_cents=candidate.price_cents,
                contracts=contracts,
                city_id=candidate.city_id,
            )
            managed = ManagedOrder(
                order_id=order_id,
                ticker=candidate.ticker,
                city_id=candidate.city_id,
                side=candidate.side,
                action=candidate.action,
                price_cents=candidate.price_cents,
                contracts=contracts,
                created_at_utc=datetime.now(UTC),
            )
            self.open_orders[order_id] = managed
            placed.append(managed)
            exposure.gross_dollars += contracts * (candidate.price_cents / 100.0)
            exposure.net_dollars += contracts * (candidate.price_cents / 100.0)
            exposure.city_exposure[candidate.city_id] = (
                exposure.city_exposure.get(candidate.city_id, 0.0)
                + contracts * (candidate.price_cents / 100.0)
            )
            exposure.market_exposure[candidate.ticker] = (
                exposure.market_exposure.get(candidate.ticker, 0.0)
                + contracts * (candidate.price_cents / 100.0)
            )

            if self.db and hasattr(self.db, "record_order"):
                self.db.record_order(
                    order_id=order_id,
                    ticker=candidate.ticker,
                    city_id=candidate.city_id,
                    side=candidate.side,
                    action=candidate.action,
                    price_cents=candidate.price_cents,
                    contracts=contracts,
                    status="open",
                )
            LOGGER.info(
                "Placed maker order %s %s %s @%sc x%s ev=%.4f",
                candidate.ticker,
                candidate.action,
                candidate.side,
                candidate.price_cents,
                contracts,
                candidate.ev_dollars_per_contract,
            )
        return placed

    def cancel_stale_orders(self, *, max_age_seconds: int = 120) -> int:
        now = datetime.now(UTC)
        cancelled = 0
        for order_id, order in list(self.open_orders.items()):
            age = (now - order.created_at_utc).total_seconds()
            if age < max_age_seconds:
                continue
            self.exchange.cancel_order(order_id)
            self.open_orders.pop(order_id, None)
            cancelled += 1
            if self.db and hasattr(self.db, "update_order_status"):
                self.db.update_order_status(order_id, "cancelled")
        return cancelled

