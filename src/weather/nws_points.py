"""NWS points endpoint client."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx


@dataclass(slots=True)
class NWSPointMetadata:
    lat: float
    lon: float
    office: str
    grid_x: int
    grid_y: int
    forecast_url: str
    forecast_hourly_url: str
    observation_stations_url: str


class NWSPointsClient:
    BASE_URL = "https://api.weather.gov"

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

    @lru_cache(maxsize=256)
    def get_point(self, lat: float, lon: float) -> NWSPointMetadata:
        response = self.client.get(f"{self.BASE_URL}/points/{lat:.4f},{lon:.4f}")
        response.raise_for_status()
        props = response.json()["properties"]
        return NWSPointMetadata(
            lat=lat,
            lon=lon,
            office=props["gridId"],
            grid_x=int(props["gridX"]),
            grid_y=int(props["gridY"]),
            forecast_url=props["forecast"],
            forecast_hourly_url=props["forecastHourly"],
            observation_stations_url=props["observationStations"],
        )

