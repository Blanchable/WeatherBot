"""Discover and parse weather markets from Kalshi listings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from kalshi.models import KalshiMarket
from pricing.distribution import MarketStrike
from weather.geo import match_city_from_text

WEATHER_KEYWORDS = ("temperature", "temp", "rain", "precip", "weather")
MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(slots=True)
class WeatherMarketMeta:
    ticker: str
    city_id: str
    market_type: str
    target_date: date
    strike: MarketStrike
    close_time_utc: datetime
    title: str
    subtitle: str
    volume_24h: int
    open_interest: int
    yes_bid: int | None
    yes_ask: int | None

    @property
    def spread_cents(self) -> int | None:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return self.yes_ask - self.yes_bid


def _safe_close_time(raw: datetime | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    if raw.tzinfo is None:
        return raw.replace(tzinfo=UTC)
    return raw.astimezone(UTC)


def _parse_market_type(text: str) -> str | None:
    lowered = text.lower()
    if "high temperature" in lowered or "high temp" in lowered:
        return "high_temp"
    if "low temperature" in lowered or "low temp" in lowered:
        return "low_temp"
    if "rain" in lowered or "precip" in lowered:
        return "precip"
    return None


def _parse_target_date(text: str, fallback: datetime) -> date:
    iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    human_match = re.search(
        r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:,?\s*(20\d{2}))?\b",
        text,
    )
    if human_match:
        month_raw, day_raw, year_raw = human_match.groups()
        month_num = MONTH_NAMES.get(month_raw.lower())
        if month_num:
            year = int(year_raw) if year_raw else fallback.year
            return date(year, month_num, int(day_raw))

    return fallback.date()


def _parse_strike_from_text(text: str, market: KalshiMarket) -> MarketStrike | None:
    if market.floor_strike is not None and market.cap_strike is not None:
        return MarketStrike("range", low=float(market.floor_strike), high=float(market.cap_strike))

    lowered = text.lower()
    strike_type_raw = (market.strike_type or "").lower()
    if strike_type_raw in {"between", "range"} and market.floor_strike is not None and market.cap_strike is not None:
        return MarketStrike("range", low=float(market.floor_strike), high=float(market.cap_strike))
    if strike_type_raw in {"above", "at_or_above", "ge"} and market.floor_strike is not None:
        return MarketStrike("ge", low=float(market.floor_strike))
    if strike_type_raw in {"below", "under", "lt"} and market.cap_strike is not None:
        return MarketStrike("lt", high=float(market.cap_strike))

    range_match = re.search(
        r"(?:between\s+)?(-?\d+(?:\.\d+)?)\s*(?:°|degrees?)?\s*(?:to|-|and)\s*(-?\d+(?:\.\d+)?)",
        lowered,
    )
    if range_match:
        low, high = map(float, range_match.groups())
        low, high = sorted((low, high))
        return MarketStrike("range", low=low, high=high)

    ge_match = re.search(
        r"(?:at least|>=|above|over|or higher|or more(?:\s+than)?)\s*(-?\d+(?:\.\d+)?)",
        lowered,
    )
    if ge_match:
        return MarketStrike("ge", low=float(ge_match.group(1)))

    lt_match = re.search(
        r"(?:below|under|<|or lower|or less(?:\s+than)?)\s*(-?\d+(?:\.\d+)?)",
        lowered,
    )
    if lt_match:
        return MarketStrike("lt", high=float(lt_match.group(1)))

    return None


def parse_weather_market(market: KalshiMarket, allowed_cities: set[str] | None = None) -> WeatherMarketMeta | None:
    if market.status and market.status.lower() != "open":
        return None

    title = market.title or ""
    subtitle = market.subtitle or ""
    search_blob = " ".join(
        part
        for part in [
            title,
            subtitle,
            market.yes_sub_title or "",
            market.no_sub_title or "",
            market.ticker,
        ]
        if part
    )

    if not any(keyword in search_blob.lower() for keyword in WEATHER_KEYWORDS):
        return None

    city = match_city_from_text(search_blob, allowed_cities=allowed_cities)
    if city is None:
        return None

    market_type = _parse_market_type(search_blob)
    if market_type is None:
        return None

    close_time = _safe_close_time(market.close_time or market.expiration_time)
    target_date = _parse_target_date(search_blob, fallback=close_time)
    strike = _parse_strike_from_text(search_blob, market)
    if strike is None:
        return None

    return WeatherMarketMeta(
        ticker=market.ticker,
        city_id=city.city_id,
        market_type=market_type,
        target_date=target_date,
        strike=strike,
        close_time_utc=close_time,
        title=title,
        subtitle=subtitle,
        volume_24h=int(market.volume_24h or market.volume or 0),
        open_interest=int(market.open_interest or 0),
        yes_bid=market.yes_bid,
        yes_ask=market.yes_ask,
    )


def discover_weather_markets(
    markets: list[KalshiMarket],
    *,
    allowed_cities: set[str] | None,
    max_markets: int,
    only_high_temp: bool = True,
) -> list[WeatherMarketMeta]:
    parsed: list[WeatherMarketMeta] = []
    for market in markets:
        meta = parse_weather_market(market, allowed_cities=allowed_cities)
        if meta is None:
            continue
        if only_high_temp and meta.market_type != "high_temp":
            continue
        parsed.append(meta)

    parsed.sort(key=lambda item: (item.volume_24h, item.open_interest), reverse=True)
    return parsed[:max_markets]

