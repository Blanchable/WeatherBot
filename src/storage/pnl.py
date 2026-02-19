"""PnL and exposure calculations."""

from __future__ import annotations

from dataclasses import dataclass

from execution.fills import PositionState
from strategy.sizing import ExposureSnapshot


@dataclass(slots=True)
class PnLReport:
    realized_dollars: float
    unrealized_dollars: float
    gross_exposure_dollars: float
    net_exposure_dollars: float


def compute_unrealized_pnl(positions: list[PositionState], mark_prices: dict[str, int]) -> float:
    total = 0.0
    for pos in positions:
        mark = mark_prices.get(pos.ticker)
        if mark is None:
            continue
        total += (mark - pos.avg_price_cents) * pos.contracts / 100.0
    return total


def compute_exposure(positions: list[PositionState]) -> ExposureSnapshot:
    snapshot = ExposureSnapshot()
    for pos in positions:
        notional = pos.contracts * (pos.avg_price_cents / 100.0)
        snapshot.gross_dollars += abs(notional)
        snapshot.net_dollars += notional
        snapshot.city_exposure[pos.city_id] = snapshot.city_exposure.get(pos.city_id, 0.0) + abs(notional)
        snapshot.market_exposure[pos.ticker] = abs(notional)
    return snapshot


def build_pnl_report(positions: list[PositionState], mark_prices: dict[str, int]) -> PnLReport:
    realized = sum(pos.realized_pnl_dollars for pos in positions)
    unrealized = compute_unrealized_pnl(positions, mark_prices=mark_prices)
    exposure = compute_exposure(positions)
    return PnLReport(
        realized_dollars=realized,
        unrealized_dollars=unrealized,
        gross_exposure_dollars=exposure.gross_dollars,
        net_exposure_dollars=exposure.net_dollars,
    )

