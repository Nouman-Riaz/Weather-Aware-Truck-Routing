import pytest

from routing.services.hos import HOUR, drive_seconds_at, elapsed_seconds, stops


@pytest.mark.parametrize(
    "drive_h, elapsed_h",
    [
        (5, 5),
        (8, 8),  # break only needed when driving continues past 8 h
        (9, 9.5),
        (11, 11.5),  # arriving at the 11 h limit needs no rest
        (12, 22.5),  # 11 h + 0.5 h break + 10 h rest + 1 h
        (22, 33),  # 21.5 h first shift cycle + 11.5 h second shift ending at the limit
    ],
)
def test_elapsed_time_includes_required_stops(drive_h, elapsed_h):
    assert elapsed_seconds(drive_h * HOUR) == pytest.approx(elapsed_h * HOUR)


def test_disabled_hos_is_identity():
    assert elapsed_seconds(30 * HOUR, enabled=False) == 30 * HOUR


@pytest.mark.parametrize("drive_h", [0, 3, 8, 8.2, 10.9, 11, 15, 25])
def test_drive_seconds_at_inverts_elapsed(drive_h):
    assert drive_seconds_at(elapsed_seconds(drive_h * HOUR)) == pytest.approx(drive_h * HOUR)


def test_truck_is_stationary_during_rest():
    assert drive_seconds_at(12 * HOUR) == drive_seconds_at(21 * HOUR) == 11 * HOUR


def test_stops_for_long_trip():
    kinds = [(s["kind"], s["start_s"] / HOUR) for s in stops(20 * HOUR)]
    assert kinds == [("break", 8), ("rest", 11.5), ("break", 29.5)]
