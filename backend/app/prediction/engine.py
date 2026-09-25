"""Heuristic prediction engine: habitat suitability x fruiting conditions x season."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.prediction.features import lagged_rain
from app.prediction.scoring import (
    clamp, piecewise, rain_kernel, season_score, trapezoid, weighted_mean,
)
from app.species.base import MODEL, ModelSettings, SpeciesConfig
from app.species.sites import FERTILITY_SOIL_PROXY, parse_site_type


@dataclass
class ForestInfo:
    """Stand data for one location. species: [(genus, share or None)], dominant first."""
    species: list[tuple[str, float | None]] = field(default_factory=list)
    species_codes: list[str] = field(default_factory=list)
    site_type: str | None = None
    stand_age: float | None = None
    address: str | None = None
    source: str = "BDL"


@dataclass
class SoilInfo:
    ph: float | None = None
    sand: float | None = None
    clay: float | None = None
    soc: float | None = None
    source: str = "SoilGrids"


@dataclass
class Context:
    forest: ForestInfo | None
    weather: dict[str, Any] | None = None
    soil: SoilInfo | None = None
    gbif_count: int | None = None
    elevation: float | None = None
    lead_days: int = 0
    resolution_m: int = 250
    weather_coarse: bool = False  # weather from the ~30 km fallback grid


def _rnd(x: float | None, n: int = 3) -> float | None:
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- habitat parts

def host_score(cfg: SpeciesConfig, forest: ForestInfo | None, m: ModelSettings = MODEL) -> float | None:
    if forest is None or not forest.species:
        return None
    shares = [s for _, s in forest.species]
    if all(s is None for s in shares):
        # only the dominant species is known
        genus = forest.species[0][0]
        known = [(genus, m.default_dominant_share)]
    else:
        known = [(g, s) for g, s in forest.species if s is not None]
    covered = min(1.0, sum(s for _, s in known))
    raw = sum(s * cfg.host_trees.get(g, 0.0) for g, s in known)
    raw += (1.0 - covered) * cfg.unknown_companion_host
    return clamp(raw / m.host_saturation)


def habitat_score(cfg: SpeciesConfig, forest: ForestInfo | None) -> float | None:
    site = parse_site_type(forest.site_type) if forest else None
    if site is None or site.fertility is None:
        return None
    fert = cfg.site_fertility.get(site.fertility, 0.3)
    moist = cfg.site_moisture.get(site.moisture, 0.7) if site.moisture else 0.7
    v = fert * moist
    if site.mountain:
        v *= cfg.mountain_factor
    return clamp(v)


def soil_score(cfg: SpeciesConfig, soil: SoilInfo | None, forest: ForestInfo | None) -> tuple[float | None, str | None]:
    """Returns (score, source) where source is 'soilgrids', 'site_proxy' or None."""
    ph = sand = None
    source = None
    if soil is not None and soil.ph is not None:
        ph, sand, source = soil.ph, soil.sand, "soilgrids"
    else:
        site = parse_site_type(forest.site_type) if forest else None
        if site and site.fertility in FERTILITY_SOIL_PROXY:
            proxy = FERTILITY_SOIL_PROXY[site.fertility]
            ph, sand, source = proxy["ph"], proxy["sand"], "site_proxy"
    if ph is None:
        return None, None
    s_ph = trapezoid(ph, *cfg.ph_pref)
    if sand is None:
        return s_ph, source
    s_sand = trapezoid(sand, *cfg.sand_pref)
    return math.sqrt(max(s_ph, 0.0) * max(s_sand, 0.0)), source


def stand_score(cfg: SpeciesConfig, forest: ForestInfo | None) -> float | None:
    if forest is None or forest.stand_age is None:
        return None
    return trapezoid(forest.stand_age, *cfg.stand_age_pref)


def terrain_score(cfg: SpeciesConfig, elevation: float | None) -> float | None:
    return None if elevation is None else trapezoid(elevation, *cfg.elevation_pref)


def prior_score(gbif_count: int | None, m: ModelSettings = MODEL) -> float | None:
    """Presence-only prior: no records is NOT evidence of absence -> stays at 0.5."""
    if gbif_count is None:
        return None
    return 0.5 + 0.5 * (1.0 - math.exp(-gbif_count / m.prior_scale_records))


# ---------------------------------------------------------------- weather parts

def weather_components(cfg: SpeciesConfig, w: dict[str, Any] | None) -> dict[str, float | None]:
    """Sub-scores 0..1 (None = unavailable). Also returns species lagged rain under '_lag'."""
    comp: dict[str, float | None] = {k: None for k in MODEL.weather_weights}
    comp["_lag"] = None
    if not w:
        return comp
    precip = w.get("precip_series")
    if precip is not None:
        kernel = rain_kernel(*cfg.rain_lag, max_lag=35)
        lag = lagged_rain(precip, w["t_index"], kernel)
        comp["_lag"] = lag
        comp["rainfall_lag"] = None if lag is None else piecewise(lag, cfg.rain_response)
    sm = w.get("soil_moisture_mean_14d")
    if sm is None:
        sm = w.get("soil_moisture_mean_7d")
    comp["soil_moisture"] = None if sm is None else piecewise(sm, cfg.soil_moisture_pref)
    t14 = w.get("temperature_mean_14d")
    t7 = w.get("temperature_mean_7d")
    if t14 is not None and t7 is not None:
        comp["temperature"] = piecewise(0.6 * t14 + 0.4 * t7, cfg.temperature_pref)
    elif t14 is not None or t7 is not None:
        comp["temperature"] = piecewise(t14 if t14 is not None else t7, cfg.temperature_pref)
    st = w.get("soil_temperature")
    comp["soil_temperature"] = None if st is None else piecewise(st, cfg.soil_temperature_pref)
    hv = [v for v in (
        None if w.get("humidity") is None else piecewise(w["humidity"], cfg.humidity_pref),
        None if w.get("vpd") is None else piecewise(w["vpd"], cfg.vpd_pref),
    ) if v is not None]
    comp["humidity_vpd"] = sum(hv) / len(hv) if hv else None
    wb = w.get("water_balance_14d")
    comp["water_balance"] = None if wb is None else piecewise(wb, cfg.water_balance_pref)
    return comp


def penalties(cfg: SpeciesConfig, w: dict[str, Any] | None, m: ModelSettings = MODEL) -> dict[str, float]:
    """Multiplicative factors in (0, 1]; also returns severities under '*_severity'."""
    out = {"drought": 1.0, "heat": 1.0, "frost": 1.0,
           "drought_severity": 0.0, "heat_severity": 0.0, "frost_severity": 0.0}
    if not w:
        return out
    # severity driven by lack of rain in the last ~30 days; long dry spell amplifies it
    r30 = w.get("rain_30d_effective")
    dd = w.get("dry_days_effective")
    rain_sev = None if r30 is None else piecewise(
        r30, [(m.drought_rain_30d[1], 1.0), (m.drought_rain_30d[0], 0.0)])
    dry_sev = None if dd is None else piecewise(
        dd, [(m.drought_dry_days[0], 0.0), (m.drought_dry_days[1], 1.0)])
    sev = None
    if rain_sev is not None:
        sev = rain_sev * (0.6 + 0.4 * (dry_sev if dry_sev is not None else 0.5))
    elif dry_sev is not None:
        sev = 0.7 * dry_sev
    if sev is not None:
        out["drought_severity"] = sev
        out["drought"] = 1.0 - cfg.drought_max_penalty * sev
    tmax = w.get("tmax_mean_7d")
    if tmax is not None:
        sev = piecewise(tmax, [(cfg.heat_tmax[0], 0.0), (cfg.heat_tmax[1], 1.0)])
        out["heat_severity"] = sev
        out["heat"] = 1.0 - cfg.heat_max_penalty * sev
    tmins = w.get("tmin_7d_values")
    if tmins:
        # recent frost matters more: weight last 3 days double
        n = len(tmins)
        score = sum((2.0 if i >= n - 3 else 1.0) for i, v in enumerate(tmins)
                    if v is not None and v <= cfg.frost_tmin)
        sev = clamp(score / 4.0)
        out["frost_severity"] = sev
        out["frost"] = 1.0 - cfg.frost_max_penalty * sev
    return out


# ---------------------------------------------------------------- main

@dataclass
class WeatherPart:
    """Everything that depends only on (species, weather point, date) - shared by many cells."""
    wcomp: dict[str, float | None]
    lag_mm: float | None
    weather: float | None
    season: float
    pen: dict[str, float]
    penalty_factor: float


def weather_part(cfg: SpeciesConfig, w: dict[str, Any] | None, target: date,
                 m: ModelSettings = MODEL) -> WeatherPart:
    wcomp = weather_components(cfg, w)
    lag_mm = wcomp.pop("_lag")
    ww = cfg.weather_weights or m.weather_weights
    weather, _ = weighted_mean((wcomp[k], ww[k]) for k in ww)
    season = season_score(target.timetuple().tm_yday, *cfg.season)
    pen = penalties(cfg, w, m)
    return WeatherPart(wcomp, lag_mm, weather, season, pen,
                       pen["drought"] * pen["heat"] * pen["frost"])


def _habitat(cfg: SpeciesConfig, ctx: Context, m: ModelSettings):
    forest = ctx.forest
    comps: dict[str, float | None] = {
        "host": host_score(cfg, forest, m),
        "habitat": habitat_score(cfg, forest),
        "soil": None,
        "stand": stand_score(cfg, forest),
        "terrain": terrain_score(cfg, ctx.elevation),
        "prior": prior_score(ctx.gbif_count, m),
    }
    comps["soil"], soil_source = soil_score(cfg, ctx.soil, forest)
    hw = cfg.habitat_weights or m.habitat_weights
    filled = {k: (v if v is not None else m.unknown_component[k]) for k, v in comps.items()}
    habitat_raw = sum(hw[k] * filled[k] for k in hw) / sum(hw.values())
    limiting = min(filled["host"], filled["habitat"])
    gate = m.gate_floor + (1 - m.gate_floor) * clamp(limiting / m.gate_threshold)
    return comps, soil_source, habitat_raw * gate


def _combine(habitat_total: float, prior: float | None, wp: WeatherPart, m: ModelSettings) -> int:
    weather_val = wp.weather if wp.weather is not None else m.weather_unknown
    hist_adj = 1.0 if prior is None else 1.0 + m.historical_adjustment_max * (prior - 0.5) * 2
    base = habitat_total * (m.weather_floor + (1 - m.weather_floor) * weather_val) * wp.season
    return int(round(clamp(base * wp.penalty_factor * hist_adj * 100, 0, 100)))


def score_only(cfg: SpeciesConfig, ctx: Context, wp: WeatherPart, m: ModelSettings = MODEL) -> tuple[int, int]:
    """Fast path for map cells: (score, confidence) without explanations."""
    comps, soil_source, habitat_total = _habitat(cfg, ctx, m)
    confidence, _ = _confidence(ctx, comps, wp.wcomp, soil_source, m)
    return _combine(habitat_total, comps["prior"], wp, m), confidence


def predict(cfg: SpeciesConfig, ctx: Context, target: date, m: ModelSettings = MODEL,
            wp: WeatherPart | None = None) -> dict[str, Any]:
    if wp is None:
        wp = weather_part(cfg, ctx.weather, target, m)
    comps, soil_source, habitat_total = _habitat(cfg, ctx, m)
    wcomp, lag_mm, weather, season, pen, penalty_factor = (
        wp.wcomp, wp.lag_mm, wp.weather, wp.season, wp.pen, wp.penalty_factor)
    score = _combine(habitat_total, comps["prior"], wp, m)

    confidence, missing = _confidence(ctx, comps, wcomp, soil_source, m)
    positive, negative = _reasons(comps, wcomp, season, pen, ctx, m)

    w = ctx.weather or {}
    return {
        "species": cfg.id,
        "date": target.isoformat(),
        "score": score,
        "confidence": confidence,
        "components": {
            "host": _rnd(comps["host"]), "habitat": _rnd(comps["habitat"]),
            "soil": _rnd(comps["soil"]), "stand": _rnd(comps["stand"]),
            "terrain": _rnd(comps["terrain"]), "prior": _rnd(comps["prior"]),
            "habitat_score": _rnd(habitat_total), "weather": _rnd(weather),
            "season": _rnd(season), "penalties": _rnd(penalty_factor),
            "weather_parts": {k: _rnd(v) for k, v in wcomp.items()},
        },
        "positive_factors": positive,
        "negative_factors": negative,
        "missing_data": missing,
        "features": {
            "rain_3d": _rnd(w.get("rain_3d"), 1), "rain_7d": _rnd(w.get("rain_7d"), 1),
            "rain_14d": _rnd(w.get("rain_14d"), 1), "rain_30d": _rnd(w.get("rain_30d"), 1),
            "rain_days_14d": w.get("rain_days_14d"),
            "days_since_rain_10mm": w.get("days_since_rain_10mm"),
            "rain_lag_mm_day": _rnd(lag_mm, 2),
            "temperature_mean_7d": _rnd(w.get("temperature_mean_7d"), 1),
            "temperature_mean_14d": _rnd(w.get("temperature_mean_14d"), 1),
            "soil_moisture_mean_7d": _rnd(w.get("soil_moisture_mean_7d"), 3),
            "soil_temperature": _rnd(w.get("soil_temperature"), 1),
            "humidity": _rnd(w.get("humidity"), 0), "vpd": _rnd(w.get("vpd"), 2),
            "water_balance_14d": _rnd(w.get("water_balance_14d"), 1),
            "soil_source": soil_source,
            "gbif_records_nearby": ctx.gbif_count,
            "elevation": _rnd(ctx.elevation, 0),
        },
    }


def _confidence(ctx: Context, comps, wcomp, soil_source, m: ModelSettings) -> tuple[int, list[str]]:
    cw = m.confidence_weights
    got = 0.0
    missing: list[str] = []
    forest = ctx.forest
    if comps["host"] is not None:
        got += cw["tree_species"]
        if forest and any(s is not None for _, s in forest.species):
            got += cw["species_share"]
    else:
        missing.append("TREE_SPECIES_MISSING")
    if comps["habitat"] is not None:
        got += cw["site_type"]
    else:
        missing.append("SITE_TYPE_MISSING")
    if comps["stand"] is not None:
        got += cw["stand_age"]
    else:
        missing.append("STAND_AGE_MISSING")
    if wcomp["rainfall_lag"] is not None and wcomp["temperature"] is not None:
        got += cw["weather_core"]
    else:
        missing.append("WEATHER_MISSING")
    if wcomp["soil_moisture"] is not None:
        got += cw["soil_moisture"]
    elif "WEATHER_MISSING" not in missing:
        missing.append("SOIL_MOISTURE_MISSING")
    if wcomp["humidity_vpd"] is not None:
        got += cw["humidity"]
    if soil_source == "soilgrids":
        got += cw["soil"]
    elif soil_source == "site_proxy":
        got += cw["soil"] * 0.5
        missing.append("SOILGRIDS_MISSING")
    else:
        missing.append("SOIL_MISSING")
    if comps["prior"] is not None:
        got += cw["gbif"]
    else:
        missing.append("GBIF_MISSING")
    if comps["terrain"] is not None:
        got += cw["elevation"]
    total = sum(cw.values())
    conf = 100.0 * got / total
    conf -= m.confidence_lead_day_penalty * max(0, ctx.lead_days)
    conf -= m.confidence_resolution_penalty.get(ctx.resolution_m, 10)
    if ctx.weather_coarse and ctx.weather:
        conf -= m.confidence_coarse_weather_penalty
    return int(round(clamp(conf, 5, 100))), missing


def _reasons(comps, wcomp, season, pen, ctx: Context, m: ModelSettings) -> tuple[list[str], list[str]]:
    good, bad = m.good, m.bad
    pos: list[str] = []
    neg: list[str] = []

    def check(value, pos_code, neg_code, hi=good, lo=bad):
        if value is None:
            return
        if pos_code and value >= hi:
            pos.append(pos_code)
        elif neg_code and value <= lo:
            neg.append(neg_code)

    h = comps["host"]
    if h is not None:
        if h >= good:
            pos.append("HOST_TREE_STRONG")
        elif h <= 0.25:
            neg.append("HOST_MISSING")
        elif h <= 0.5:
            neg.append("HOST_WEAK")
    check(comps["habitat"], "HABITAT_GOOD", "HABITAT_POOR")
    check(comps["soil"], "SOIL_GOOD", "SOIL_UNFAVORABLE")
    check(comps["stand"], "STAND_AGE_GOOD", "STAND_AGE_UNFAVORABLE")
    if ctx.gbif_count:
        pos.append("HISTORICAL_RECORDS_NEARBY")
    check(wcomp["rainfall_lag"], "RAIN_LAG_FAVORABLE", "RAIN_LAG_LOW")
    check(wcomp["soil_moisture"], "SOIL_MOISTURE_GOOD", "SOIL_DRY")
    check(wcomp["temperature"], "TEMPERATURE_GOOD", "TEMPERATURE_UNFAVORABLE")
    check(wcomp["soil_temperature"], "SOIL_TEMPERATURE_GOOD", "SOIL_TEMPERATURE_UNFAVORABLE")
    w = ctx.weather or {}
    if w.get("vpd") is not None and wcomp["humidity_vpd"] is not None:
        if wcomp["humidity_vpd"] >= good:
            pos.append("HUMIDITY_GOOD")
        elif wcomp["humidity_vpd"] <= 0.45:
            neg.append("VPD_HIGH")
    if pen["drought_severity"] >= 0.4:
        neg.append("RECENT_DROUGHT")
    if pen["heat_severity"] >= 0.3:
        neg.append("HEAT")
    if pen["frost_severity"] >= 0.25:
        neg.append("FROST")
    if season >= 0.8:
        pos.append("IN_SEASON")
    elif season <= 0.2:
        neg.append("OUTSIDE_SEASON")
    else:
        neg.append("SEASON_EDGE")
    return pos, neg
