"""Route alternatives from OSRM.

OSRM's native `alternatives` often returns fewer than three routes, so missing options are
filled by routing through via-points offset to either side of the straight line between origin
and destination, keeping only candidates that are meaningfully different and not excessively slow.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from django.conf import settings

from . import geo
from .geo import Coord
from .http import UpstreamError, get_json

logger = logging.getLogger(__name__)

# Car-profile durations are adjusted for a loaded truck by capping speed at 65 mph.
TRUCK_MAX_SPEED_MPS = 65 * geo.METERS_PER_MILE / 3600

MAX_SLOWDOWN = 1.6  # alternatives slower than this multiple of the fastest are discarded
MAX_OVERLAP = 0.85 # alternatives sharing more than this fraction of distance are duplicates
MAX_BACKTRACK = 0.03  # via-point routes that double back more than this are rejected
VIA_OFFSETS = (0.15, -0.15, 0.3, -0.3)  # perpendicular offset, as a fraction of trip length
OVERLAP_CELL_DEG = 0.02


@dataclass
class Route:
    coords: list[Coord]
    seg_distance_m: list[float]
    seg_drive_s: list[float]
    summary: str
    via: Coord | None = None
    _cum_distance: list[float] | None = field(default=None, repr=False)

    @property
    def distance_m(self) -> float:
        return self.cum_distance_m[-1]

    @property
    def drive_s(self) -> float:
        return sum(self.seg_drive_s)

    @property
    def cum_distance_m(self) -> list[float]:
        if self._cum_distance is None:
            self._cum_distance = geo.cumulative(self.seg_distance_m)
        return self._cum_distance

    def _samples(self) -> list[tuple[tuple[int, int], float]]:
        """(grid cell, metres) for ~1 km pieces of the route, in travel order."""
        samples = []
        for (a, b), d in zip(zip(self.coords, self.coords[1:]), self.seg_distance_m):
            steps = max(1, int(d // 1000))
            for k in range(steps):
                lon, lat = geo.lerp_coord(a, b, (k + 0.5) / steps)
                samples.append(((round(lon / OVERLAP_CELL_DEG), round(lat / OVERLAP_CELL_DEG)), d / steps))
        return samples

    def cells(self) -> dict[tuple[int, int], float]:
        """Distance (m) travelled in each coarse grid cell, used to measure overlap."""
        cells: dict[tuple[int, int], float] = {}
        for key, d in self._samples():
            cells[key] = cells.get(key, 0.0) + d
        return cells

    def backtrack_ratio(self) -> float:
        """Fraction of distance spent re-entering cells left earlier, i.e. doubling back. Via-point
        routes that snap onto a side road produce an out-and-back spur, which this detects."""
        last_seen: dict[tuple[int, int], int] = {}
        backtracked = 0.0
        samples = self._samples()
        for i, (key, d) in enumerate(samples):
            if key in last_seen and i - last_seen[key] > 3:
                backtracked += d
            last_seen[key] = i
        return backtracked / max(self.distance_m, 1.0)


def overlap(a: Route, b: Route) -> float:
    """Fraction of route `a`'s distance that runs through cells also used by route `b`."""
    cells_a, cells_b = a.cells(), b.cells()
    shared = sum(d for key, d in cells_a.items() if key in cells_b)
    return shared / max(sum(cells_a.values()), 1.0)


def _parse(osrm_route: dict, via: Coord | None) -> Route:
    coords = [tuple(c) for c in osrm_route["geometry"]["coordinates"]]
    distances: list[float] = []
    durations: list[float] = []
    for leg in osrm_route["legs"]:
        distances += leg["annotation"]["distance"]
        durations += leg["annotation"]["duration"]
    if len(distances) != len(coords) - 1:
        raise UpstreamError("routing", "geometry and annotations are misaligned")

    drive = [max(t, d / TRUCK_MAX_SPEED_MPS) for d, t in zip(distances, durations)]
    roads: list[str] = []
    for leg in osrm_route["legs"]:
        for name in (leg.get("summary") or "").split(", "):
            if name and name not in roads:
                roads.append(name)
    return Route(coords=coords, seg_distance_m=distances, seg_drive_s=drive, summary=", ".join(roads[:3]), via=via)


def _request(waypoints: list[Coord], alternatives: int = 0) -> list[dict]:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in waypoints)
    data = get_json(
        "routing",
        f"{settings.OSRM_URL}/route/v1/driving/{path}",
        params={
            "alternatives": alternatives or "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "true",  # needed for OSRM to fill in leg summaries (road names)
        },
        timeout=25,
    )
    if data.get("code") != "Ok":
        if data.get("code") in {"NoRoute", "NoSegment"}:
            return []
        raise UpstreamError("routing", data.get("message") or data.get("code", "unknown error"))
    return data["routes"]


def _via_points(origin: Coord, destination: Coord) -> list[Coord]:
    length = geo.haversine_m(origin, destination)
    midpoint = geo.lerp_coord(origin, destination, 0.5)
    perpendicular = geo.bearing_deg(origin, destination) + 90
    return [geo.destination(midpoint, perpendicular, max(length * abs(f), 15_000) * (1 if f > 0 else -1)) for f in VIA_OFFSETS]


def _is_distinct(candidate: Route, chosen: list[Route]) -> bool:
    return all(overlap(candidate, r) <= MAX_OVERLAP and overlap(r, candidate) <= MAX_OVERLAP for r in chosen)


def _via_route(waypoints: tuple[Coord, Coord, Coord]) -> Route | None:
    try:
        routes = _request(list(waypoints))
    except UpstreamError as exc:
        logger.warning("via-point route failed: %s", exc)
        return None
    return _parse(routes[0], waypoints[1]) if routes else None


def fetch_routes(origin: Coord, destination: Coord, count: int = 3) -> list[Route]:
    """Up to `count` distinct truck routes, fastest first."""
    native = [_parse(r, None) for r in _request([origin, destination], alternatives=count)]
    if not native:
        return []

    chosen: list[Route] = []
    for route in native:
        if _is_distinct(route, chosen):
            chosen.append(route)
    fastest = min(r.drive_s for r in chosen)

    if len(chosen) >= count:
        return sorted(chosen, key=lambda r: r.drive_s)[:count]

    # The public OSRM server is rate limited, so via candidates are fetched two at a time.
    with ThreadPoolExecutor(max_workers=2) as pool:
        candidates = list(pool.map(_via_route, [(origin, via, destination) for via in _via_points(origin, destination)]))

    for route in candidates:
        if len(chosen) >= count:
            break
        if route is None:
            continue
        if (
            route.drive_s <= fastest * MAX_SLOWDOWN
            and route.backtrack_ratio() <= MAX_BACKTRACK
            and _is_distinct(route, chosen)
        ):
            chosen.append(route)

    return sorted(chosen, key=lambda r: r.drive_s)[:count]
