"""GBIF presence records for Poland -> small historical prior.

Loaded lazily in the background (a few dozen paged requests per species), kept in memory
and in /tmp. Until loaded (or when GBIF is down) the prior is UNKNOWN, never 0.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import Counter
from datetime import date

import httpx

from app import config
from app.sources.http import get_client

log = logging.getLogger(__name__)

BIN = 0.05            # degrees; neighbourhood = 3x3 bins in lat, 5 in lon (~10 km)
PAGE = 300
MAX_RECORDS = 6000
MIN_YEAR = 1980
MAX_UNCERTAINTY_M = 5000
CACHE_TTL_S = 30 * 86400

_bins: dict[str, Counter] = {}
_status: dict[str, str] = {}   # species -> loading|ready|error
_tasks: dict[str, asyncio.Task] = {}


def _bin(lat: float, lon: float) -> tuple[int, int]:
    return (int(lat // BIN), int(lon // BIN))


def filter_records(results: list[dict]) -> list[tuple[float, float]]:
    seen = set()
    out = []
    for r in results:
        lat, lon = r.get("decimalLatitude"), r.get("decimalLongitude")
        if lat is None or lon is None:
            continue
        unc = r.get("coordinateUncertaintyInMeters")
        if unc is not None and unc > MAX_UNCERTAINTY_M:
            continue
        if r.get("basisOfRecord") in ("FOSSIL_SPECIMEN", "LIVING_SPECIMEN"):
            continue
        year = r.get("year")
        if year is not None and year < MIN_YEAR:
            continue
        key = (round(lat, 3), round(lon, 3), str(r.get("eventDate", ""))[:10])
        if key in seen:
            continue
        seen.add(key)
        out.append((lat, lon))
    return out


async def _download(names: list[str]) -> list[tuple[float, float]]:
    client = get_client()
    pts: list[tuple[float, float]] = []
    raw: list[dict] = []
    for name in names:
        offset = 0
        while offset < MAX_RECORDS:
            params = {
                "scientificName": name, "country": "PL", "hasCoordinate": "true",
                "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT",
                "year": f"{MIN_YEAR},{date.today().year}", "limit": PAGE, "offset": offset,
            }
            r = await client.get(config.GBIF_URL, params=params)
            r.raise_for_status()
            body = r.json()
            raw.extend(body.get("results") or [])
            if body.get("endOfRecords", True):
                break
            offset += PAGE
            await asyncio.sleep(0.3)
    pts.extend(filter_records(raw))
    return pts


def _cache_path(species_id: str) -> str:
    return os.path.join(config.CACHE_DIR, f"gbif_{species_id}.json")


def _load_disk(species_id: str) -> list | None:
    try:
        with open(_cache_path(species_id)) as f:
            data = json.load(f)
        if time.time() - data["ts"] < CACHE_TTL_S:
            return data["points"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def _save_disk(species_id: str, points: list) -> None:
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(_cache_path(species_id), "w") as f:
            json.dump({"ts": time.time(), "points": points}, f)
    except OSError:
        pass


def set_points(species_id: str, points: list[tuple[float, float]]) -> None:
    _bins[species_id] = Counter(_bin(lat, lon) for lat, lon in points)
    _status[species_id] = "ready"


async def _load(species_id: str, names: list[str]) -> None:
    disk = _load_disk(species_id)
    if disk is not None:
        set_points(species_id, [tuple(p) for p in disk])
        return
    try:
        pts = await _download(names)
        set_points(species_id, pts)
        _save_disk(species_id, pts)
        log.info("GBIF %s: %d records", species_id, len(pts))
    except (httpx.HTTPError, ValueError) as e:
        log.warning("GBIF %s failed: %s", species_id, e)
        _status[species_id] = "error"


def ensure_loading(species: dict) -> None:
    """Start background loads (sequential, polite). Retries after errors on later calls."""
    if config.DISABLE_GBIF:
        return
    pending = [c for c in species.values() if _status.get(c.id) not in ("ready", "loading")]
    if not pending:
        return
    for c in pending:
        _status[c.id] = "loading"

    async def run():
        for c in pending:
            await _load(c.id, c.gbif_names)

    task = asyncio.get_running_loop().create_task(run())
    _tasks[pending[0].id] = task


def count_near(species_id: str, lat: float, lon: float) -> int | None:
    """Records within ~10 km, or None when the prior is not available."""
    bins = _bins.get(species_id)
    if bins is None:
        return None
    bi, bj = _bin(lat, lon)
    return sum(bins.get((bi + di, bj + dj), 0) for di in (-1, 0, 1) for dj in (-2, -1, 0, 1, 2))


def status() -> dict[str, str]:
    return dict(_status)


def reset() -> None:
    _bins.clear()
    _status.clear()
    _tasks.clear()
