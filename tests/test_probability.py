"""Tests for probability distribution calculations."""

import pytest
import math

from src.pricing.distribution import (
    prob_in_range,
    prob_gte,
    prob_lte,
    compute_fair_price,
    get_sigma,
)


class TestProbInRange:
    def test_symmetric_range_around_mean(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=73.0, high=77.0)
        assert 0.6 < prob < 0.7  # ~68% for +/- 1 sigma

    def test_wide_range(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=69.0, high=81.0)
        assert prob > 0.99

    def test_narrow_range(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=74.9, high=75.1)
        assert prob < 0.10

    def test_range_far_from_mean(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=85.0, high=90.0)
        assert prob < 0.001

    def test_only_lower_bound(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=75.0, high=None)
        assert abs(prob - 0.5) < 0.01

    def test_only_upper_bound(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=None, high=75.0)
        assert abs(prob - 0.5) < 0.01

    def test_no_bounds(self):
        prob = prob_in_range(mean=75.0, sigma=2.0, low=None, high=None)
        assert prob == 1.0


class TestProbGte:
    def test_at_mean(self):
        prob = prob_gte(mean=75.0, sigma=2.0, threshold=75.0)
        assert abs(prob - 0.5) < 0.01

    def test_below_mean(self):
        prob = prob_gte(mean=75.0, sigma=2.0, threshold=73.0)
        assert prob > 0.8

    def test_above_mean(self):
        prob = prob_gte(mean=75.0, sigma=2.0, threshold=77.0)
        assert prob < 0.2

    def test_far_above(self):
        prob = prob_gte(mean=75.0, sigma=2.0, threshold=85.0)
        assert prob < 0.001


class TestProbLte:
    def test_at_mean(self):
        prob = prob_lte(mean=75.0, sigma=2.0, threshold=75.0)
        assert abs(prob - 0.5) < 0.01

    def test_above_mean(self):
        prob = prob_lte(mean=75.0, sigma=2.0, threshold=77.0)
        assert prob > 0.8

    def test_below_mean(self):
        prob = prob_lte(mean=75.0, sigma=2.0, threshold=73.0)
        assert prob < 0.2

    def test_complements(self):
        gte = prob_gte(mean=75.0, sigma=2.0, threshold=78.0)
        lte = prob_lte(mean=75.0, sigma=2.0, threshold=78.0)
        assert abs(gte + lte - 1.0) < 1e-10


class TestComputeFairPrice:
    def test_range_market(self):
        fair = compute_fair_price(
            predicted_value=75.0,
            sigma=2.0,
            strike_low=73.0,
            strike_high=77.0,
            strike_op="range",
        )
        assert 0.6 < fair < 0.7

    def test_gte_market(self):
        fair = compute_fair_price(
            predicted_value=80.0,
            sigma=2.0,
            strike_low=75.0,
            strike_high=None,
            strike_op="gte",
        )
        assert fair > 0.98

    def test_lte_market(self):
        fair = compute_fair_price(
            predicted_value=75.0,
            sigma=2.0,
            strike_low=None,
            strike_high=80.0,
            strike_op="lte",
        )
        assert fair > 0.98

    def test_unknown_op_returns_half(self):
        fair = compute_fair_price(
            predicted_value=75.0,
            sigma=2.0,
            strike_low=None,
            strike_high=None,
            strike_op="invalid",
        )
        assert fair == 0.5

    def test_probabilities_sum_to_one_for_adjacent_ranges(self):
        """Adjacent range markets covering the full space should sum ~1."""
        sigma = 2.0
        mean = 75.0
        ranges = [(60, 70), (70, 72), (72, 74), (74, 76), (76, 78), (78, 80), (80, 90)]
        total = sum(
            compute_fair_price(mean, sigma, lo, hi, "range")
            for lo, hi in ranges
        )
        assert abs(total - 1.0) < 0.01


class TestGetSigma:
    def test_same_day(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sigma = get_sigma("NYC", today)
        assert 1.0 <= sigma <= 2.0

    def test_far_future(self):
        sigma = get_sigma("NYC", "2030-01-01")
        assert sigma >= 2.5
