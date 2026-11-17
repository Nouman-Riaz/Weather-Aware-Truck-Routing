from datetime import datetime, timedelta, timezone

import pytest

from routing.services.checkpoints import RouteTimeline
from routing.services.hos import HOUR

from .factories import straight_route

DEPARTURE = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_are_evenly_spaced_and_cover_the_route(interval):
    timeline = RouteTimeline(straight_route(120), DEPARTURE, hos_enabled=False)
    cps = timeline.checkpoints(interval)
    assert cps[0].mile == 0
    assert cps[-1].mile == pytest.approx(120, abs=0.01)
    assert all(b.mile - a.mile <= interval + 1e-6 for a, b in zip(cps, cps[1:]))
    assert sum(cp.coverage_mi for cp in cps) == pytest.approx(120, abs=0.01)


def test_eta_follows_driving_speed():
    timeline = RouteTimeline(straight_route(120, mph=60), DEPARTURE, hos_enabled=False)
    cp = timeline.checkpoints(50)[1]
    assert cp.mile == 50
    assert cp.eta - DEPARTURE == pytest.approx(timedelta(minutes=50), abs=timedelta(seconds=30))


def test_eta_includes_hos_rest():
    timeline = RouteTimeline(straight_route(720, mph=60), DEPARTURE, hos_enabled=True)
    # Mile 700 is reached after 11h40m of driving: +30 min break, +10 h rest.
    cp = next(c for c in timeline.checkpoints(50) if c.mile == 700)
    expected = timedelta(hours=11, minutes=40) + timedelta(hours=10.5)
    assert cp.eta - DEPARTURE == pytest.approx(expected, abs=timedelta(minutes=1))
    assert [s["kind"] for s in timeline.stops()] == ["break", "rest"]


def test_last_regular_mark_merges_into_destination():
    cps = RouteTimeline(straight_route(52), DEPARTURE, hos_enabled=False).checkpoints(25)
    assert [round(cp.mile) for cp in cps] == [0, 25, 52]


def test_position_during_rest_does_not_move():
    timeline = RouteTimeline(straight_route(900, mph=60), DEPARTURE, hos_enabled=True)
    assert timeline.at_elapsed(12 * HOUR) == timeline.at_elapsed(20 * HOUR)
