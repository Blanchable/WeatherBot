"""NWS Forecast retrieval — hourly & daily forecasts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from src.bot.logging import get_logger
from src.weather.nws_points import NWSGridPoint, NWS_HEADERS, resolve_point
from src.weather.geo import CityInfo

log = get_logger(__name__)


@dataclass
class HourlyPeriod:
    start_time: str
    end_time: str
    temperature: float
    temperature_unit: str
    probability_of_precipitation: float
    wind_speed: str
    short_forecast: str


@dataclass
class ForecastSnapshot:
    city_id: str
    fetched_at_utc: datetime
    forecast_date: str
    predicted_high: float | None
    predicted_low: float | None
    hourly_temps: list[float] = field(default_factory=list)
    hourly_precip_probs: list[float] = field(default_factory=list)
    raw_periods: list[dict] = field(default_factory=list)

    @property
    def is_stale(self) -> bool:
        age = (datetime.now(timezone.utc) - self.fetched_at_utc).total_seconds()
        return age > 3600


_grid_cache: dict[str, NWSGridPoint] = {}


async def _get_grid(city: CityInfo) -> NWSGridPoint:
    if city.code not in _grid_cache:
        _grid_cache[city.code] = await resolve_point(city.lat, city.lon)
    return _grid_cache[city.code]


async def fetch_hourly_forecast(city: CityInfo) -> list[HourlyPeriod]:
    grid = await _get_grid(city)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(grid.forecast_hourly_url, headers=NWS_HEADERS)
        resp.raise_for_status()
        data = resp.json()

    periods = []
    for p in data.get("properties", {}).get("periods", []):
        pop_raw = p.get("probabilityOfPrecipitation", {})
        pop_val = 0.0
        if isinstance(pop_raw, dict):
            pop_val = float(pop_raw.get("value", 0) or 0)

        periods.append(HourlyPeriod(
            start_time=p["startTime"],
            end_time=p["endTime"],
            temperature=float(p["temperature"]),
            temperature_unit=p.get("temperatureUnit", "F"),
            probability_of_precipitation=pop_val,
            wind_speed=p.get("windSpeed", ""),
            short_forecast=p.get("shortForecast", ""),
        ))

    return periods


def build_forecast_snapshot(
    city: CityInfo,
    target_date: str,
    hourly_periods: list[HourlyPeriod],
) -> ForecastSnapshot | None:
    day_periods = [
        p for p in hourly_periods
        if p.start_time[:10] == target_date
    ]
    if not day_periods:
        return None

    temps = [p.temperature for p in day_periods]
    precips = [p.probability_of_precipitation for p in day_periods]

    return ForecastSnapshot(
        city_id=city.code,
        fetched_at_utc=datetime.now(timezone.utc),
        forecast_date=target_date,
        predicted_high=max(temps) if temps else None,
        predicted_low=min(temps) if temps else None,
        hourly_temps=temps,
        hourly_precip_probs=precips,
        raw_periods=[
            {
                "start": p.start_time,
                "temp": p.temperature,
                "precip": p.probability_of_precipitation,
            }
            for p in day_periods
        ],
    )


async def get_forecast_for_city(
    city: CityInfo,
    target_date: str | None = None,
) -> ForecastSnapshot | None:
    if target_date is None:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        periods = await fetch_hourly_forecast(city)
    except Exception as exc:
        log.error("Failed to fetch forecast for %s: %s", city.code, exc)
        return None

    return build_forecast_snapshot(city, target_date, periods)
