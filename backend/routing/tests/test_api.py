from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from routing.services import planner
from routing.services.weather import Hourly

from .factories import straight_route

CALM = Hourly(wind_mph=5, gust_mph=8, rain_in_hr=0, snow_in_hr=0, temp_f=50, code=0)
WINDY = Hourly(wind_mph=50, gust_mph=60, rain_in_hr=0, snow_in_hr=0, temp_f=50, code=0)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def payload(**overrides):
    body = {
        "origin": {"label": "A", "lat": 35.0, "lon": -100.0},
        "destination": {"label": "B", "lat": 36.7, "lon": -100.0},
        "departure": (timezone.now() + timedelta(hours=1)).isoformat(),
        "load_lb": 35_000,
        "interval_mi": 25,
    }
    body.update(overrides)
    return body


def fake_series(conditions_by_route):
    """Weather stub returning fixed conditions per route, identified by checkpoint order."""

    def get_series(points, start, end):
        result = []
        for count, wx in conditions_by_route:
            result += [{"wx": wx}] * count
        return result[: len(points)]

    return get_series


@mock.patch("routing.services.planner.weather.at", side_effect=lambda series, moment: series["wx"])
def test_plan_recommends_safer_route(_at):
    fast, slow = straight_route(120, mph=65), straight_route(120, mph=50)
    with (
        mock.patch.object(planner, "fetch_routes", return_value=[fast, slow]),
        mock.patch.object(planner.weather, "get_series", side_effect=fake_series([(6, WINDY), (6, CALM)])),
    ):
        response = APIClient().post("/api/plan", payload(), format="json")

    assert response.status_code == 200, response.json()
    data = response.json()
    route_a, route_b = data["routes"]
    # 50 mph wind with a 35,000 lb load is No Travel on route A.
    assert route_a["metrics"]["max_level"] == "no_travel"
    assert route_b["metrics"]["max_level"] == "low"
    assert data["recommendation"]["route_id"] == "B"
    assert len(route_a["checkpoints"]) == 6
    assert route_a["checkpoints"][1]["mile"] == 25


def test_plan_rejects_invalid_input():
    response = APIClient().post("/api/plan", payload(load_lb=-5, interval_mi=15), format="json")
    assert response.status_code == 400
    assert set(response.json()) == {"load_lb", "interval_mi"}


def test_plan_rejects_departure_beyond_forecast():
    late = (timezone.now() + timedelta(days=30)).isoformat()
    response = APIClient().post("/api/plan", payload(departure=late), format="json")
    assert response.status_code == 400
    assert "departure" in response.json()


def test_upstream_failure_returns_502():
    from routing.services.http import UpstreamError

    with mock.patch.object(planner, "fetch_routes", side_effect=UpstreamError("routing", "down")):
        response = APIClient().post("/api/plan", payload(), format="json")
    assert response.status_code == 502
    assert "routing" in response.json()["detail"]


def test_heatmap_returns_49_hours_per_point():
    route = [list(c) for c in straight_route(200).coords]
    with mock.patch("routing.services.heatmap.weather.get_series", side_effect=lambda pts, s, e: [{}] * len(pts)):
        response = APIClient().post(
            "/api/heatmap",
            {"routes": [route], "departure": (timezone.now()).isoformat(), "load_lb": 20_000},
            format="json",
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["hours"]) == 49
    assert 0 < len(data["points"]) <= 220
    assert all(len(row) == 49 for row in data["risk"])
