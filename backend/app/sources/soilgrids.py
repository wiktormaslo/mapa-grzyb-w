"""ISRIC SoilGrids point query - optional enrichment for single-point details only
(the public API is slow and rate limited, so it is never called for whole map views)."""
from __future__ import annotations

import logging

import httpx

from app import config
from app.cache.ttl import TTLCache
from app.prediction.engine import SoilInfo
from app.sources.http import get_client

log = logging.getLogger(__name__)
_cache = TTLCache(ttl_s=7 * 86400, max_items=2000)
PROPS = ("phh2o", "sand", "silt", "clay", "soc")


def parse(body: dict) -> SoilInfo | None:
    vals: dict[str, float] = {}
    for layer in (body.get("properties") or {}).get("layers") or []:
        name = layer.get("name")
        d_factor = (layer.get("unit_measure") or {}).get("d_factor") or 1
        for depth in layer.get("depths") or []:
            if depth.get("label") in ("0-5cm", "5-15cm"):
                mean = (depth.get("values") or {}).get("mean")
                if mean is not None and name not in vals:
                    vals[name] = mean / d_factor
    if "phh2o" not in vals:
        return None
    # sand/silt/clay: g/kg -> % after d_factor (10) gives %, soc: g/kg
    return SoilInfo(ph=vals.get("phh2o"), sand=vals.get("sand"), clay=vals.get("clay"),
                    soc=vals.get("soc"))


async def fetch_soil(lat: float, lon: float) -> SoilInfo | None:
    key = (round(lat, 2), round(lon, 2))
    cached = _cache.get(key)
    if cached is not None:
        return cached or None
    params = [("lon", f"{lon:.4f}"), ("lat", f"{lat:.4f}"), ("value", "mean"),
              ("depth", "0-5cm"), ("depth", "5-15cm")] + [("property", p) for p in PROPS]
    try:
        r = await get_client().get(config.SOILGRIDS_URL, params=params, timeout=8.0)
        if r.status_code != 200:
            return None
        info = parse(r.json())
    except (httpx.HTTPError, ValueError) as e:
        log.info("SoilGrids unavailable: %s", e)
        return None
    _cache.set(key, info or False)
    return info
