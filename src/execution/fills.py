"""Fill events and lightweight position accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True)
class FillEvent:
    order_id: str
    ticker: str
    city_id: str
    action: str  # buy | sell
    side: str  # yes | no
    price_cents: int
    contracts: int
    mode: str  # paper | live
    filled_at_utc: datetime


@dataclass(slots=True)
class PositionState:
    ticker: str
    city_id: str
    contracts: int = 0
    avg_price_cents: int = 0
    realized_pnl_dollars: float = 0.0


def utc_now() -> datetime:
    return datetime.now(UTC)


def apply_fill(position: PositionState, fill: FillEvent) -> PositionState:
    if fill.contracts <= 0:
        return position

    if fill.action == "buy":
        new_contracts = position.contracts + fill.contracts
        if new_contracts <= 0:
            return position
        weighted_cost = position.contracts * position.avg_price_cents + fill.contracts * fill.price_cents
        position.contracts = new_contracts
        position.avg_price_cents = int(round(weighted_cost / new_contracts))
        return position

    if fill.action == "sell":
        sold = min(fill.contracts, position.contracts)
        if sold <= 0:
            return position
        pnl_cents = (fill.price_cents - position.avg_price_cents) * sold
        position.realized_pnl_dollars += pnl_cents / 100.0
        position.contracts -= sold
        if position.contracts == 0:
            position.avg_price_cents = 0
        return position

    return position

