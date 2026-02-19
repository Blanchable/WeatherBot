"""Expected value calculations net of fees."""

from __future__ import annotations

from dataclasses import dataclass

from pricing.fees import fee_per_contract_dollars


@dataclass(frozen=True, slots=True)
class EVResult:
    side: str
    probability: float
    price_cents: int
    ev_dollars_per_contract: float
    fee_dollars_per_contract: float


def ev_buy_yes(probability_yes: float, price_cents: int, maker: bool = True) -> EVResult:
    p = max(0.0, min(1.0, probability_yes))
    price_d = price_cents / 100.0
    fee = fee_per_contract_dollars(contracts=1, price_cents=price_cents, maker=maker)
    ev = p - price_d - fee
    return EVResult(
        side="yes",
        probability=p,
        price_cents=price_cents,
        ev_dollars_per_contract=ev,
        fee_dollars_per_contract=fee,
    )


def ev_buy_no(probability_yes: float, no_price_cents: int, maker: bool = True) -> EVResult:
    p_yes = max(0.0, min(1.0, probability_yes))
    p_no = 1.0 - p_yes
    price_d = no_price_cents / 100.0
    fee = fee_per_contract_dollars(contracts=1, price_cents=no_price_cents, maker=maker)
    ev = p_no - price_d - fee
    return EVResult(
        side="no",
        probability=p_no,
        price_cents=no_price_cents,
        ev_dollars_per_contract=ev,
        fee_dollars_per_contract=fee,
    )

