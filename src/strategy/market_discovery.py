"""Discover and parse Kalshi weather markets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from src.bot.config import get_settings
from src.bot.logging import get_logger
from src.kalshi.models import Market
from src.weather.geo import find_city_in_text, CITY_REGISTRY

log = get_logger(__name__)


@dataclass
class WeatherMarketMeta:
    ticker: str
    event_ticker: str
    city: str
    market_date: str
    market_type: str  # 'high_temp', 'low_temp', 'rain'
    strike_low: float | None
    strike_high: float | None
    strike_op: str  # 'range', 'gte', 'lte'
    close_time: str
    title: str

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "event_ticker": self.event_ticker,
            "city": self.city,
            "market_date": self.market_date,
            "market_type": self.market_type,
            "strike_low": self.strike_low,
            "strike_high": self.strike_high,
            "strike_op": self.strike_op,
            "close_time": self.close_time,
            "status": "open",
        }


# Patterns for parsing market titles
_TEMP_RANGE_PAT = re.compile(
    r"(\d+)\s*°?\s*(?:F|to)\s*(\d+)\s*°?\s*F?",
    re.IGNORECASE,
)
_TEMP_GTE_PAT = re.compile(
    r"(?:at\s+least|above|>=?|or\s+(?:more|higher|above))\s*(\d+)\s*°?\s*F?",
    re.IGNORECASE,
)
_TEMP_LTE_PAT = re.compile(
    r"(?:below|under|<=?|at\s+most|or\s+(?:less|lower|below))\s*(\d+)\s*°?\s*F?",
    re.IGNORECASE,
)
_MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)
_DATE_PAT = re.compile(
    rf"(\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?|(?:{_MONTH_NAMES})\s+\d{{1,2}}(?:,?\s+\d{{4}})?)",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_date_from_title(title: str) -> str | None:
    """Try to extract a date string (YYYY-MM-DD) from the title."""
    m = _DATE_PAT.search(title)
    if not m:
        return None

    raw = m.group(1).strip()

    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw

    if "/" in raw:
        parts = raw.split("/")
        if len(parts) >= 2:
            month, day = int(parts[0]), int(parts[1])
            year = int(parts[2]) if len(parts) > 2 else datetime.now(timezone.utc).year
            if year < 100:
                year += 2000
            return f"{year:04d}-{month:02d}-{day:02d}"

    parts = raw.replace(",", "").split()
    if len(parts) >= 2:
        month_str = parts[0].lower()
        day = int(parts[1])
        year = int(parts[2]) if len(parts) > 2 else datetime.now(timezone.utc).year
        month = _MONTH_MAP.get(month_str)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def _detect_market_type(title: str) -> str:
    title_lower = title.lower()
    if "high" in title_lower and "temp" in title_lower:
        return "high_temp"
    if "low" in title_lower and "temp" in title_lower:
        return "low_temp"
    if any(w in title_lower for w in ("rain", "precip", "snow", "precipitation")):
        return "rain"
    if "temp" in title_lower:
        return "high_temp"
    return "unknown"


def _parse_strike(title: str) -> tuple[float | None, float | None, str]:
    """Parse temperature strike from title. Returns (low, high, op)."""
    m_range = _TEMP_RANGE_PAT.search(title)
    if m_range:
        lo, hi = float(m_range.group(1)), float(m_range.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi, "range"

    m_gte = _TEMP_GTE_PAT.search(title)
    if m_gte:
        return float(m_gte.group(1)), None, "gte"

    m_lte = _TEMP_LTE_PAT.search(title)
    if m_lte:
        return None, float(m_lte.group(1)), "lte"

    digits = re.findall(r"(\d+)\s*°", title)
    if len(digits) == 2:
        a, b = float(digits[0]), float(digits[1])
        if a > b:
            a, b = b, a
        return a, b, "range"
    elif len(digits) == 1:
        val = float(digits[0])
        title_lower = title.lower()
        if "or more" in title_lower or "or higher" in title_lower or "above" in title_lower:
            return val, None, "gte"
        elif "or less" in title_lower or "or lower" in title_lower or "below" in title_lower:
            return None, val, "lte"
        return val, None, "gte"

    return None, None, "unknown"


def is_weather_market(market: Market) -> bool:
    title_lower = market.title.lower()
    weather_keywords = [
        "temperature", "high temp", "low temp", "rain",
        "precipitation", "snow", "weather",
    ]
    if any(kw in title_lower for kw in weather_keywords):
        return True
    city = find_city_in_text(market.title)
    if city and ("°" in market.title or "temp" in title_lower):
        return True
    return False


def parse_weather_market(market: Market) -> WeatherMarketMeta | None:
    if not is_weather_market(market):
        return None

    city = find_city_in_text(market.title)
    if not city:
        return None

    market_type = _detect_market_type(market.title)
    if market_type == "unknown":
        return None

    market_date = _parse_date_from_title(market.title)
    if not market_date:
        if market.close_time:
            market_date = market.close_time[:10]
        else:
            return None

    strike_low, strike_high, strike_op = _parse_strike(market.title)
    if strike_op == "unknown":
        return None

    return WeatherMarketMeta(
        ticker=market.ticker,
        event_ticker=market.event_ticker,
        city=city,
        market_date=market_date,
        market_type=market_type,
        strike_low=strike_low,
        strike_high=strike_high,
        strike_op=strike_op,
        close_time=market.close_time,
        title=market.title,
    )


def filter_tradeable_markets(
    markets: list[Market],
    allowed_cities: list[str] | None = None,
) -> list[WeatherMarketMeta]:
    """Parse and filter weather markets for trading."""
    settings = get_settings()
    if allowed_cities is None:
        allowed_cities = settings.city_list

    allowed_set = {c.upper() for c in allowed_cities}
    results: list[WeatherMarketMeta] = []

    for m in markets:
        if m.status != "open":
            continue
        meta = parse_weather_market(m)
        if meta is None:
            continue
        if meta.city not in allowed_set:
            continue
        if meta.market_type not in ("high_temp", "low_temp"):
            continue
        if m.spread < settings.min_spread_cents:
            continue
        if m.volume_24h < settings.min_24h_volume:
            log.debug("Skipping %s: 24h volume %d < %d", m.ticker, m.volume_24h, settings.min_24h_volume)
            continue

        now = datetime.now(timezone.utc)
        try:
            close_dt = datetime.fromisoformat(meta.close_time.replace("Z", "+00:00"))
            secs_to_close = (close_dt - now).total_seconds()
            if secs_to_close < settings.no_trade_window_seconds:
                log.debug("Skipping %s: within no-trade window", m.ticker)
                continue
        except (ValueError, TypeError):
            pass

        results.append(meta)

    results.sort(key=lambda x: (x.market_date, x.city, x.strike_low or 0))

    if len(results) > settings.max_markets:
        results = results[: settings.max_markets]

    return results
