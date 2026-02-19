"""Minimal backtest harness placeholder for Phase 3+ expansion."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class BacktestResult:
    trades: int
    win_rate: float
    total_pnl_dollars: float


def run_simple_backtest(trades_df: pd.DataFrame) -> BacktestResult:
    if trades_df.empty:
        return BacktestResult(trades=0, win_rate=0.0, total_pnl_dollars=0.0)
    pnl = trades_df["realized_pnl_dollars"].sum()
    wins = (trades_df["realized_pnl_dollars"] > 0).sum()
    trades = len(trades_df)
    return BacktestResult(
        trades=trades,
        win_rate=float(wins) / float(trades),
        total_pnl_dollars=float(pnl),
    )

