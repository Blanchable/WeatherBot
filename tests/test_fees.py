from pricing.fees import estimate_fee_dollars, fee_per_contract_dollars


def test_maker_fee_rounds_up_to_cent() -> None:
    fee = estimate_fee_dollars(contracts=10, price_cents=60, maker=True)
    assert fee == 0.05


def test_taker_fee_rounds_up_to_cent() -> None:
    fee = estimate_fee_dollars(contracts=10, price_cents=60, maker=False)
    assert fee == 0.17


def test_fee_per_contract() -> None:
    per_contract = fee_per_contract_dollars(contracts=10, price_cents=60, maker=True)
    assert per_contract == 0.005

