"""Rich-powered CLI dashboard rendering."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from execution.fills import PositionState
from storage.pnl import PnLReport
from strategy.weather_strategy import TradeCandidate


def render_dashboard(
    *,
    console: Console,
    mode: str,
    exit_only: bool,
    candidates: list[TradeCandidate],
    positions: list[PositionState],
    pnl: PnLReport,
) -> None:
    summary = Table(title="Kalshi Weather Bot")
    summary.add_column("Mode")
    summary.add_column("Exit-Only")
    summary.add_column("Realized PnL")
    summary.add_column("Unrealized PnL")
    summary.add_column("Gross Exposure")
    summary.add_column("Net Exposure")
    summary.add_row(
        mode,
        "YES" if exit_only else "NO",
        f"${pnl.realized_dollars:.2f}",
        f"${pnl.unrealized_dollars:.2f}",
        f"${pnl.gross_exposure_dollars:.2f}",
        f"${pnl.net_exposure_dollars:.2f}",
    )
    console.print(summary)

    ctable = Table(title="Top Candidate Trades")
    ctable.add_column("Ticker")
    ctable.add_column("City")
    ctable.add_column("Price")
    ctable.add_column("Fair")
    ctable.add_column("EV/ctrt")
    ctable.add_column("Spread")
    ctable.add_column("Mean")
    ctable.add_column("Sigma")
    for candidate in candidates[:10]:
        ctable.add_row(
            candidate.ticker,
            candidate.city_id,
            f"{candidate.price_cents}c",
            f"{candidate.fair_price_cents}c",
            f"${candidate.ev_dollars_per_contract:.3f}",
            f"{candidate.spread_cents}c",
            f"{candidate.model_mean_high_f:.1f}",
            f"{candidate.model_sigma_f:.2f}",
        )
    console.print(ctable)

    ptable = Table(title="Open Positions")
    ptable.add_column("Ticker")
    ptable.add_column("City")
    ptable.add_column("Contracts")
    ptable.add_column("Avg Price")
    ptable.add_column("Realized")
    for pos in positions:
        ptable.add_row(
            pos.ticker,
            pos.city_id,
            str(pos.contracts),
            f"{pos.avg_price_cents}c",
            f"${pos.realized_pnl_dollars:.2f}",
        )
    console.print(ptable)

