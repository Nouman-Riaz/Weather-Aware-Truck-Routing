"""Checkpoints along a route at a fixed mileage interval, each with the truck's ETA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from . import geo, hos
from .geo import Coord
from .risk import Assessment
from .routing import Route
from .weather import Hourly


@dataclass
class Checkpoint:
    mile: float
    coord: Coord
    drive_s: float
    eta: datetime
    # Miles of route this checkpoint's weather stands for: half the gap to each neighbour,
    # so coverage over all checkpoints sums to the route length.
    coverage_mi: float
    weather: Hourly | None = None
    assessment: Assessment | None = None


class RouteTimeline:
    """Maps distance and wall-clock time along a route, accounting for hours-of-service stops."""

    def __init__(self, route: Route, departure: datetime, hos_enabled: bool):
        self.route = route
        self.departure = departure
        self.hos_enabled = hos_enabled
        self.cum_distance = route.cum_distance_m
        self.cum_drive = geo.cumulative(route.seg_drive_s)

    @property
    def total_elapsed_s(self) -> float:
        return hos.elapsed_seconds(self.cum_drive[-1], self.hos_enabled)

    def at_distance(self, distance_m: float) -> tuple[Coord, float]:
        """(position, driving seconds) at `distance_m` from the start."""
        i, t = geo.interpolate(self.cum_distance, distance_m)
        coord = geo.lerp_coord(self.route.coords[i], self.route.coords[i + 1], t)
        return coord, self.cum_drive[i] + (self.cum_drive[i + 1] - self.cum_drive[i]) * t

    def at_drive_time(self, drive_s: float) -> Coord:
        i, t = geo.interpolate(self.cum_drive, drive_s)
        return geo.lerp_coord(self.route.coords[i], self.route.coords[i + 1], t)

    def at_elapsed(self, elapsed_s: float) -> Coord:
        return self.at_drive_time(hos.drive_seconds_at(elapsed_s, self.hos_enabled))

    def eta(self, drive_s: float) -> datetime:
        return self.departure + timedelta(seconds=hos.elapsed_seconds(drive_s, self.hos_enabled))

    def checkpoints(self, interval_mi: float) -> list[Checkpoint]:
        total_mi = self.cum_distance[-1] / geo.METERS_PER_MILE
        miles = [k * interval_mi for k in range(int(total_mi // interval_mi) + 1)]
        # Always include the destination; drop a regular mark that sits almost on top of it.
        if miles and total_mi - miles[-1] < interval_mi * 0.25 and len(miles) > 1:
            miles.pop()
        miles.append(total_mi)

        result = []
        for k, mile in enumerate(miles):
            lower = (mile + miles[k - 1]) / 2 if k > 0 else 0.0
            upper = (mile + miles[k + 1]) / 2 if k < len(miles) - 1 else total_mi
            coord, drive_s = self.at_distance(mile * geo.METERS_PER_MILE)
            result.append(
                Checkpoint(mile=mile, coord=coord, drive_s=drive_s, eta=self.eta(drive_s), coverage_mi=upper - lower)
            )
        return result

    def stops(self) -> list[dict]:
        """Hours-of-service breaks and rests with their location and time."""
        result = []
        for stop in hos.stops(self.cum_drive[-1], self.hos_enabled):
            start = self.departure + timedelta(seconds=stop["start_s"])
            result.append(
                {
                    "kind": stop["kind"],
                    "coord": self.at_drive_time(stop["drive_s"]),
                    "start": start,
                    "end": start + timedelta(seconds=stop["duration_s"]),
                }
            )
        return result
