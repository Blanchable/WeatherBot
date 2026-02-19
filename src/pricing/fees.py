"""Kalshi fee approximations with round-up-to-cent semantics."""

from __future__ import annotations

import math

MAKER_RATE = 0.0175
TAKER_RATE = 0.07


def _round_up_cent(amount_dollars: float) -> float:
    return math.ceil(amount_dollars * 100.0) / 100.0


def estimate_fee_dollars(
    *,
    contracts: int,
    price_cents: int,
    maker: bool = True,
) -> float:
    if contracts <= 0:
        return 0.0
    prob = max(0.0, min(1.0, price_cents / 100.0))
    rate = MAKER_RATE if maker else TAKER_RATE
    raw_fee = rate * contracts * prob * (1.0 - prob)
    return _round_up_cent(raw_fee)


def fee_per_contract_dollars(*, contracts: int, price_cents: int, maker: bool = True) -> float:
    total = estimate_fee_dollars(contracts=contracts, price_cents=price_cents, maker=maker)
    if contracts <= 0:
        return 0.0
    return total / contracts

