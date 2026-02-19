"""Backtest harness — replay historical forecasts against observed outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.bot.logging import get_logger
from src.pricing.distribution import compute_fair_price, get_sigma
from src.pricing.fees import maker_fee_per_contract

log = get_logger(__name__)


@dataclass
class BacktestTrade:
    ticker: str
    city: str
    date: str
    side: str
    price_cents: int
    quantity: int
    model_prob: float
    actual_outcome: bool
    pnl_dollars: float
    fee_dollars: float


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    total_pnl: float = 0.0
    total_fees: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0

    def summary(self) -> str:
        return (
            f"Backtest: {self.num_trades} trades, "
            f"PnL=${self.total_pnl:.2f}, Fees=${self.total_fees:.2f}, "
            f"Net=${self.total_pnl - self.total_fees:.2f}, "
            f"Win rate={self.win_rate:.1%}"
        )


def run_backtest(
    historical_forecasts: list[dict],
    actual_outcomes: dict[str, float],
    markets: list[dict],
) -> BacktestResult:
    """Run backtest over historical data.

    historical_forecasts: [{city, date, predicted_high, sigma}, ...]
    actual_outcomes: {"{city}_{date}": actual_high_temp, ...}
    markets: [{ticker, city, date, strike_low, strike_high, strike_op, yes_bid, yes_ask}, ...]
    """
    trades: list[BacktestTrade] = []

    for mkt in markets:
        key = f"{mkt['city']}_{mkt['date']}"
        if key not in actual_outcomes:
            continue

        forecast = None
        for f in historical_forecasts:
            if f["city"] == mkt["city"] and f["date"] == mkt["date"]:
                forecast = f
                break
        if not forecast:
            continue

        sigma = forecast.get("sigma", get_sigma(mkt["city"], mkt["date"]))
        prob = compute_fair_price(
            forecast["predicted_high"],
            sigma,
            mkt.get("strike_low"),
            mkt.get("strike_high"),
            mkt["strike_op"],
        )

        actual = actual_outcomes[key]
        strike_low = mkt.get("strike_low")
        strike_high = mkt.get("strike_high")
        strike_op = mkt["strike_op"]

        resolved_yes = False
        if strike_op == "range" and strike_low is not None and strike_high is not None:
            resolved_yes = strike_low <= actual <= strike_high
        elif strike_op == "gte" and strike_low is not None:
            resolved_yes = actual >= strike_low
        elif strike_op == "lte" and strike_high is not None:
            resolved_yes = actual <= strike_high

        yes_bid = mkt.get("yes_bid", 50)
        yes_ask = mkt.get("yes_ask", 50)
        buy_price = yes_bid + 1

        if prob > buy_price / 100.0 + 0.03:
            fee = maker_fee_per_contract(buy_price, 1)
            pnl = (1.0 if resolved_yes else 0.0) - buy_price / 100.0 - fee
            trades.append(BacktestTrade(
                ticker=mkt.get("ticker", ""),
                city=mkt["city"],
                date=mkt["date"],
                side="yes",
                price_cents=buy_price,
                quantity=1,
                model_prob=prob,
                actual_outcome=resolved_yes,
                pnl_dollars=pnl,
                fee_dollars=fee,
            ))

    result = BacktestResult(trades=trades)
    result.num_trades = len(trades)
    result.total_pnl = sum(t.pnl_dollars for t in trades)
    result.total_fees = sum(t.fee_dollars for t in trades)
    if trades:
        result.win_rate = sum(1 for t in trades if t.pnl_dollars > 0) / len(trades)

    return result
