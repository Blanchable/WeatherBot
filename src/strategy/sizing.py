"""Position sizing with exposure limits."""

from __future__ import annotations

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.storage.db import Database

log = get_logger(__name__)


def compute_max_new_contracts(
    ticker: str,
    city: str,
    price_cents: int,
    db: Database,
    is_paper: bool = True,
) -> int:
    """Compute maximum new contracts we can add, respecting all exposure limits."""
    settings = get_settings()

    positions = db.get_positions(is_paper)
    orders = db.get_open_orders(is_paper)

    gross_exposure = 0.0
    net_exposure = 0.0
    city_exposure = 0.0
    market_exposure = 0.0

    for p in positions:
        exp_d = p["quantity"] * p["avg_price_cents"] / 100.0
        gross_exposure += abs(exp_d)
        net_exposure += exp_d if p["side"] == "yes" else -exp_d

        mkt = db.conn.execute(
            "SELECT city FROM weather_markets WHERE ticker = ?", (p["ticker"],)
        ).fetchone()
        if mkt and mkt["city"] == city:
            city_exposure += abs(exp_d)
        if p["ticker"] == ticker:
            market_exposure += abs(exp_d)

    for o in orders:
        exp_d = o["quantity"] * o["price_cents"] / 100.0
        gross_exposure += abs(exp_d)
        mkt = db.conn.execute(
            "SELECT city FROM weather_markets WHERE ticker = ?", (o["ticker"],)
        ).fetchone()
        if mkt and mkt["city"] == city:
            city_exposure += abs(exp_d)
        if o["ticker"] == ticker:
            market_exposure += abs(exp_d)

    price_d = price_cents / 100.0
    if price_d <= 0:
        return 0

    max_by_gross = max(0, int((settings.max_gross_exposure_dollars - gross_exposure) / price_d))
    max_by_net = max(0, int((settings.max_net_exposure_dollars - abs(net_exposure)) / price_d))
    max_by_city = max(0, int((settings.max_exposure_per_city_dollars - city_exposure) / price_d))
    max_by_market = max(0, int((settings.max_exposure_per_market_dollars - market_exposure) / price_d))
    max_by_order = settings.max_order_size_contracts

    result = min(max_by_gross, max_by_net, max_by_city, max_by_market, max_by_order)
    return max(0, result)
