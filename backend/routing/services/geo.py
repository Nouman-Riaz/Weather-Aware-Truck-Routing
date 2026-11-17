"""Small spherical-geometry helpers. Coordinates are (lon, lat) tuples, matching GeoJSON."""

from __future__ import annotations

import math
from bisect import bisect_right
from typing import Sequence

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344

Coord = tuple[float, float]


def haversine_m(a: Coord, b: Coord) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_deg(a: Coord, b: Coord) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination(origin: Coord, bearing: float, distance_m: float) -> Coord:
    """Point reached by travelling `distance_m` from `origin` on initial `bearing` (degrees)."""
    lon1, lat1 = map(math.radians, origin)
    brg = math.radians(bearing)
    d = distance_m / EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return (math.degrees(lon2 + 3 * math.pi) % 360 - 180, math.degrees(lat2))


def cumulative(values: Sequence[float]) -> list[float]:
    """Prefix sums starting at 0, so len(result) == len(values) + 1."""
    out = [0.0]
    for v in values:
        out.append(out[-1] + v)
    return out


def interpolate(xs: Sequence[float], x: float) -> tuple[int, float]:
    """Locate x in the ascending breakpoints xs: returns (segment index i, fraction t in [0, 1])
    such that x lies between xs[i] and xs[i + 1]."""
    if x <= xs[0]:
        return 0, 0.0
    if x >= xs[-1]:
        return len(xs) - 2, 1.0
    i = bisect_right(xs, x) - 1
    span = xs[i + 1] - xs[i]
    return i, (x - xs[i]) / span if span > 0 else 0.0


def lerp_coord(a: Coord, b: Coord, t: float) -> Coord:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def simplify(coords: Sequence[Coord], tolerance_deg: float) -> list[Coord]:
    """Ramer-Douglas-Peucker line simplification (iterative, planar in degrees)."""
    n = len(coords)
    if n < 3:
        return list(coords)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg**2
    while stack:
        start, end = stack.pop()
        (x1, y1), (x2, y2) = coords[start], coords[end]
        dx, dy = x2 - x1, y2 - y1
        seg_len2 = dx * dx + dy * dy
        max_d2, index = 0.0, -1
        for i in range(start + 1, end):
            px, py = coords[i]
            if seg_len2 == 0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len2))
                d2 = (px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2
            if d2 > max_d2:
                max_d2, index = d2, i
        if max_d2 > tol2 and index != -1:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [c for c, k in zip(coords, keep) if k]
