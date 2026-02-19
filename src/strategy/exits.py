"""Exit policy logic to avoid bagholding and late surprises."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bot.config import BotConfig


@dataclass(slots=True)
class PositionView:
    ticker: str
    city_id: str
    contracts: int
    avg_entry_price_cents: int
    mark_price_cents: int
    model_ev_dollars_per_contract: float
    close_time_utc: datetime


@dataclass(slots=True)
class ExitPlan:
    ticker: str
    contracts_to_exit: int
    target_price_cents: int
    reason: str
    allow_taker: bool = False


def evaluate_exit(position: PositionView, config: BotConfig, now_utc: datetime | None = None) -> ExitPlan | None:
    now = now_utc or datetime.now(UTC)
    seconds_to_close = (position.close_time_utc - now).total_seconds()
    mtm_cents = position.mark_price_cents - position.avg_entry_price_cents

    if position.contracts <= 0:
        return None

    strong_ev = max(config.min_ev_dollars_per_contract * 2, 0.04)
    if seconds_to_close <= 3600 and position.model_ev_dollars_per_contract < strong_ev:
        return ExitPlan(
            ticker=position.ticker,
            contracts_to_exit=position.contracts,
            target_price_cents=max(1, position.mark_price_cents),
            reason="force_flat_1h_before_close",
            allow_taker=seconds_to_close <= 5400,
        )

    if mtm_cents <= -config.stop_loss_cents and position.model_ev_dollars_per_contract <= 0:
        return ExitPlan(
            ticker=position.ticker,
            contracts_to_exit=position.contracts,
            target_price_cents=max(1, position.mark_price_cents),
            reason="stop_loss_ev_not_positive",
            allow_taker=seconds_to_close <= 5400,
        )

    if position.model_ev_dollars_per_contract <= config.model_flip_ev_threshold:
        return ExitPlan(
            ticker=position.ticker,
            contracts_to_exit=max(1, position.contracts // 2),
            target_price_cents=max(1, position.mark_price_cents),
            reason="model_flip_reduce_50pct",
            allow_taker=False,
        )

    if mtm_cents >= config.take_profit_cents:
        return ExitPlan(
            ticker=position.ticker,
            contracts_to_exit=max(1, position.contracts // 2),
            target_price_cents=max(1, position.mark_price_cents),
            reason="take_profit_partial",
            allow_taker=False,
        )

    if seconds_to_close <= config.no_trade_window_seconds:
        return ExitPlan(
            ticker=position.ticker,
            contracts_to_exit=max(1, position.contracts // 2),
            target_price_cents=max(1, position.mark_price_cents),
            reason="time_based_reduce_6h",
            allow_taker=False,
        )

    return None

