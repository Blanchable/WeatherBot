"""NWS forecast fetcher and normalized snapshot objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import numpy as np

from weather.geo import City
from weather.nws_points import NWSPointMetadata


def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    return dt.astimezone(UTC)


@dataclass(slots=True)
class ForecastSnapshot:
    city_id: str
    fetched_at_utc: datetime
    forecast_valid_from: datetime
    hourly_times_utc: list[datetime]
    hourly_temps_f: list[float]
    daily_highs_f: list[float]
    daily_lows_f: list[float]
    precip_probability_next_48h: list[float]
    confidence_spread_f: float
    raw_json: str

    def age_minutes(self, now_utc: datetime) -> float:
        return (now_utc - self.fetched_at_utc).total_seconds() / 60.0


class NWSForecastClient:
    def __init__(self, user_agent: str = "kalshi-weather-bot/0.1 (contact: local)") -> None:
        self.client = httpx.Client(
            timeout=10.0,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/geo+json",
            },
        )

    def close(self) -> None:
        self.client.close()

    def fetch_forecast(self, city: City, point: NWSPointMetadata) -> ForecastSnapshot:
        now = datetime.now(UTC)
        hourly_resp = self.client.get(point.forecast_hourly_url)
        hourly_resp.raise_for_status()
        daily_resp = self.client.get(point.forecast_url)
        daily_resp.raise_for_status()

        hourly_data = hourly_resp.json()
        daily_data = daily_resp.json()
        hourly_periods = hourly_data.get("properties", {}).get("periods", [])[:48]
        daily_periods = daily_data.get("properties", {}).get("periods", [])

        hourly_times: list[datetime] = []
        hourly_temps: list[float] = []
        precip_values: list[float] = []
        for period in hourly_periods:
            start = period.get("startTime")
            temp = period.get("temperature")
            pop = period.get("probabilityOfPrecipitation", {}).get("value")
            if start is None or temp is None:
                continue
            hourly_times.append(_parse_iso(start))
            hourly_temps.append(float(temp))
            precip_values.append(float(pop or 0.0))

        daily_highs: list[float] = []
        daily_lows: list[float] = []
        by_day: dict[datetime.date, list[float]] = {}
        for period in daily_periods:
            temp = period.get("temperature")
            start = period.get("startTime")
            if temp is None or start is None:
                continue
            date_key = _parse_iso(start).date()
            by_day.setdefault(date_key, []).append(float(temp))

        for day in sorted(by_day.keys())[:7]:
            values = by_day[day]
            daily_highs.append(max(values))
            daily_lows.append(min(values))

        spread = float(np.std(hourly_temps)) if hourly_temps else 0.0
        valid_from = hourly_times[0] if hourly_times else now
        raw_json = json.dumps({"hourly": hourly_data, "daily": daily_data}, separators=(",", ":"))
        return ForecastSnapshot(
            city_id=city.city_id,
            fetched_at_utc=now,
            forecast_valid_from=valid_from,
            hourly_times_utc=hourly_times,
            hourly_temps_f=hourly_temps,
            daily_highs_f=daily_highs,
            daily_lows_f=daily_lows,
            precip_probability_next_48h=precip_values,
            confidence_spread_f=spread,
            raw_json=raw_json,
        )

