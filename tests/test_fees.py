"""Tests for fee calculations."""

import pytest
import math

from src.pricing.fees import (
    maker_fee_per_contract,
    taker_fee_per_contract,
    total_maker_fee,
    total_taker_fee,
)


class TestMakerFee:
    def test_at_50c(self):
        fee = maker_fee_per_contract(50, 1)
        # 0.0175 * 1 * 0.5 * 0.5 = 0.004375 -> ceil to $0.01
        assert fee == 0.01

    def test_at_80c(self):
        fee = maker_fee_per_contract(80, 1)
        # 0.0175 * 1 * 0.8 * 0.2 = 0.0028 -> ceil to $0.01
        assert fee == 0.01

    def test_at_10c(self):
        fee = maker_fee_per_contract(10, 1)
        # 0.0175 * 1 * 0.1 * 0.9 = 0.001575 -> ceil to $0.01
        assert fee == 0.01

    def test_multiple_contracts(self):
        fee = maker_fee_per_contract(50, 10)
        # 0.0175 * 10 * 0.5 * 0.5 = 0.04375 -> ceil to $0.05
        assert fee == 0.05

    def test_at_1c(self):
        fee = maker_fee_per_contract(1, 1)
        # 0.0175 * 1 * 0.01 * 0.99 = 0.00017325 -> ceil to $0.01
        assert fee == 0.01

    def test_at_99c(self):
        fee = maker_fee_per_contract(99, 1)
        assert fee == 0.01

    def test_fee_is_always_positive(self):
        for price in range(1, 100):
            fee = maker_fee_per_contract(price, 1)
            assert fee > 0

    def test_fee_is_rounded_up(self):
        for price in range(1, 100):
            fee = maker_fee_per_contract(price, 1)
            assert fee == math.ceil(fee * 100) / 100


class TestTakerFee:
    def test_at_50c(self):
        fee = taker_fee_per_contract(50, 1)
        # 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> ceil to $0.02
        assert fee == 0.02

    def test_taker_higher_than_maker(self):
        for price in range(5, 96):
            maker = maker_fee_per_contract(price, 1)
            taker = taker_fee_per_contract(price, 1)
            assert taker >= maker, f"Taker fee should be >= maker at {price}c"

    def test_multiple_contracts(self):
        fee = taker_fee_per_contract(50, 10)
        # 0.07 * 10 * 0.5 * 0.5 = 0.175 -> ceil to $0.18
        assert fee == 0.18


class TestTotalFees:
    def test_total_maker_matches(self):
        for price in range(1, 100):
            for qty in [1, 5, 10]:
                assert total_maker_fee(price, qty) == maker_fee_per_contract(price, qty)

    def test_total_taker_matches(self):
        for price in range(1, 100):
            for qty in [1, 5, 10]:
                assert total_taker_fee(price, qty) == taker_fee_per_contract(price, qty)
