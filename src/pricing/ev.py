"""Expected value calculation for weather market trades."""

from __future__ import annotations

from src.pricing.fees import maker_fee_per_contract, taker_fee_per_contract
from src.bot.config import get_settings
from src.bot.logging import get_logger

log = get_logger(__name__)


def compute_ev_buy_yes(
    prob: float,
    price_cents: int,
    contracts: int = 1,
    maker: bool = True,
) -> float:
    """EV in dollars for buying YES at price_cents.

    If contract resolves YES, you receive $1.00 per contract.
    Cost = price_cents/100 * contracts + fee.
    """
    price_d = price_cents / 100.0
    if maker:
        fee = maker_fee_per_contract(price_cents, contracts)
    else:
        fee = taker_fee_per_contract(price_cents, contracts)

    ev = prob * 1.0 * contracts - price_d * contracts - fee
    return ev


def compute_ev_buy_no(
    prob: float,
    price_cents: int,
    contracts: int = 1,
    maker: bool = True,
) -> float:
    """EV for buying NO. prob is the probability of YES."""
    no_prob = 1.0 - prob
    price_d = price_cents / 100.0
    if maker:
        fee = maker_fee_per_contract(price_cents, contracts)
    else:
        fee = taker_fee_per_contract(price_cents, contracts)

    ev = no_prob * 1.0 * contracts - price_d * contracts - fee
    return ev


def best_trade(
    prob: float,
    yes_bid: int,
    yes_ask: int,
    contracts: int = 1,
) -> dict | None:
    """Determine best available maker trade given fair probability.

    Returns dict with keys: side, action, price_cents, ev, or None if no trade meets threshold.
    """
    settings = get_settings()
    min_ev = settings.min_ev_dollars_per_contract * contracts

    candidates = []

    # Buy YES: place bid at yes_bid + 1 (improving the bid)
    buy_yes_price = yes_bid + 1
    if 1 <= buy_yes_price <= 99:
        ev_yes = compute_ev_buy_yes(prob, buy_yes_price, contracts, maker=True)
        if ev_yes >= min_ev:
            candidates.append({
                "side": "yes",
                "action": "buy",
                "price_cents": buy_yes_price,
                "ev": ev_yes,
                "prob": prob,
            })

    # Buy NO: no_price = 100 - yes_ask + 1 (improving the no bid)
    no_price = 100 - yes_ask + 1
    if 1 <= no_price <= 99:
        ev_no = compute_ev_buy_no(prob, no_price, contracts, maker=True)
        if ev_no >= min_ev:
            candidates.append({
                "side": "no",
                "action": "buy",
                "price_cents": no_price,
                "ev": ev_no,
                "prob": prob,
            })

    if not candidates:
        return None

    return max(candidates, key=lambda c: c["ev"])
