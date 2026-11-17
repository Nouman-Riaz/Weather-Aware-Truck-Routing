"""Trip planning: routes -> checkpoints with ETAs -> weather at ETA -> risk -> recommendation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.core.cache import cache

from . import geo, weather
from .checkpoints import Checkpoint, RouteTimeline
from .geocoding import Place
from .recommend import Recommendation, RouteMetrics, metrics, recommend
from .risk import Risk, assess
from .routing import Route, fetch_routes

ROUTE_IDS = "ABC"
PROGRESS_STEP_S = 600  # truck position resolution for the forecast slider
PROGRESS_HORIZON_S = 48 * 3600
ROUTE_CACHE_SECONDS = 60 * 60


class NoRouteFound(ValueError):
    pass


@dataclass
class PlannedRoute:
    id: str
    route: Route
    timeline: RouteTimeline
    checkpoints: list[Checkpoint]
    metrics: RouteMetrics | None = None


def _routes(origin: Place, destination: Place) -> list[Route]:
    key = f"routes:{origin.lon:.4f},{origin.lat:.4f}:{destination.lon:.4f},{destination.lat:.4f}"
    routes = cache.get(key)
    if routes is None:
        routes = fetch_routes((origin.lon, origin.lat), (destination.lon, destination.lat))
        cache.set(key, routes, ROUTE_CACHE_SECONDS)
    return routes


def _attach_weather(planned: list[PlannedRoute], load_lb: float) -> None:
    checkpoints = [cp for p in planned for cp in p.checkpoints]
    start = min(cp.eta for cp in checkpoints) - timedelta(hours=1)
    end = max(cp.eta for cp in checkpoints) + timedelta(hours=1)
    series = weather.get_series([cp.coord for cp in checkpoints], start, end)
    for cp, s in zip(checkpoints, series):
        cp.weather = weather.at(s, cp.eta)
        if cp.weather:
            cp.assessment = assess(cp.weather.wind_mph, cp.weather.rain_in_hr, cp.weather.snow_in_hr, load_lb)


def plan_trip(
    origin: Place,
    destination: Place,
    departure: datetime,
    load_lb: float,
    interval_mi: int,
    hos_enabled: bool = True,
) -> dict:
    routes = _routes(origin, destination)
    if not routes:
        raise NoRouteFound("No drivable route found between these locations.")

    planned = []
    for route_id, route in zip(ROUTE_IDS, routes):
        timeline = RouteTimeline(route, departure, hos_enabled)
        planned.append(PlannedRoute(route_id, route, timeline, timeline.checkpoints(interval_mi)))

    _attach_weather(planned, load_lb)
    for p in planned:
        p.metrics = metrics(p.checkpoints, p.timeline.total_elapsed_s)
    result = recommend([p.metrics for p in planned], [f"Route {p.id}" for p in planned])

    return {
        "origin": origin.as_dict(),
        "destination": destination.as_dict(),
        "departure": departure,
        "load_lb": load_lb,
        "interval_mi": interval_mi,
        "hos": hos_enabled,
        "recommendation": _serialize_recommendation(result, planned),
        "routes": [_serialize_route(p, rank=result.ranking.index(i) + 1) for i, p in enumerate(planned)],
    }


def _round_coord(coord: geo.Coord) -> list[float]:
    return [round(coord[0], 5), round(coord[1], 5)]


def _serialize_recommendation(result: Recommendation, planned: list[PlannedRoute]) -> dict:
    return {
        "route_id": planned[result.best].id,
        "ranking": [planned[i].id for i in result.ranking],
        "reasons": result.reasons,
        "warnings": result.warnings,
    }


def _serialize_checkpoint(cp: Checkpoint) -> dict:
    a = cp.assessment
    return {
        "mile": round(cp.mile, 1),
        "coord": _round_coord(cp.coord),
        "eta": cp.eta,
        "coverage_mi": round(cp.coverage_mi, 2),
        "level": a.level.key if a else None,
        "factors": {"wind": a.wind.key, "rain": a.rain.key, "snow": a.snow.key} if a else None,
        "reasons": a.reasons if a else [],
        "weather": cp.weather.as_dict() if cp.weather else None,
    }


def _serialize_route(p: PlannedRoute, rank: int) -> dict:
    m = p.metrics
    timeline = p.timeline
    horizon = min(timeline.total_elapsed_s, PROGRESS_HORIZON_S)
    progress = [_round_coord(timeline.at_elapsed(t)) for t in range(0, int(horizon) + PROGRESS_STEP_S, PROGRESS_STEP_S)]
    return {
        "id": p.id,
        "name": f"Route {p.id}",
        "summary": p.route.summary,
        "is_alternative_via": p.route.via is not None,
        "rank": rank,
        "distance_mi": round(p.route.distance_m / geo.METERS_PER_MILE, 1),
        "drive_s": round(p.route.drive_s),
        "total_s": round(m.total_s),
        "arrival": timeline.eta(timeline.cum_drive[-1]),
        "metrics": {
            "miles_by_level": {level.key: round(m.miles_by_level[level], 1) for level in Risk},
            "unknown_miles": round(m.unknown_miles, 1),
            "avg_risk": round(m.avg_risk, 3),
            "max_level": m.max_level.key if m.max_level is not None else None,
        },
        "geometry": [_round_coord(c) for c in geo.simplify(p.route.coords, 0.0005)],
        "checkpoints": [_serialize_checkpoint(cp) for cp in p.checkpoints],
        "stops": [{**s, "coord": _round_coord(s["coord"])} for s in timeline.stops()],
        "progress": {"step_s": PROGRESS_STEP_S, "coords": progress},
    }
