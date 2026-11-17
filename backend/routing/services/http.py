"""Shared HTTP session for third-party APIs, with retries and a consistent error type."""

from __future__ import annotations

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class UpstreamError(Exception):
    """A third-party service (routing, geocoding, weather) failed or returned unusable data."""

    def __init__(self, service: str, message: str):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message


def _build_session() -> requests.Session:
    session = requests.Session()
    # Don't honour Retry-After: a rate-limited provider can ask for a minute-long wait, which would
    # hang the request past the server timeout. Fail fast with a clear error instead.
    retry = Retry(
        total=2,
        connect=0,  # an unreachable host fails after one connect timeout, so fallbacks kick in fast
        backoff_factor=0.5,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = settings.HTTP_USER_AGENT
    return session


_session: requests.Session | None = None


CONNECT_TIMEOUT_S = 5


def get_json(service: str, url: str, params: dict | None = None, timeout: float = 20) -> dict | list:
    global _session
    if _session is None:
        _session = _build_session()
    try:
        response = _session.get(url, params=params, timeout=(CONNECT_TIMEOUT_S, timeout))
    except requests.RequestException as exc:
        raise UpstreamError(service, f"request failed ({exc.__class__.__name__})") from exc
    if response.status_code == 429:
        raise UpstreamError(service, "rate limit reached")
    if response.status_code >= 400:
        raise UpstreamError(service, f"HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamError(service, "invalid JSON response") from exc
