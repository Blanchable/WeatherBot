"""City registry and matching utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class City:
    city_id: str
    name: str
    state: str
    lat: float
    lon: float
    nws_station: str | None = None
    aliases: tuple[str, ...] = ()


_CITIES: tuple[City, ...] = (
    City("NYC", "New York", "NY", 40.7128, -74.0060, "KNYC", ("NEW YORK CITY", "NYC")),
    City("LA", "Los Angeles", "CA", 34.0522, -118.2437, "KCQT", ("LOS ANGELES", "LA")),
    City("CHI", "Chicago", "IL", 41.8781, -87.6298, "KORD", ("CHICAGO", "CHI")),
    City("DAL", "Dallas", "TX", 32.7767, -96.7970, "KDAL", ("DALLAS", "DAL")),
    City("MIA", "Miami", "FL", 25.7617, -80.1918, "KMIA", ("MIAMI", "MIA")),
    City("BOS", "Boston", "MA", 42.3601, -71.0589, "KBOS", ("BOSTON",)),
    City("SEA", "Seattle", "WA", 47.6062, -122.3321, "KSEA", ("SEATTLE",)),
    City("DEN", "Denver", "CO", 39.7392, -104.9903, "KDEN", ("DENVER",)),
    City("PHX", "Phoenix", "AZ", 33.4484, -112.0740, "KPHX", ("PHOENIX",)),
    City("ATL", "Atlanta", "GA", 33.7490, -84.3880, "KATL", ("ATLANTA",)),
    City("DC", "Washington", "DC", 38.9072, -77.0369, "KDCA", ("WASHINGTON", "WASHINGTON DC")),
    City("SF", "San Francisco", "CA", 37.7749, -122.4194, "KSFO", ("SAN FRANCISCO", "SFO")),
)


def city_registry() -> dict[str, City]:
    return {city.city_id: city for city in _CITIES}


def match_city_from_text(text: str, allowed_cities: set[str] | None = None) -> City | None:
    normalized = text.upper()
    for city in _CITIES:
        if allowed_cities and city.city_id not in allowed_cities:
            continue
        candidates = {city.city_id, city.name.upper(), *city.aliases}
        if any(token in normalized for token in candidates):
            return city
    return None

