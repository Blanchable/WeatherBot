"""Kalshi fee calculations.

Maker fee ≈ ceil(0.0175 * C * P * (1-P))  per contract
Taker fee ≈ ceil(0.07   * C * P * (1-P))  per contract

P is in dollars (price_cents / 100).
"""

from __future__ import annotations

import math


def maker_fee_per_contract(price_cents: int, contracts: int = 1) -> float:
    """Maker fee in dollars for the given price and contract count."""
    p = price_cents / 100.0
    raw = 0.0175 * contracts * p * (1.0 - p)
    return math.ceil(raw * 100) / 100.0


def taker_fee_per_contract(price_cents: int, contracts: int = 1) -> float:
    """Taker fee in dollars for the given price and contract count."""
    p = price_cents / 100.0
    raw = 0.07 * contracts * p * (1.0 - p)
    return math.ceil(raw * 100) / 100.0


def total_maker_fee(price_cents: int, contracts: int) -> float:
    return maker_fee_per_contract(price_cents, contracts)


def total_taker_fee(price_cents: int, contracts: int) -> float:
    return taker_fee_per_contract(price_cents, contracts)
