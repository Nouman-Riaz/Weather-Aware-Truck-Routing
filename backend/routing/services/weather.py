"""Hourly forecasts from Open-Meteo.

Requests are batched (many locations per call) and cached per ~11 km grid cell and UTC day, so
overlapping routes, repeated plans and the heatmap share forecast data.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from .geo import Coord
from .http import UpstreamError, get_json

logger = logging.getLogger(__name__)

CELL_DEG = 0.1
BATCH_SIZE = 100
CACHE_SECONDS = 30 * 60
HOST_DOWN_SECONDS = 5 * 60
FORECAST_DAYS = 16  # Open-Meteo forecast horizon
VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m", "weather_code")


@dataclass(frozen=True)
class Hourly:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float  # liquid precipitation (rain + showers)
    snow_in_hr: float  # snowfall depth
    temp_f: float
    code: int  # WMO weather code

    def as_dict(self) -> dict:
        return {
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 2),
            "temp_f": round(self.temp_f),
            "code": self.code,
        }


# Per-point forecast: UTC hour (as epoch seconds) -> conditions.
Series = dict[int, Hourly]


def _cell(point: Coord) -> tuple[float, float]:
    lon, lat = point
    return (round(round(lon / CELL_DEG) * CELL_DEG, 2), round(round(lat / CELL_DEG) * CELL_DEG, 2))


def _cache_key(cell: tuple[float, float], day: date) -> str:
    return f"wx:{cell[0]}:{cell[1]}:{day.isoformat()}"


def forecast_window() -> tuple[datetime, datetime]:
    """The UTC range for which forecasts are available."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=2), today + timedelta(days=FORECAST_DAYS)


def _fetch_batch(cells: list[tuple[float, float]], first: date, last: date) -> dict[tuple[float, float], dict]:
    params = {
        "latitude": ",".join(str(c[1]) for c in cells),
        "longitude": ",".join(str(c[0]) for c in cells),
        "hourly": ",".join(VARIABLES),
        "start_date": first.isoformat(),
        "end_date": last.isoformat(),
        "timezone": "GMT",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    data = _get_forecast(params)
    results = data if isinstance(data, list) else [data]
    return {cell: result["hourly"] for cell, result in zip(cells, results)}


def _hosts() -> list[str]:
    if settings.OPEN_METEO_API_KEY:
        return [settings.OPEN_METEO_URL.replace("://api.", "://customer-api.")]
    hosts = [settings.OPEN_METEO_URL, settings.OPEN_METEO_FALLBACK_URL]
    # Skip a host that failed recently so every request doesn't wait on its timeout.
    healthy = [h for h in hosts if not cache.get(f"wx-down:{h}")]
    return healthy or hosts


def _get_forecast(params: dict) -> dict | list:
    """Request from the primary host, falling back to the next one if it is unreachable."""
    error: UpstreamError | None = None
    for host in _hosts():
        try:
            return get_json("weather", f"{host}/v1/forecast", params=params, timeout=30)
        except UpstreamError as exc:
            logger.warning("weather host %s failed: %s", host, exc.message)
            cache.set(f"wx-down:{host}", True, HOST_DOWN_SECONDS)
            error = exc
    raise error


def _split_days(hourly: dict) -> dict[date, list[tuple | None]]:
    """Convert Open-Meteo's column arrays into per-day lists of 24 compact tuples."""
    days: dict[date, list[tuple | None]] = {}
    for i, stamp in enumerate(hourly["time"]):
        moment = datetime.fromisoformat(stamp)
        values = [hourly[v][i] for v in VARIABLES]
        row = None
        if values[0] is not None:
            wind, gust, rain, showers, snow, temp, code = (v or 0 for v in values)
            row = (wind, gust, rain + showers, snow, temp, int(code))
        days.setdefault(moment.date(), [None] * 24)[moment.hour] = row
    return days


def get_series(points: list[Coord], start: datetime, end: datetime) -> list[Series]:
    """Hourly forecasts for each point covering [start, end] (UTC), aligned with `points`.
    Hours outside the forecast horizon are simply absent from the series."""
    window_start, window_end = forecast_window()
    first = max(start, window_start).date()
    last = min(end, window_end - timedelta(hours=1)).date()
    if first > last:
        return [{} for _ in points]
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]

    cells = sorted({_cell(p) for p in points})
    keys = {(cell, day): _cache_key(cell, day) for cell in cells for day in days}
    cached = cache.get_many(list(keys.values()))
    missing = sorted({cell for (cell, day), key in keys.items() if key not in cached})

    if missing:
        batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(lambda batch: _fetch_batch(batch, first, last), batches):
                to_store = {}
                for cell, hourly in result.items():
                    for day, rows in _split_days(hourly).items():
                        to_store[_cache_key(cell, day)] = rows
                cache.set_many(to_store, CACHE_SECONDS)
                cached.update(to_store)

    by_cell: dict[tuple[float, float], Series] = {}
    for cell in cells:
        series: Series = {}
        for day in days:
            rows = cached.get(keys[(cell, day)]) or []
            midnight = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
            for hour, row in enumerate(rows):
                if row is not None:
                    series[midnight + hour * 3600] = Hourly(*row)
        by_cell[cell] = series
    return [by_cell[_cell(p)] for p in points]


def at(series: Series, moment: datetime) -> Hourly | None:
    """Conditions for the hour nearest to `moment`."""
    epoch = int(moment.timestamp())
    return series.get(round(epoch / 3600) * 3600)
