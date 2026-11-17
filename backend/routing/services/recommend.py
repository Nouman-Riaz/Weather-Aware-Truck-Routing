"""Route scoring and recommendation.

Routes are compared criterion by criterion, in this order:

    0. Fewest No Travel miles (a No Travel segment means the trip should not be made as planned,
       so it outranks everything; the brief's "fewest Severe miles" is applied right after)
    1. Fewest Severe miles
    2. Fewest High miles
    3. Lowest average risk (distance-weighted, Low=0 .. No Travel=4)
    4. Shortest travel time (including hours-of-service stops)

Each comparison has a small tolerance so negligible differences (half a mile of High, a few
hundredths of average risk) fall through to the next criterion instead of deciding the outcome.
This is what lets travel time matter when two routes are, in practice, equally safe.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cmp_to_key

from .checkpoints import Checkpoint
from .risk import Risk


@dataclass
class RouteMetrics:
    miles_by_level: dict[Risk, float]
    unknown_miles: float
    avg_risk: float
    max_level: Risk | None
    total_s: float

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[Risk.NO_TRAVEL]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[Risk.SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[Risk.HIGH]


@dataclass(frozen=True)
class Criterion:
    label: str
    value: Callable[[RouteMetrics], float]
    tolerance: float
    unit: str


CRITERIA = (
    Criterion("No Travel miles", lambda m: m.no_travel_miles, 0.5, "mi"),
    Criterion("Severe miles", lambda m: m.severe_miles, 0.5, "mi"),
    Criterion("High miles", lambda m: m.high_miles, 0.5, "mi"),
    Criterion("average risk", lambda m: m.avg_risk, 0.05, ""),
    Criterion("travel time", lambda m: m.total_s, 60.0, "s"),
)


def metrics(checkpoints: list[Checkpoint], total_s: float) -> RouteMetrics:
    miles = {level: 0.0 for level in Risk}
    unknown = 0.0
    weighted = 0.0
    for cp in checkpoints:
        if cp.assessment is None:
            unknown += cp.coverage_mi
            continue
        miles[cp.assessment.level] += cp.coverage_mi
        weighted += cp.assessment.level * cp.coverage_mi
    known = sum(miles.values())
    levels = [cp.assessment.level for cp in checkpoints if cp.assessment]
    return RouteMetrics(
        miles_by_level=miles,
        unknown_miles=unknown,
        avg_risk=weighted / known if known else 0.0,
        max_level=max(levels) if levels else None,
        total_s=total_s,
    )


def compare(a: RouteMetrics, b: RouteMetrics) -> int:
    for criterion in CRITERIA:
        diff = criterion.value(a) - criterion.value(b)
        if abs(diff) > criterion.tolerance:
            return -1 if diff < 0 else 1
    return 0


def deciding_criterion(winner: RouteMetrics, other: RouteMetrics) -> Criterion | None:
    for criterion in CRITERIA:
        if abs(criterion.value(winner) - criterion.value(other)) > criterion.tolerance:
            return criterion
    return None


@dataclass
class Recommendation:
    best: int
    ranking: list[int]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _duration(seconds: float) -> str:
    minutes = round(abs(seconds) / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes} min"


def _fmt(criterion: Criterion, value: float) -> str:
    if criterion.unit == "s":
        return _duration(value)
    if criterion.unit == "mi":
        return f"{value:.0f} mi"
    return f"{value:.2f}"


def recommend(all_metrics: list[RouteMetrics], names: list[str]) -> Recommendation:
    ranking = sorted(range(len(all_metrics)), key=cmp_to_key(lambda i, j: compare(all_metrics[i], all_metrics[j])))
    best = ranking[0]
    winner = all_metrics[best]
    reasons = []
    for other in ranking[1:]:
        criterion = deciding_criterion(winner, all_metrics[other])
        if criterion is None:
            reasons.append(f"Equivalent to {names[other]} on risk and time.")
            continue
        ours, theirs = criterion.value(winner), criterion.value(all_metrics[other])
        if criterion.unit == "s":
            reasons.append(f"Same risk profile as {names[other]}, but {_duration(theirs - ours)} faster.")
        else:
            comparative = "Fewer" if criterion.unit == "mi" else "Lower"
            reasons.append(
                f"{comparative} {criterion.label} than {names[other]} ({_fmt(criterion, ours)} vs {_fmt(criterion, theirs)})."
            )

    fastest = min(m.total_s for m in all_metrics)
    if winner.total_s - fastest > 60:
        reasons.append(f"Adds {_duration(winner.total_s - fastest)} over the fastest route in exchange for lower risk.")

    warnings = []
    if winner.no_travel_miles > 0:
        warnings.append(
            f"Every route has No Travel conditions ({winner.no_travel_miles:.0f} mi on the best one). "
            "Consider delaying departure: use the forecast slider to find a safer window."
        )
    elif winner.severe_miles > 0:
        warnings.append(f"The recommended route still has {winner.severe_miles:.0f} mi of Severe conditions.")
    if any(m.unknown_miles > 0 for m in all_metrics):
        warnings.append("Part of the trip is beyond the 16-day forecast horizon; those miles are unrated.")
    return Recommendation(best=best, ranking=ranking, reasons=reasons, warnings=warnings)
