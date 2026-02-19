"""City registry and geographic mapping for weather markets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CityInfo:
    code: str
    name: str
    lat: float
    lon: float
    state: str
    aliases: tuple[str, ...] = ()


CITY_REGISTRY: dict[str, CityInfo] = {
    "NYC": CityInfo("NYC", "New York", 40.7128, -74.0060, "NY",
                     ("new york", "nyc", "manhattan", "central park")),
    "LA": CityInfo("LA", "Los Angeles", 34.0522, -118.2437, "CA",
                   ("los angeles", "la", "lax")),
    "CHI": CityInfo("CHI", "Chicago", 41.8781, -87.6298, "IL",
                    ("chicago", "chi", "ohare", "o'hare")),
    "DAL": CityInfo("DAL", "Dallas", 32.7767, -96.7970, "TX",
                    ("dallas", "dfw", "dallas-fort worth")),
    "MIA": CityInfo("MIA", "Miami", 25.7617, -80.1918, "FL",
                    ("miami", "mia", "south florida")),
    "HOU": CityInfo("HOU", "Houston", 29.7604, -95.3698, "TX",
                    ("houston", "hou")),
    "PHX": CityInfo("PHX", "Phoenix", 33.4484, -112.0740, "AZ",
                    ("phoenix", "phx")),
    "PHI": CityInfo("PHI", "Philadelphia", 39.9526, -75.1652, "PA",
                    ("philadelphia", "philly", "phi", "phl")),
    "DEN": CityInfo("DEN", "Denver", 39.7392, -104.9903, "CO",
                    ("denver", "den")),
    "ATL": CityInfo("ATL", "Atlanta", 33.7490, -84.3880, "GA",
                    ("atlanta", "atl")),
    "SF": CityInfo("SF", "San Francisco", 37.7749, -122.4194, "CA",
                   ("san francisco", "sf")),
    "SEA": CityInfo("SEA", "Seattle", 47.6062, -122.3321, "WA",
                    ("seattle", "sea")),
    "BOS": CityInfo("BOS", "Boston", 42.3601, -71.0589, "MA",
                    ("boston", "bos")),
    "DCA": CityInfo("DCA", "Washington DC", 38.9072, -77.0369, "DC",
                    ("washington", "dc", "dca", "washington dc")),
    "MSP": CityInfo("MSP", "Minneapolis", 44.9778, -93.2650, "MN",
                    ("minneapolis", "msp")),
    "STL": CityInfo("STL", "St. Louis", 38.6270, -90.1994, "MO",
                    ("st louis", "st. louis", "stl")),
    "LAS": CityInfo("LAS", "Las Vegas", 36.1699, -115.1398, "NV",
                    ("las vegas", "las", "vegas")),
    "SAN": CityInfo("SAN", "San Diego", 32.7157, -117.1611, "CA",
                    ("san diego", "san")),
    "AUS": CityInfo("AUS", "Austin", 30.2672, -97.7431, "TX",
                    ("austin", "aus")),
    "DET": CityInfo("DET", "Detroit", 42.3314, -83.0458, "MI",
                    ("detroit", "det")),
}


def find_city_in_text(text: str) -> str | None:
    text_lower = text.lower()
    for code, info in CITY_REGISTRY.items():
        for alias in info.aliases:
            if alias in text_lower:
                return code
    return None


def get_city(code: str) -> CityInfo | None:
    return CITY_REGISTRY.get(code.upper())
