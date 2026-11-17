"""FMCSA hours-of-service approximation (property-carrying drivers).

A driver may drive 11 hours before a 10-hour off-duty rest, and must take a 30-minute break
after 8 cumulative hours of driving. Applying these rules turns pure driving time into
elapsed (wall-clock) time, which is what determines when the truck meets the weather.
"""

from __future__ import annotations

HOUR = 3600.0
DRIVE_LIMIT_S = 11 * HOUR
BREAK_AFTER_S = 8 * HOUR
BREAK_S = 0.5 * HOUR
REST_S = 10 * HOUR


def elapsed_seconds(drive_s: float, enabled: bool = True) -> float:
    """Wall-clock seconds needed to accumulate `drive_s` of driving, including required stops.

    Stops are only inserted once the driver needs to keep driving past a limit, so arriving
    exactly at a limit does not add a stop.
    """
    if not enabled:
        return drive_s
    full_shifts, in_shift = divmod(drive_s, DRIVE_LIMIT_S)
    if in_shift == 0 and full_shifts > 0:
        full_shifts, in_shift = full_shifts - 1, DRIVE_LIMIT_S
    elapsed = full_shifts * (DRIVE_LIMIT_S + BREAK_S + REST_S)
    elapsed += in_shift + (BREAK_S if in_shift > BREAK_AFTER_S else 0.0)
    return elapsed


def stops(total_drive_s: float, enabled: bool = True) -> list[dict]:
    """The breaks and rests taken on a trip, as {kind, drive_s, start_s, duration_s}."""
    if not enabled:
        return []
    result = []
    shift_start = 0.0
    while True:
        break_at = shift_start + BREAK_AFTER_S
        if total_drive_s <= break_at:
            break
        result.append(
            {"kind": "break", "drive_s": break_at, "start_s": elapsed_seconds(break_at), "duration_s": BREAK_S}
        )
        rest_at = shift_start + DRIVE_LIMIT_S
        if total_drive_s <= rest_at:
            break
        result.append(
            {"kind": "rest", "drive_s": rest_at, "start_s": elapsed_seconds(rest_at), "duration_s": REST_S}
        )
        shift_start = rest_at
    return result


def drive_seconds_at(elapsed_s: float, enabled: bool = True) -> float:
    """Inverse of `elapsed_seconds`: driving time accumulated after `elapsed_s` of wall-clock time."""
    if not enabled:
        return elapsed_s
    cycle = DRIVE_LIMIT_S + BREAK_S + REST_S
    full_cycles, t = divmod(elapsed_s, cycle)
    if t <= BREAK_AFTER_S:
        in_shift = t
    elif t <= BREAK_AFTER_S + BREAK_S:
        in_shift = BREAK_AFTER_S
    elif t <= DRIVE_LIMIT_S + BREAK_S:
        in_shift = t - BREAK_S
    else:
        in_shift = DRIVE_LIMIT_S
    return full_cycles * DRIVE_LIMIT_S + in_shift
