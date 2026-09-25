"""Fallback weather: coarse national grid prepared by GitHub Actions (see scripts/build_weather_grid.py)."""
from __future__ import annotations

import gzip
import json
import logging
import math
import time
from datetime import datetime, timezone

import httpx

from app import config
from app.prediction.features import WeatherSeries
from app.sources.http import get_client

log = logging.getLogger(__name__)

RELOAD_S = 3600
MAX_AGE_H = 36

_state: dict = {"loaded_at": 0.0, "doc": None, "index": {}}


def load_doc(doc: dict) -> None:
    index: dict[tuple[int, int], WeatherSeries] = {}
    dlat, dlon = doc["step"]
    for p in doc["points"]:
        s = WeatherSeries(dates=list(doc["dates"]), daily=p["d"], elevation=p.get("elev"),
                          lat=p["lat"], lon=p["lon"])
        index[(round(p["lat"] / dlat), round(p["lon"] / dlon))] = s
    _state.update(doc=doc, index=index, loaded_at=time.monotonic())


async def _ensure_loaded() -> None:
    if _state["doc"] is not None and time.monotonic() - _state["loaded_at"] < RELOAD_S:
        return
    if not config.WEATHER_GRID_URL:
        return
    try:
        r = await get_client().get(config.WEATHER_GRID_URL, timeout=30)
        r.raise_for_status()
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        load_doc(json.loads(raw))
        log.info("weather grid loaded: %s, %d points", _state["doc"]["generated"], len(_state["index"]))
    except (httpx.HTTPError, ValueError, KeyError, OSError) as e:
        log.warning("weather grid unavailable: %s", e)
        _state["loaded_at"] = time.monotonic() - RELOAD_S + 300  # retry in 5 min


def generated_at() -> str | None:
    doc = _state["doc"]
    return doc["generated"] if doc else None


def _fresh() -> bool:
    gen = generated_at()
    if gen is None:
        return False
    age = datetime.now(timezone.utc) - datetime.fromisoformat(gen)
    return age.total_seconds() < MAX_AGE_H * 3600


async def nearest(points: list[tuple[float, float]]) -> dict[tuple[float, float], WeatherSeries]:
    """Nearest grid series for each point (only if the grid is fresh)."""
    await _ensure_loaded()
    if not _state["index"] or not _fresh():
        return {}
    dlat, dlon = _state["doc"]["step"]
    out = {}
    for lat, lon in points:
        best, best_d = None, math.inf
        ci, cj = round(lat / dlat), round(lon / dlon)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                s = _state["index"].get((ci + di, cj + dj))
                if s is None:
                    continue
                d = (s.lat - lat) ** 2 + ((s.lon - lon) * 0.62) ** 2
                if d < best_d:
                    best, best_d = s, d
        if best is not None:
            out[(lat, lon)] = best
    return out


def reset() -> None:
    _state.update(loaded_at=0.0, doc=None, index={})
