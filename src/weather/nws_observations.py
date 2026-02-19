"""NWS Observations — fetch latest station observations (optional)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.bot.logging import get_logger
from src.weather.nws_points import NWS_HEADERS, resolve_point
from src.weather.geo import CityInfo

log = get_logger(__name__)


@dataclass
class Observation:
    station_id: str
    timestamp: str
    temperature_f: float | None
    humidity: float | None
    wind_speed_mph: float | None
    description: str


def _c_to_f(c: float | None) -> float | None:
    if c is None:
        return None
    return c * 9.0 / 5.0 + 32.0


async def get_latest_observation(city: CityInfo) -> Observation | None:
    try:
        grid = await resolve_point(city.lat, city.lon)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(grid.observation_stations_url, headers=NWS_HEADERS)
            resp.raise_for_status()
            stations = resp.json().get("features", [])
            if not stations:
                return None

            station_url = stations[0]["id"] + "/observations/latest"
            resp2 = await client.get(station_url, headers=NWS_HEADERS)
            resp2.raise_for_status()
            props = resp2.json()["properties"]

        temp_c = props.get("temperature", {}).get("value")
        humidity = props.get("relativeHumidity", {}).get("value")
        wind_ms = props.get("windSpeed", {}).get("value")
        wind_mph = wind_ms * 2.237 if wind_ms else None

        return Observation(
            station_id=stations[0].get("properties", {}).get("stationIdentifier", ""),
            timestamp=props.get("timestamp", ""),
            temperature_f=_c_to_f(temp_c),
            humidity=humidity,
            wind_speed_mph=wind_mph,
            description=props.get("textDescription", ""),
        )
    except Exception as exc:
        log.error("Failed to fetch observation for %s: %s", city.code, exc)
        return None
