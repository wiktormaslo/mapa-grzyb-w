"""Orchestration: bbox -> grid -> BDL (grouped) -> weather (grouped) -> scores -> GeoJSON."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app import config
from app.cache.ttl import TTLCache
from app.prediction import grid
from app.prediction.engine import Context, ForestInfo, predict, score_only, weather_part
from app.prediction.features import WeatherSeries, compute_weather_features
from app.sources import bdl, gbif, open_meteo, soilgrids, weather_grid
from app.sources.http import SourceError
from app.species import MODEL, SPECIES
from app.species.sites import parse_site_type
from app.species.trees import GENUS_PL

log = logging.getLogger(__name__)

_forest_cache = TTLCache(ttl_s=24 * 3600, max_items=4000)
_response_cache = TTLCache(ttl_s=30 * 60, max_items=300)
_tile_sem: asyncio.Semaphore | None = None

ALL = "all"
MAX_BROWSER_POINTS = 200


class InputError(ValueError):
    pass


def today_pl() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def resolve_date(value: str | None) -> tuple[date, int]:
    today = today_pl()
    d = today if not value else date.fromisoformat(value)
    lead = (d - today).days
    if lead < 0 or lead >= config.FORECAST_DAYS:
        raise InputError(f"date must be between {today} and {today + timedelta(days=config.FORECAST_DAYS - 1)}")
    return d, lead


def resolve_species(value: str) -> list[str]:
    if value == ALL:
        return list(SPECIES)
    if value not in SPECIES:
        raise InputError(f"unknown species '{value}'")
    return [value]


async def _forest_tile(ti: int, tj: int, res: int) -> list[tuple[grid.Cell, list[ForestInfo]]]:
    """Forest stands at the sample points of each cell of a tile (cells without forest dropped)."""
    global _tile_sem
    if _tile_sem is None:
        _tile_sem = asyncio.Semaphore(4)

    async def fetch():
        cells = grid.tile_cells(ti, tj, res)
        if not cells:
            return []
        n = grid.samples_per_side(res)
        points = [p for c in cells for p in c.subpoints(n)]
        async with _tile_sem:
            infos = await bdl.query_points(points, simplify_deg=min(0.001, cells[0].dlat / (20 * n)))
        k = n * n
        out = []
        for idx, c in enumerate(cells):
            forests = [f for f in infos[idx * k:(idx + 1) * k] if f is not None]
            if forests:
                out.append((c, forests))
        return out

    return await _forest_cache.get_or_fetch(("forest", res, ti, tj), fetch)


async def get_weather(points: list[tuple[float, float]]) -> tuple[dict, list[str], str, set]:
    """Live Open-Meteo first; points it could not serve come from the fallback grid.

    Returns (series by point, errors, source label, points served by the coarse grid)."""
    weather, errors = await open_meteo.fetch_weather(points)
    missing = [p for p in points if p not in weather]
    if not missing:
        return weather, [], "open-meteo", set()
    fallback = await weather_grid.nearest(missing)
    weather.update(fallback)
    coarse = set(fallback)
    if len(fallback) == len(missing):
        return weather, [], "open-meteo" if len(fallback) < len(points) / 2 else "grid", coarse
    return weather, errors + ["weather grid: unavailable"], "partial", coarse


def _features_for(series: WeatherSeries | None, d: date) -> dict[str, Any] | None:
    if series is None:
        return None
    t = series.index_of(d.isoformat())
    if t is None:
        return None
    return compute_weather_features(series, t, MODEL.min_effect_lag)


async def predict_bbox(west: float, south: float, east: float, north: float, zoom: float,
                       species: str, date_str: str | None) -> dict[str, Any]:
    species_ids = resolve_species(species)
    target, lead = resolve_date(date_str)
    if not (west < east and south < north):
        raise InputError("invalid bbox")
    bbox = grid.clip_to_poland((west, south, east, north))
    meta: dict[str, Any] = {"species": species, "date": target.isoformat(), "errors": []}
    if bbox is None:
        meta.update(resolution_m=None, cells=0)
        return {"type": "FeatureCollection", "features": [], "meta": meta}
    res = grid.choose_resolution(bbox, zoom)
    i0, j0, i1, j1 = grid.cell_range(bbox, res)
    rkey = (res, i0, j0, i1, j1, species, target.isoformat())
    cached = _response_cache.get(rkey)
    if cached is not None:
        return cached

    gbif.ensure_loading(SPECIES)
    t0 = time.monotonic()
    tiles = grid.tiles_for(bbox, res)
    results = await asyncio.gather(*(_forest_tile(ti, tj, res) for ti, tj in tiles),
                                   return_exceptions=True)
    errors: set[str] = set()
    cells: list[tuple[grid.Cell, list[ForestInfo]]] = []
    for r in results:
        if isinstance(r, SourceError):
            errors.add(str(r))
        elif isinstance(r, BaseException):
            log.exception("tile failed", exc_info=r)
            errors.add("bdl: unexpected error")
        else:
            cells.extend(cf for cf in r if grid.cell_in_bbox(cf[0], bbox))

    t1 = time.monotonic()
    wpoints = {c: grid.snap_weather(*c.center, res) for c, _ in cells}
    weather, werr, wsource, coarse = await get_weather(list(set(wpoints.values())))
    errors.update(werr)
    t2 = time.monotonic()
    wfeat_cache: dict[tuple[float, float], dict | None] = {}
    wpart_cache: dict = {}

    features = []
    for cell, forests in cells:
        wp = wpoints[cell]
        if wp not in wfeat_cache:
            wfeat_cache[wp] = _features_for(weather.get(wp), target)
        wf = wfeat_cache[wp]
        series = weather.get(wp)
        lat, lon = cell.center
        best = None
        scores = {}
        for sid in species_ids:
            key = (sid, wp)
            if key not in wpart_cache:
                wpart_cache[key] = weather_part(SPECIES[sid], wf, target)
            gcount = gbif.count_near(sid, lat, lon)
            elev = series.elevation if series else None
            # cell value = mean over the forest sample points inside it
            tot_s = tot_c = 0
            for forest in forests:
                ctx = Context(forest=forest, weather=wf, gbif_count=gcount, elevation=elev,
                              lead_days=lead, resolution_m=res, weather_coarse=wp in coarse)
                sc, cf = score_only(SPECIES[sid], ctx, wpart_cache[key])
                tot_s += sc
                tot_c += cf
            score = round(tot_s / len(forests))
            conf = round(tot_c / len(forests))
            scores[sid] = score
            if best is None or score > best["score"]:
                best = {"score": score, "confidence": conf, "species": sid}
        props = {"score": best["score"], "confidence": best["confidence"],
                 "species": best["species"]}
        if len(species_ids) > 1:
            # runner-up helps the UI say "also good for ..."
            second = sorted(scores.items(), key=lambda kv: -kv[1])[1]
            props["second"], props["second_score"] = second
        features.append({"type": "Feature", "properties": props,
                         "geometry": {"type": "Point",
                                      "coordinates": [round(lon, 5), round(lat, 5)]}})

    # points without weather, or (when zoomed in) served only by the coarse fallback grid:
    # the browser fetches them from Open-Meteo itself and uploads them (POST /weather)
    refine = res <= grid.REFINE_MAX_RES
    weather_missing = sorted({wp for wp in wpoints.values()
                              if wp not in weather or (refine and wp in coarse)})
    if weather_missing:
        meta["weather_missing"] = [list(p) for p in weather_missing[:MAX_BROWSER_POINTS]]
        meta["weather_request"] = {"url": config.OPEN_METEO_URL, "params": open_meteo.base_params()}
    t3 = time.monotonic()
    timings = {"forest_s": round(t1 - t0, 2), "weather_s": round(t2 - t1, 2),
               "score_s": round(t3 - t2, 2)}
    log.info("bbox res=%d tiles=%d cells=%d %s", res, len(tiles), len(features), timings)
    probe = grid.Cell(0, 0, res)
    meta.update(resolution_m=res, cells=len(features), tiles=len(tiles), timings=timings,
                cell_deg=[round(probe.dlon, 7), round(probe.dlat, 7)],
                weather_source=wsource,
                weather_points=len(set(wpoints.values())), errors=sorted(errors),
                gbif=gbif.status())
    out = {"type": "FeatureCollection", "features": features, "meta": meta}
    if not errors and not weather_missing:
        _response_cache.set(rkey, out)
    return out


def _forest_summary(forest: ForestInfo) -> dict[str, Any]:
    site = parse_site_type(forest.site_type)
    return {
        "trees": [{"genus": g, "name_pl": GENUS_PL.get(g, g),
                   "share": None if s is None else round(s, 2)} for g, s in forest.species],
        "species_codes": forest.species_codes,
        "site_type": forest.site_type,
        "site_type_label": site.label_pl() if site else None,
        "stand_age": forest.stand_age,
        "address": forest.address,
        "owner": forest.owner,
    }


async def predict_point(lat: float, lon: float, species: str, date_str: str | None) -> dict[str, Any]:
    species_ids = resolve_species(species)
    target, lead = resolve_date(date_str)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InputError("invalid coordinates")
    gbif.ensure_loading(SPECIES)
    errors: list[str] = []
    sources: list[str] = []

    forest: ForestInfo | None = None
    try:
        forest = (await bdl.query_points([(lat, lon)]))[0]
        sources.append("BDL (Bank Danych o Lasach)")
    except SourceError as e:
        errors.append(str(e))

    base = {"lat": lat, "lon": lon, "date": target.isoformat(), "species": species,
            "in_forest": forest is not None, "errors": errors}
    if forest is None:
        base["results"] = []
        base["sources"] = sources
        return base

    wp = grid.snap_weather(lat, lon, grid.LADDER[0])
    (weather, werr, wsource, coarse), soil = await asyncio.gather(get_weather([wp]),
                                                          soilgrids.fetch_soil(lat, lon))
    errors.extend(werr)
    series = weather.get(wp)
    wf = _features_for(series, target)
    if series is None or wp in coarse:
        base["weather_missing"] = [list(wp)]
        base["weather_request"] = {"url": config.OPEN_METEO_URL, "params": open_meteo.base_params()}
    if series is not None:
        sources.append("Open-Meteo" if wsource == "open-meteo"
                       else "Open-Meteo (siatka krajowa ~30 km, odświeżana co 6 h)")
    if soil is not None:
        sources.append("SoilGrids (ISRIC)")

    results = []
    for sid in species_ids:
        cnt = gbif.count_near(sid, lat, lon)
        ctx = Context(forest=forest, weather=dict(wf) if wf else None, soil=soil,
                      gbif_count=cnt, elevation=series.elevation if series else None,
                      lead_days=lead, resolution_m=250, weather_coarse=wp in coarse)
        p = predict(SPECIES[sid], ctx, target)
        p["name_pl"] = SPECIES[sid].name_pl
        p["latin"] = SPECIES[sid].latin
        results.append(p)
    results.sort(key=lambda p: -p["score"])
    if any(r["components"]["prior"] is not None for r in results):
        sources.append("GBIF")
    base.update(forest=_forest_summary(forest), results=results, sources=sources,
                best_species=results[0]["species"] if results else None)
    return base
