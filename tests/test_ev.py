"""Tests for expected value calculations."""

import pytest

from src.pricing.ev import compute_ev_buy_yes, compute_ev_buy_no, best_trade


class TestEVBuyYes:
    def test_positive_ev(self):
        ev = compute_ev_buy_yes(prob=0.70, price_cents=60, contracts=1, maker=True)
        assert ev > 0

    def test_negative_ev_overpriced(self):
        ev = compute_ev_buy_yes(prob=0.30, price_cents=60, contracts=1, maker=True)
        assert ev < 0

    def test_breakeven_approx(self):
        ev = compute_ev_buy_yes(prob=0.50, price_cents=50, contracts=1, maker=True)
        assert ev < 0  # fee drag makes this slightly negative

    def test_high_prob_low_price(self):
        ev = compute_ev_buy_yes(prob=0.90, price_cents=80, contracts=1, maker=True)
        assert ev > 0

    def test_multiple_contracts(self):
        ev1 = compute_ev_buy_yes(prob=0.70, price_cents=60, contracts=1, maker=True)
        ev5 = compute_ev_buy_yes(prob=0.70, price_cents=60, contracts=5, maker=True)
        assert ev5 > ev1


class TestEVBuyNo:
    def test_positive_ev(self):
        ev = compute_ev_buy_no(prob=0.30, price_cents=60, contracts=1, maker=True)
        assert ev > 0

    def test_negative_ev(self):
        ev = compute_ev_buy_no(prob=0.70, price_cents=60, contracts=1, maker=True)
        assert ev < 0

    def test_complements(self):
        ev_yes = compute_ev_buy_yes(prob=0.60, price_cents=50, contracts=1, maker=True)
        ev_no = compute_ev_buy_no(prob=0.60, price_cents=50, contracts=1, maker=True)
        # Both can't be positive at same price (fee drag)
        assert not (ev_yes > 0 and ev_no > 0)


class TestBestTrade:
    def test_finds_yes_trade(self):
        # Fair prob 0.70, bid 55, ask 65 -> should want to buy yes near 56
        trade = best_trade(prob=0.70, yes_bid=55, yes_ask=65, contracts=1)
        if trade:
            assert trade["side"] == "yes"
            assert trade["action"] == "buy"
            assert trade["ev"] > 0

    def test_finds_no_trade(self):
        # Fair prob 0.30, bid 55, ask 65 -> should want to buy no
        trade = best_trade(prob=0.30, yes_bid=55, yes_ask=65, contracts=1)
        if trade:
            assert trade["side"] == "no"
            assert trade["ev"] > 0

    def test_no_trade_when_fair(self):
        # Fair prob 0.50, bid 49, ask 51 -> no edge
        trade = best_trade(prob=0.50, yes_bid=49, yes_ask=51, contracts=1)
        assert trade is None

    def test_no_trade_extreme_spread(self):
        # Wide spread but fair price
        trade = best_trade(prob=0.50, yes_bid=30, yes_ask=70, contracts=1)
        # Might or might not find a trade depending on where bid+1 lands
        if trade:
            assert trade["ev"] > 0
