"""Weather grid along the trip corridor for hours 0-48 after departure.

Grid points are laid over the routes' bounding box and kept only if they are within a couple of
cells of a route. The cell size grows until the grid fits within MAX_POINTS, which keeps the
upstream weather request small and the client-side heatmap fast.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from . import geo, weather
from .geo import Coord
from .risk import hazard_index

HOURS = 48
MAX_POINTS = 220
MIN_SPACING_DEG = 0.15
CORRIDOR_CELLS = 2


def _grid(routes: list[list[Coord]], spacing: float) -> list[Coord]:
    all_coords = [c for r in routes for c in r]
    mid_lat = sum(c[1] for c in all_coords) / len(all_coords)
    lat_step = spacing
    lon_step = spacing / max(math.cos(math.radians(mid_lat)), 0.2)  # roughly square cells
    min_lon = min(c[0] for c in all_coords)
    min_lat = min(c[1] for c in all_coords)

    def cell_of(lon: float, lat: float) -> tuple[int, int]:
        return round((lon - min_lon) / lon_step), round((lat - min_lat) / lat_step)

    occupied: set[tuple[int, int]] = set()
    for route in routes:
        for a, b in zip(route, route[1:]):
            # Sample each segment finely enough not to skip cells.
            steps = max(1, int(max(abs(b[0] - a[0]) / lon_step, abs(b[1] - a[1]) / lat_step) * 2))
            for k in range(steps + 1):
                occupied.add(cell_of(*geo.lerp_coord(a, b, k / steps)))

    corridor: set[tuple[int, int]] = set()
    r = CORRIDOR_CELLS
    for ix, iy in occupied:
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    corridor.add((ix + dx, iy + dy))
    return [(min_lon + ix * lon_step, min_lat + iy * lat_step) for ix, iy in sorted(corridor)]


def corridor_grid(routes: list[list[Coord]]) -> tuple[list[Coord], float]:
    spacing = MIN_SPACING_DEG
    points = _grid(routes, spacing)
    while len(points) > MAX_POINTS:
        spacing *= 1.15
        points = _grid(routes, spacing)
    return points, spacing


LAYERS = ("risk", "wind_mph", "rain_in_hr", "snow_in_hr")


def _values(wx: weather.Hourly | None, load_lb: float) -> dict[str, float | None]:
    if wx is None:
        return dict.fromkeys(LAYERS)
    return {
        "risk": hazard_index(wx.wind_mph, wx.rain_in_hr, wx.snow_in_hr, load_lb),
        "wind_mph": round(wx.wind_mph, 1),
        "rain_in_hr": round(wx.rain_in_hr, 3),
        "snow_in_hr": round(wx.snow_in_hr, 2),
    }


def build(routes: list[list[Coord]], departure: datetime, load_lb: float) -> dict:
    points, spacing = corridor_grid(routes)
    start = departure.replace(minute=0, second=0, microsecond=0)
    if departure.minute >= 30:
        start += timedelta(hours=1)
    hours = [start + timedelta(hours=h) for h in range(HOURS + 1)]
    series = weather.get_series(points, hours[0], hours[-1])

    layers: dict[str, list[list[float | None]]] = {name: [] for name in LAYERS}
    for s in series:
        rows: dict[str, list[float | None]] = {name: [] for name in LAYERS}
        for moment in hours:
            for name, value in _values(weather.at(s, moment), load_lb).items():
                rows[name].append(value)
        for name in LAYERS:
            layers[name].append(rows[name])

    return {
        "hours": hours,
        "spacing_deg": round(spacing, 4),
        "points": [[round(lon, 4), round(lat, 4)] for lon, lat in points],
        **layers,
    }
