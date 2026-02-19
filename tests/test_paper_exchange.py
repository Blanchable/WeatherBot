from sim.paper_exchange import BookSnapshot, PaperExchange


def test_paper_exchange_initializes_rng_with_slots() -> None:
    exchange = PaperExchange(rng_seed=123)
    assert exchange.rng is not None


def test_crossing_order_fills_immediately() -> None:
    exchange = PaperExchange(rng_seed=123)
    exchange.update_book(BookSnapshot(ticker="TEST", best_yes_bid=40, best_yes_ask=45, volume_24h=1000))
    order_id = exchange.place_limit_order(
        ticker="TEST",
        side="yes",
        action="buy",
        price_cents=45,
        contracts=2,
        city_id="NYC",
    )
    fills = exchange.step()
    assert len(fills) >= 1
    assert fills[0].order_id == order_id
