"""Weather risk classification, implementing the assessment's threshold and load rules.

Threshold table (lower bound inclusive, so a value sitting on a boundary takes the higher level):

    Condition   Low       Moderate    High        Severe      No Travel
    Wind        <25 mph   25-34       35-44       45-54       >=55 mph
    Rain        <0.10     0.10-0.25   0.25-0.50   0.50-1.00   >1.00 in/hr
    Snow        <0.5      0.5-1.0     1.0-2.0     2.0-3.0     >3.0 in/hr

Rain and snow "No Travel" are strictly greater than the top bound (1.00 / 3.0), as written in
the table, while wind "No Travel" starts at 55 mph inclusive.

Load rules (applied on top of the wind level):
    wind >= 55 mph                     -> No Travel for any load
    wind 45-54 mph and load > 30,000 lb -> No Travel
    wind 35-44 mph and load > 40,000 lb -> Severe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def key(self) -> str:
        return self.name.lower()


# Lower bounds for Moderate, High and Severe.
WIND_MPH = (25.0, 35.0, 45.0)
RAIN_IN_HR = (0.10, 0.25, 0.50)
SNOW_IN_HR = (0.5, 1.0, 2.0)

WIND_NO_TRAVEL_MPH = 55.0  # inclusive
RAIN_NO_TRAVEL_IN_HR = 1.00  # exclusive
SNOW_NO_TRAVEL_IN_HR = 3.0  # exclusive

HEAVY_LOAD_LB = 30_000  # > this in 45-54 mph wind -> No Travel
VERY_HEAVY_LOAD_LB = 40_000  # > this in 35-44 mph wind -> Severe


def _classify(value: float, bounds: tuple[float, float, float]) -> Risk:
    moderate, high, severe = bounds
    if value >= severe:
        return Risk.SEVERE
    if value >= high:
        return Risk.HIGH
    if value >= moderate:
        return Risk.MODERATE
    return Risk.LOW


def classify_wind(mph: float) -> Risk:
    return Risk.NO_TRAVEL if mph >= WIND_NO_TRAVEL_MPH else _classify(mph, WIND_MPH)


def classify_rain(in_per_hr: float) -> Risk:
    return Risk.NO_TRAVEL if in_per_hr > RAIN_NO_TRAVEL_IN_HR else _classify(in_per_hr, RAIN_IN_HR)


def classify_snow(in_per_hr: float) -> Risk:
    return Risk.NO_TRAVEL if in_per_hr > SNOW_NO_TRAVEL_IN_HR else _classify(in_per_hr, SNOW_IN_HR)


def apply_load_rules(wind_risk: Risk, load_lb: float) -> Risk:
    if wind_risk == Risk.SEVERE and load_lb > HEAVY_LOAD_LB:
        return Risk.NO_TRAVEL
    if wind_risk == Risk.HIGH and load_lb > VERY_HEAVY_LOAD_LB:
        return Risk.SEVERE
    return wind_risk


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: list[str] = field(default_factory=list)


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk is the worst of the (load-adjusted) wind, rain and snow levels."""
    base_wind = classify_wind(wind_mph)
    wind = apply_load_rules(base_wind, load_lb)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)

    reasons = []
    if wind != base_wind:
        reasons.append(
            f"Wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load: {base_wind.label} → {wind.label}"
        )
    elif wind > Risk.LOW:
        reasons.append(f"Wind {wind_mph:.0f} mph: {wind.label}")
    if rain > Risk.LOW:
        reasons.append(f"Rain {rain_in_hr:.2f} in/hr: {rain.label}")
    if snow > Risk.LOW:
        reasons.append(f"Snow {snow_in_hr:.2f} in/hr: {snow.label}")

    return Assessment(level=max(wind, rain, snow), wind=wind, rain=rain, snow=snow, reasons=reasons)


def _continuous(value: float, bounds: tuple[float, ...]) -> float:
    """Piecewise-linear position of `value` on a 0..4 scale given the 4 level boundaries."""
    points = (0.0, *bounds)
    for level in range(len(points) - 1):
        lo, hi = points[level], points[level + 1]
        if value < hi:
            return level + (value - lo) / (hi - lo)
    return 4.0


def hazard_index(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> float:
    """Continuous 0-4 score used only to render a smooth heatmap. It is anchored to the same
    thresholds, so floor(hazard_index) matches the discrete level up to boundary effects of the
    load rules."""
    level = assess(wind_mph, rain_in_hr, snow_in_hr, load_lb).level
    smooth = max(
        _continuous(wind_mph, (*WIND_MPH, WIND_NO_TRAVEL_MPH)),
        _continuous(rain_in_hr, (*RAIN_IN_HR, RAIN_NO_TRAVEL_IN_HR)),
        _continuous(snow_in_hr, (*SNOW_IN_HR, SNOW_NO_TRAVEL_IN_HR)),
    )
    # Keep the continuous value inside its discrete band (load rules can raise the band).
    return round(min(max(smooth, float(level)), level + 0.99, 4.0), 2)
