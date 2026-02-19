"""Core weather trading strategy — decides what to quote and at what price."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.pricing.distribution import compute_fair_price, get_sigma
from src.pricing.ev import best_trade, compute_ev_buy_yes, compute_ev_buy_no
from src.pricing.fees import maker_fee_per_contract
from src.strategy.market_discovery import WeatherMarketMeta
from src.weather.nws_forecast import ForecastSnapshot

log = get_logger(__name__)


class TradeSignal:
    def __init__(
        self,
        meta: WeatherMarketMeta,
        side: str,
        action: str,
        price_cents: int,
        quantity: int,
        model_prob: float,
        model_ev: float,
        forecast_high: float,
        sigma: float,
    ):
        self.meta = meta
        self.side = side
        self.action = action
        self.price_cents = price_cents
        self.quantity = quantity
        self.model_prob = model_prob
        self.model_ev = model_ev
        self.forecast_high = forecast_high
        self.sigma = sigma

    def __repr__(self) -> str:
        return (
            f"TradeSignal({self.meta.ticker} {self.action} {self.side}@{self.price_cents}c "
            f"qty={self.quantity} prob={self.model_prob:.3f} ev=${self.model_ev:.4f})"
        )


def evaluate_market(
    meta: WeatherMarketMeta,
    forecast: ForecastSnapshot,
    yes_bid: int,
    yes_ask: int,
    max_qty: int = 10,
) -> TradeSignal | None:
    """Evaluate a weather market and return a trade signal if EV-positive."""
    settings = get_settings()

    if forecast.predicted_high is None:
        return None

    predicted = forecast.predicted_high
    if meta.market_type == "low_temp" and forecast.predicted_low is not None:
        predicted = forecast.predicted_low

    sigma = get_sigma(meta.city, meta.market_date)

    prob = compute_fair_price(
        predicted_value=predicted,
        sigma=sigma,
        strike_low=meta.strike_low,
        strike_high=meta.strike_high,
        strike_op=meta.strike_op,
    )

    if prob < 0.03 or prob > 0.97:
        log.debug("Skipping %s: extreme probability %.3f", meta.ticker, prob)
        return None

    spread = yes_ask - yes_bid
    if spread < settings.min_spread_cents:
        return None

    trade = best_trade(prob, yes_bid, yes_ask, contracts=1)
    if trade is None:
        return None

    qty = min(max_qty, settings.max_order_size_contracts)

    per_contract_ev = trade["ev"]
    total_ev = per_contract_ev * qty

    return TradeSignal(
        meta=meta,
        side=trade["side"],
        action=trade["action"],
        price_cents=trade["price_cents"],
        quantity=qty,
        model_prob=prob,
        model_ev=per_contract_ev,
        forecast_high=predicted,
        sigma=sigma,
    )


def should_exit_position(
    meta: WeatherMarketMeta,
    forecast: ForecastSnapshot,
    position_side: str,
    avg_price_cents: float,
    current_mid: float,
    quantity: int,
) -> dict | None:
    """Check if an exit is warranted. Returns exit info dict or None."""
    settings = get_settings()

    now = datetime.now(timezone.utc)
    try:
        close_dt = datetime.fromisoformat(meta.close_time.replace("Z", "+00:00"))
        secs_to_close = (close_dt - now).total_seconds()
    except (ValueError, TypeError):
        secs_to_close = float("inf")

    if forecast.predicted_high is None:
        return None

    predicted = forecast.predicted_high
    if meta.market_type == "low_temp" and forecast.predicted_low is not None:
        predicted = forecast.predicted_low
    sigma = get_sigma(meta.city, meta.market_date)
    prob = compute_fair_price(predicted, sigma, meta.strike_low, meta.strike_high, meta.strike_op)

    reason = None

    if position_side == "yes":
        pnl_cents = current_mid - avg_price_cents
    else:
        pnl_cents = (100 - current_mid) - (100 - avg_price_cents)

    # Take profit
    if pnl_cents >= settings.take_profit_cents:
        reason = "take_profit"

    # Stop loss + EV check
    if pnl_cents <= -settings.stop_loss_cents:
        if position_side == "yes":
            ev = compute_ev_buy_yes(prob, int(current_mid), 1, maker=True)
        else:
            ev = compute_ev_buy_no(prob, int(100 - current_mid), 1, maker=True)
        if ev < 0:
            reason = "stop_loss_ev_negative"

    # Time-based exit
    if secs_to_close < settings.exit_only_window_seconds:
        if position_side == "yes":
            ev = compute_ev_buy_yes(prob, int(current_mid), 1, maker=True)
        else:
            ev = compute_ev_buy_no(prob, int(100 - current_mid), 1, maker=True)
        if secs_to_close < 3600 or ev < settings.min_ev_dollars_per_contract:
            reason = "time_exit"

    # Model flip
    if position_side == "yes":
        ev = compute_ev_buy_yes(prob, int(avg_price_cents), 1, maker=True)
    else:
        ev = compute_ev_buy_no(prob, int(100 - avg_price_cents), 1, maker=True)
    if ev < -0.02:
        reason = "model_flip"

    if reason:
        exit_qty = quantity
        if reason == "model_flip":
            exit_qty = max(1, quantity // 2)
        return {
            "reason": reason,
            "exit_quantity": exit_qty,
            "current_prob": prob,
            "pnl_cents": pnl_cents,
            "secs_to_close": secs_to_close,
        }

    return None
