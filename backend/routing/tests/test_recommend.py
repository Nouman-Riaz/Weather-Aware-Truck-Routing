from routing.services.recommend import RouteMetrics, recommend
from routing.services.risk import Risk


def metrics(no_travel=0.0, severe=0.0, high=0.0, avg=0.0, hours=10.0) -> RouteMetrics:
    miles = {level: 0.0 for level in Risk}
    miles.update({Risk.NO_TRAVEL: no_travel, Risk.SEVERE: severe, Risk.HIGH: high})
    return RouteMetrics(miles_by_level=miles, unknown_miles=0, avg_risk=avg, max_level=None, total_s=hours * 3600)


NAMES = ["Route A", "Route B", "Route C"]


def best(*routes):
    return recommend(list(routes), NAMES[: len(routes)])


def test_fewest_severe_miles_wins_over_time():
    result = best(metrics(severe=30, hours=8), metrics(severe=0, high=100, hours=12))
    assert result.best == 1
    assert "Severe miles" in result.reasons[0]


def test_high_miles_break_severe_ties():
    assert best(metrics(severe=10, high=50), metrics(severe=10, high=20)).best == 1


def test_average_risk_breaks_high_ties():
    assert best(metrics(high=20, avg=0.9), metrics(high=20, avg=0.4)).best == 1


def test_travel_time_breaks_risk_ties():
    result = best(metrics(avg=0.2, hours=11), metrics(avg=0.2, hours=9), metrics(avg=0.2, hours=10))
    assert result.ranking == [1, 2, 0]
    assert "faster" in result.reasons[0]


def test_negligible_risk_difference_falls_through_to_time():
    assert best(metrics(avg=0.21, hours=12), metrics(avg=0.24, hours=9)).best == 1


def test_no_travel_outranks_severe():
    result = best(metrics(no_travel=5, hours=8), metrics(severe=60, hours=9))
    assert result.best == 1


def test_warning_when_every_route_is_no_travel():
    result = best(metrics(no_travel=5), metrics(no_travel=10))
    assert result.best == 0
    assert "delaying departure" in result.warnings[0]
