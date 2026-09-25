"""Open-Meteo forecast API: ~40 days history + 6 days forecast for many points per request."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

import httpx

from app import config
from app.cache.ttl import TTLCache
from app.prediction.features import WeatherSeries
from app.sources.http import SourceError, get_client

log = logging.getLogger(__name__)

DAILY_MAP = {
    "precipitation_sum": "precip",
    "temperature_2m_mean": "tmean",
    "temperature_2m_max": "tmax",
    "temperature_2m_min": "tmin",
    "relative_humidity_2m_mean": "rh",
    "et0_fao_evapotranspiration": "et0",
    "vapour_pressure_deficit_max": "vpd",
}
HOURLY_MAP = {
    "soil_moisture_3_to_9cm": "soil_moisture",
    "soil_temperature_6cm": "soil_temp",
}
MINIMAL_DAILY = ["precipitation_sum", "temperature_2m_max", "temperature_2m_min"]

# request variants, tried in order when the API rejects a variable (HTTP 400)
VARIANTS = [
    (list(DAILY_MAP), list(HOURLY_MAP)),
    (list(DAILY_MAP), []),
    (MINIMAL_DAILY, []),
]
CHUNK = 50

_cache = TTLCache(ttl_s=3 * 3600, max_items=5000)
_variant_idx = 0
COOLDOWN_S = 600
_blocked_until = 0.0  # after a 429 skip live requests for a while (fallback grid is used)


def _key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 4), round(lon, 4))


def _hourly_to_daily(times: list[str], values: list[float | None]) -> dict[str, float | None]:
    acc: dict[str, list[float]] = defaultdict(list)
    for t, v in zip(times, values):
        if v is not None:
            acc[t[:10]].append(v)
    return {d: sum(vs) / len(vs) for d, vs in acc.items() if len(vs) >= 12}


def parse_location(obj: dict[str, Any]) -> WeatherSeries:
    daily = obj.get("daily") or {}
    dates: list[str] = list(daily.get("time") or [])
    out: dict[str, list[float | None]] = {}
    for api_name, key in DAILY_MAP.items():
        if api_name in daily:
            out[key] = list(daily[api_name])
    if "tmean" not in out and "tmax" in out and "tmin" in out:
        out["tmean"] = [None if a is None or b is None else (a + b) / 2
                        for a, b in zip(out["tmax"], out["tmin"])]
    hourly = obj.get("hourly") or {}
    htimes = hourly.get("time") or []
    for api_name, key in HOURLY_MAP.items():
        if api_name in hourly:
            per_day = _hourly_to_daily(htimes, hourly[api_name])
            out[key] = [per_day.get(d) for d in dates]
    return WeatherSeries(dates=dates, daily=out, elevation=obj.get("elevation"),
                         lat=obj.get("latitude"), lon=obj.get("longitude"))


async def _request(points: list[tuple[float, float]]) -> list[WeatherSeries]:
    global _variant_idx, _blocked_until
    client = get_client()
    while True:
        daily, hourly = VARIANTS[_variant_idx]
        params = {
            "latitude": ",".join(f"{p[0]:.4f}" for p in points),
            "longitude": ",".join(f"{p[1]:.4f}" for p in points),
            "daily": ",".join(daily),
            "past_days": config.PAST_DAYS,
            "forecast_days": config.FORECAST_DAYS,
            "timezone": config.TIMEZONE,
        }
        if hourly:
            params["hourly"] = ",".join(hourly)
        try:
            r = await client.get(config.OPEN_METEO_URL, params=params)
        except httpx.HTTPError as e:
            raise SourceError("open-meteo", f"connection error: {e}") from e
        if r.status_code == 400 and _variant_idx < len(VARIANTS) - 1:
            log.warning("Open-Meteo rejected variant %d: %s", _variant_idx, r.text[:200])
            _variant_idx += 1
            continue
        if r.status_code == 429:
            _blocked_until = time.monotonic() + COOLDOWN_S
            raise SourceError("open-meteo", "rate limited (429)")
        if r.status_code != 200:
            raise SourceError("open-meteo", f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        items = data if isinstance(data, list) else [data]
        if len(items) != len(points):
            raise SourceError("open-meteo", "unexpected number of locations in response")
        return [parse_location(o) for o in items]


async def fetch_weather(points: list[tuple[float, float]]) -> tuple[dict[tuple[float, float], WeatherSeries], list[str]]:
    """Weather for points (already snapped to the weather grid). Returns (map, errors)."""
    result: dict[tuple[float, float], WeatherSeries] = {}
    missing: list[tuple[float, float]] = []
    for p in dict.fromkeys(_key(*p) for p in points):
        cached = _cache.get(p)
        if cached is not None:
            result[p] = cached
        else:
            missing.append(p)
    errors: list[str] = []
    if missing and time.monotonic() < _blocked_until:
        return result, ["open-meteo: rate limited (429), cooling down"]
    sem = asyncio.Semaphore(2)

    async def run(chunk):
        async with sem:
            try:
                series = await _request(chunk)
            except SourceError as e:
                errors.append(str(e))
                return
            for p, s in zip(chunk, series):
                _cache.set(p, s)
                result[p] = s

    await asyncio.gather(*(run(missing[i:i + CHUNK]) for i in range(0, len(missing), CHUNK)))
    return result, sorted(set(errors))
