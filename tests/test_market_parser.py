"""Tests for weather market title parsing and discovery."""

import pytest
from unittest.mock import MagicMock

from src.strategy.market_discovery import (
    parse_weather_market,
    is_weather_market,
    _parse_strike,
    _detect_market_type,
    _parse_date_from_title,
    WeatherMarketMeta,
)
from src.kalshi.models import Market


def _make_market(title: str, **kwargs) -> Market:
    defaults = {
        "ticker": "TEST-TICKER",
        "event_ticker": "TEST-EVENT",
        "title": title,
        "status": "open",
        "close_time": "2026-02-20T23:00:00Z",
        "yes_bid": 40,
        "yes_ask": 60,
        "volume_24h": 1000,
    }
    defaults.update(kwargs)
    return Market(**defaults)


class TestIsWeatherMarket:
    def test_high_temp_market(self):
        m = _make_market("Will the high temperature in New York be 75° to 79° on Feb 20?")
        assert is_weather_market(m) is True

    def test_low_temp_market(self):
        m = _make_market("Low temperature in Chicago below 32° on February 21?")
        assert is_weather_market(m) is True

    def test_rain_market(self):
        m = _make_market("Will it rain in Miami on Feb 22?")
        assert is_weather_market(m) is True

    def test_non_weather_market(self):
        m = _make_market("Will Bitcoin hit $100k by March?")
        assert is_weather_market(m) is False

    def test_city_with_degree_sign(self):
        m = _make_market("Los Angeles 85° or higher on Feb 25?")
        assert is_weather_market(m) is True


class TestParseStrike:
    def test_range_with_degree(self):
        low, high, op = _parse_strike("75° to 79°")
        assert op == "range"
        assert low == 75.0
        assert high == 79.0

    def test_range_with_f(self):
        low, high, op = _parse_strike("75°F to 79°F")
        assert op == "range"
        assert low == 75.0
        assert high == 79.0

    def test_gte(self):
        low, high, op = _parse_strike("at least 80°F")
        assert op == "gte"
        assert low == 80.0
        assert high is None

    def test_gte_or_more(self):
        low, high, op = _parse_strike("85° or more")
        assert op == "gte"
        assert low == 85.0

    def test_lte(self):
        low, high, op = _parse_strike("below 32°F")
        assert op == "lte"
        assert high == 32.0

    def test_lte_or_less(self):
        low, high, op = _parse_strike("30° or less")
        assert op == "lte"
        assert high == 30.0

    def test_two_degree_signs(self):
        low, high, op = _parse_strike("between 70° and 75°")
        assert op == "range"
        assert low == 70.0
        assert high == 75.0

    def test_no_match(self):
        low, high, op = _parse_strike("no numbers here")
        assert op == "unknown"


class TestDetectMarketType:
    def test_high_temp(self):
        assert _detect_market_type("High temperature in NYC") == "high_temp"

    def test_low_temp(self):
        assert _detect_market_type("Low temperature in Chicago") == "low_temp"

    def test_rain(self):
        assert _detect_market_type("Will it rain in Dallas?") == "rain"

    def test_generic_temp(self):
        assert _detect_market_type("temperature in LA above 90") == "high_temp"

    def test_unknown(self):
        assert _detect_market_type("Some random market") == "unknown"


class TestParseDateFromTitle:
    def test_month_day(self):
        result = _parse_date_from_title("High temp on February 20?")
        assert result is not None
        assert result.endswith("-02-20")

    def test_month_day_year(self):
        result = _parse_date_from_title("High temp on Feb 20, 2026?")
        assert result == "2026-02-20"

    def test_iso_date(self):
        result = _parse_date_from_title("Temp on 2026-03-15?")
        assert result == "2026-03-15"

    def test_slash_date(self):
        result = _parse_date_from_title("Temp on 2/20?")
        assert result is not None
        assert result.endswith("-02-20")


class TestParseWeatherMarket:
    def test_full_parse_range(self):
        m = _make_market(
            "Will the high temperature in New York be 75° to 79° on February 20, 2026?",
        )
        meta = parse_weather_market(m)
        assert meta is not None
        assert meta.city == "NYC"
        assert meta.market_type == "high_temp"
        assert meta.strike_op == "range"
        assert meta.strike_low == 75.0
        assert meta.strike_high == 79.0
        assert meta.market_date == "2026-02-20"

    def test_full_parse_gte(self):
        m = _make_market(
            "Will the high temperature in Los Angeles be at least 90°F on Feb 25, 2026?",
        )
        meta = parse_weather_market(m)
        assert meta is not None
        assert meta.city == "LA"
        assert meta.strike_op == "gte"
        assert meta.strike_low == 90.0

    def test_non_weather_returns_none(self):
        m = _make_market("Will Bitcoin hit $100k?")
        assert parse_weather_market(m) is None

    def test_unknown_city_returns_none(self):
        m = _make_market("High temperature in Timbuktu 80° to 85°")
        assert parse_weather_market(m) is None

    def test_chicago_low_temp(self):
        m = _make_market(
            "Will the low temperature in Chicago be below 10°F on January 15, 2026?",
        )
        meta = parse_weather_market(m)
        assert meta is not None
        assert meta.city == "CHI"
        assert meta.market_type == "low_temp"
        assert meta.strike_op == "lte"
        assert meta.strike_high == 10.0
