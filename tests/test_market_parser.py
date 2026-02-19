from datetime import UTC, datetime

from kalshi.models import KalshiMarket
from strategy.market_discovery import discover_weather_markets, parse_weather_market


def test_parse_temperature_range_market() -> None:
    market = KalshiMarket(
        ticker="KXHNYC-26FEB20-T74.75",
        title="NYC High Temperature on Feb 20, 2026",
        sub_title="74° to 75°",
        status="open",
        close_time=datetime(2026, 2, 20, 23, 0, tzinfo=UTC),
        yes_bid=51,
        yes_ask=59,
        volume_24h=1200,
        open_interest=800,
    )

    meta = parse_weather_market(market, allowed_cities={"NYC"})
    assert meta is not None
    assert meta.city_id == "NYC"
    assert meta.market_type == "high_temp"
    assert meta.strike.strike_type == "range"
    assert meta.strike.low == 74.0
    assert meta.strike.high == 75.0
    assert meta.target_date.year == 2026


def test_parse_at_least_market() -> None:
    market = KalshiMarket(
        ticker="KXHCHI-26FEB20-ATLEAST70",
        title="Chicago High Temperature Feb 20, 2026",
        sub_title="At least 70°",
        status="open",
        close_time=datetime(2026, 2, 20, 23, 0, tzinfo=UTC),
        yes_bid=30,
        yes_ask=38,
        volume_24h=2000,
    )
    meta = parse_weather_market(market, allowed_cities={"CHI"})
    assert meta is not None
    assert meta.strike.strike_type == "ge"
    assert meta.strike.low == 70.0


def test_discover_filters_to_high_temp() -> None:
    markets = [
        KalshiMarket(
            ticker="RAIN-TEST",
            title="Will it rain in NYC on Feb 20, 2026",
            sub_title="Yes",
            status="open",
            close_time=datetime(2026, 2, 20, 23, 0, tzinfo=UTC),
            yes_bid=45,
            yes_ask=55,
            volume_24h=10000,
        ),
        KalshiMarket(
            ticker="TEMP-TEST",
            title="NYC High Temperature on Feb 20, 2026",
            sub_title="70° to 71°",
            status="open",
            close_time=datetime(2026, 2, 20, 23, 0, tzinfo=UTC),
            yes_bid=45,
            yes_ask=55,
            volume_24h=200,
        ),
    ]
    found = discover_weather_markets(
        markets,
        allowed_cities={"NYC"},
        max_markets=5,
        only_high_temp=True,
    )
    assert len(found) == 1
    assert found[0].ticker == "TEMP-TEST"

