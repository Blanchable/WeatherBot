"""NWS Points API — resolve lat/lon to grid office + forecast URLs."""

from __future__ import annotations

import httpx
from dataclasses import dataclass

from src.bot.logging import get_logger

log = get_logger(__name__)

NWS_BASE = "https://api.weather.gov"
NWS_HEADERS = {
    "User-Agent": "(kalshi-weather-bot, contact@example.com)",
    "Accept": "application/geo+json",
}


@dataclass
class NWSGridPoint:
    office: str
    grid_x: int
    grid_y: int
    forecast_url: str
    forecast_hourly_url: str
    observation_stations_url: str


async def resolve_point(lat: float, lon: float) -> NWSGridPoint:
    url = f"{NWS_BASE}/points/{lat:.4f},{lon:.4f}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=NWS_HEADERS)
        resp.raise_for_status()
        props = resp.json()["properties"]

    return NWSGridPoint(
        office=props["gridId"],
        grid_x=props["gridX"],
        grid_y=props["gridY"],
        forecast_url=props["forecast"],
        forecast_hourly_url=props["forecastHourly"],
        observation_stations_url=props["observationStations"],
    )
