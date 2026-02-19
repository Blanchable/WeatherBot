from datetime import UTC, datetime

from pricing.distribution import MarketStrike, fair_price_cents, predicted_daily_high, probability_for_strike


def test_predicted_daily_high_selects_target_day() -> None:
    times = [
        datetime(2026, 2, 20, 8, tzinfo=UTC),
        datetime(2026, 2, 20, 14, tzinfo=UTC),
        datetime(2026, 2, 21, 14, tzinfo=UTC),
    ]
    temps = [60.0, 71.0, 80.0]
    result = predicted_daily_high(times, temps, target_date=times[0].date())
    assert result == 71.0


def test_probability_range_market() -> None:
    strike = MarketStrike("range", low=74, high=76)
    probability = probability_for_strike(mean_f=75.0, sigma_f=1.5, strike=strike)
    assert 0.49 <= probability <= 0.51


def test_probability_ge_market() -> None:
    strike = MarketStrike("ge", low=72)
    probability = probability_for_strike(mean_f=70.0, sigma_f=2.0, strike=strike)
    assert 0.15 <= probability <= 0.17
    assert fair_price_cents(probability) == 16

