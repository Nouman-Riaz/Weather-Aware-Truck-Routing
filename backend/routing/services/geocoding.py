"""Place search via Photon (OpenStreetMap-based, keyless)."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from .http import get_json


class LocationNotFound(ValueError):
    pass


@dataclass(frozen=True)
class Place:
    label: str
    lon: float
    lat: float

    def as_dict(self) -> dict:
        return {"label": self.label, "lon": self.lon, "lat": self.lat}


def _label(props: dict) -> str:
    name = props.get("name") or props.get("street") or ""
    if props.get("housenumber") and props.get("street"):
        name = f"{props['housenumber']} {props['street']}"
    parts = [name, props.get("city"), props.get("state"), props.get("countrycode")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def search(query: str, limit: int = 6) -> list[Place]:
    query = query.strip()
    if not query:
        return []
    cache_key = f"geocode:{limit}:{query.lower()}"
    if (cached := cache.get(cache_key)) is not None:
        return cached

    data = get_json(
        "geocoding",
        f"{settings.PHOTON_URL}/api/",
        # Bias results toward the continental US, where the risk rules (mph, in/hr, lb) apply.
        params={"q": query, "limit": limit, "lang": "en", "lat": 39.5, "lon": -98.35, "location_bias_scale": 0.2},
        timeout=10,
    )
    places = []
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"]
        places.append(Place(label=_label(feature.get("properties", {})), lon=lon, lat=lat))
    cache.set(cache_key, places, 60 * 60 * 24)
    return places


def resolve(query: str) -> Place:
    results = search(query, limit=1)
    if not results:
        raise LocationNotFound(f"No location found for '{query}'")
    return results[0]
