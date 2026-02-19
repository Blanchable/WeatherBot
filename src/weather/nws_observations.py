"""Optional NWS observations client for calibration and sanity checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(slots=True)
class Observation:
    station_id: str
    timestamp_utc: datetime
    temperature_f: float | None
    text_description: str | None


class NWSObservationsClient:
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

    def get_latest_observation(self, station_id: str) -> Observation:
        response = self.client.get(f"{self.BASE_URL}/stations/{station_id}/observations/latest")
        response.raise_for_status()
        props = response.json().get("properties", {})
        temp_c = props.get("temperature", {}).get("value")
        temp_f = None if temp_c is None else (float(temp_c) * 9.0 / 5.0 + 32.0)
        return Observation(
            station_id=station_id,
            timestamp_utc=_parse_iso(props["timestamp"]),
            temperature_f=temp_f,
            text_description=props.get("textDescription"),
        )

