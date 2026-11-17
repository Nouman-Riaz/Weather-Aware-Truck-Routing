import pytest

from routing.services.risk import Risk, assess, classify_rain, classify_snow, classify_wind, hazard_index


@pytest.mark.parametrize(
    "mph, expected",
    [
        (0, Risk.LOW),
        (24.9, Risk.LOW),
        (25, Risk.MODERATE),
        (34.9, Risk.MODERATE),
        (35, Risk.HIGH),
        (44.9, Risk.HIGH),
        (45, Risk.SEVERE),
        (54.9, Risk.SEVERE),
        (55, Risk.NO_TRAVEL),
        (80, Risk.NO_TRAVEL),
    ],
)
def test_wind_thresholds(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rate, expected",
    [
        (0.09, Risk.LOW),
        (0.10, Risk.MODERATE),
        (0.25, Risk.HIGH),
        (0.50, Risk.SEVERE),
        (1.00, Risk.SEVERE),  # "Severe 0.50-1.00", No Travel is strictly "> 1.00"
        (1.01, Risk.NO_TRAVEL),
    ],
)
def test_rain_thresholds(rate, expected):
    assert classify_rain(rate) == expected


@pytest.mark.parametrize(
    "rate, expected",
    [
        (0.49, Risk.LOW),
        (0.5, Risk.MODERATE),
        (1.0, Risk.HIGH),
        (2.0, Risk.SEVERE),
        (3.0, Risk.SEVERE),
        (3.1, Risk.NO_TRAVEL),
    ],
)
def test_snow_thresholds(rate, expected):
    assert classify_snow(rate) == expected


@pytest.mark.parametrize(
    "mph, load, expected",
    [
        (55, 0, Risk.NO_TRAVEL),  # >= 55 mph: No Travel for any load
        (50, 30_000, Risk.SEVERE),  # 45-54 mph needs > 30,000 lb to escalate
        (50, 30_001, Risk.NO_TRAVEL),
        (40, 40_000, Risk.HIGH),  # 35-44 mph needs > 40,000 lb to escalate
        (40, 40_001, Risk.SEVERE),
        (30, 80_000, Risk.MODERATE),  # load rules do not apply below 35 mph
    ],
)
def test_load_rules(mph, load, expected):
    assert assess(mph, 0, 0, load).level == expected


def test_overall_level_is_worst_factor():
    result = assess(wind_mph=10, rain_in_hr=0.3, snow_in_hr=2.5, load_lb=10_000)
    assert (result.wind, result.rain, result.snow) == (Risk.LOW, Risk.HIGH, Risk.SEVERE)
    assert result.level == Risk.SEVERE
    assert len(result.reasons) == 2


def test_load_escalation_is_explained():
    result = assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=45_000)
    assert "High → Severe" in result.reasons[0]


@pytest.mark.parametrize("mph, rain, snow, load", [(0, 0, 0, 0), (30, 0, 0, 0), (40, 0.3, 0, 45_000), (60, 0, 0, 0)])
def test_hazard_index_stays_within_discrete_band(mph, rain, snow, load):
    level = assess(mph, rain, snow, load).level
    assert level <= hazard_index(mph, rain, snow, load) < level + 1 or level == Risk.NO_TRAVEL
