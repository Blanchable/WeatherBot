"""Temperature probability distribution model."""

from __future__ import annotations

from datetime import datetime, timezone

from scipy import stats

from src.bot.config import get_settings
from src.bot.logging import get_logger

log = get_logger(__name__)


def get_sigma(city_id: str, forecast_date: str) -> float:
    """Return forecast uncertainty sigma based on horizon."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    try:
        target = datetime.strptime(forecast_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return settings.sigma_2plus_day

    days_ahead = (target.date() - now.date()).days

    if days_ahead <= 0:
        return settings.sigma_same_day
    elif days_ahead == 1:
        return settings.sigma_next_day
    else:
        return settings.sigma_2plus_day


def prob_in_range(
    mean: float,
    sigma: float,
    low: float | None,
    high: float | None,
) -> float:
    """P(low <= X <= high) where X ~ N(mean, sigma)."""
    if low is not None and high is not None:
        return float(stats.norm.cdf(high, mean, sigma) - stats.norm.cdf(low, mean, sigma))
    elif low is not None:
        return float(1.0 - stats.norm.cdf(low, mean, sigma))
    elif high is not None:
        return float(stats.norm.cdf(high, mean, sigma))
    else:
        return 1.0


def prob_gte(mean: float, sigma: float, threshold: float) -> float:
    """P(X >= threshold)."""
    return float(1.0 - stats.norm.cdf(threshold, mean, sigma))


def prob_lte(mean: float, sigma: float, threshold: float) -> float:
    """P(X <= threshold)."""
    return float(stats.norm.cdf(threshold, mean, sigma))


def compute_fair_price(
    predicted_value: float,
    sigma: float,
    strike_low: float | None,
    strike_high: float | None,
    strike_op: str,
) -> float:
    """Return fair probability (0-1) for a weather market contract."""
    if strike_op == "range":
        return prob_in_range(predicted_value, sigma, strike_low, strike_high)
    elif strike_op == "gte":
        return prob_gte(predicted_value, sigma, strike_low or 0)
    elif strike_op == "lte":
        return prob_lte(predicted_value, sigma, strike_high or 200)
    else:
        log.warning("Unknown strike_op '%s', returning 0.5", strike_op)
        return 0.5
