"""Temperature distribution and contract probability calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from scipy.stats import norm


@dataclass(frozen=True, slots=True)
class MarketStrike:
    strike_type: str  # range | ge | lt
    low: float | None = None
    high: float | None = None


def predicted_daily_high(hourly_times: list[datetime], hourly_temps_f: list[float], target_date: date) -> float:
    selected: list[float] = []
    for timestamp, temp in zip(hourly_times, hourly_temps_f, strict=False):
        if timestamp.date() == target_date:
            selected.append(temp)
    if not selected:
        if not hourly_temps_f:
            raise ValueError("No hourly temperatures available to estimate daily high.")
        return max(hourly_temps_f)
    return max(selected)


def probability_for_strike(mean_f: float, sigma_f: float, strike: MarketStrike) -> float:
    if sigma_f <= 0:
        sigma_f = 0.01

    if strike.strike_type == "range":
        if strike.low is None or strike.high is None:
            raise ValueError("Range strike requires both low and high.")
        lower_cdf = norm.cdf(strike.low, loc=mean_f, scale=sigma_f)
        upper_cdf = norm.cdf(strike.high, loc=mean_f, scale=sigma_f)
        return max(0.0, min(1.0, upper_cdf - lower_cdf))

    if strike.strike_type == "ge":
        if strike.low is None:
            raise ValueError("GE strike requires low.")
        return float(1.0 - norm.cdf(strike.low, loc=mean_f, scale=sigma_f))

    if strike.strike_type == "lt":
        if strike.high is None:
            raise ValueError("LT strike requires high.")
        return float(norm.cdf(strike.high, loc=mean_f, scale=sigma_f))

    raise ValueError(f"Unsupported strike type: {strike.strike_type}")


def fair_price_cents(probability: float) -> int:
    bounded = max(0.0, min(1.0, probability))
    return int(round(bounded * 100))

