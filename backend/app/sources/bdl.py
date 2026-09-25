"""Bank Danych o Lasach (BDL) - forest subdivisions (wydzielenia) via ArcGIS REST query.

One request per group of points (esriGeometryMultipoint) returns the subdivisions that
contain any of the points; points are then matched locally with Shapely.
Attribute names are resolved defensively; anything not found stays UNKNOWN (None).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from shapely import STRtree
from shapely.geometry import Point, Polygon

from app import config
from app.prediction.engine import ForestInfo
from app.sources.http import SourceError, get_client
from app.species.trees import genus_for_code, parse_composition

log = logging.getLogger(__name__)

SPECIES_FIELDS = ("species_cd_d", "species_cd", "spec_cd", "gat_pan", "gatunek", "species")
COMPOSITION_FIELDS = ("species_comp", "sklad", "sklad_gat", "composition", "spec_comp")
AGE_FIELDS = ("species_age", "spec_age", "age", "wiek", "stand_age")
SITE_FIELDS = ("site_type_cd", "site_type", "siedlisko", "tsl", "typ_siedl")
SHARE_FIELDS = ("species_share", "udzial", "part_cd")
ADDRESS_FIELDS = ("adress_forest", "adres_forest", "address_forest", "adr_for", "adres_les")
STRUCTURE_FIELDS = ("stand_stru", "stand_struct")

MAX_SPLIT_DEPTH = 4


def _pick(attrs: dict[str, Any], names: tuple[str, ...]) -> Any:
    for n in names:
        v = attrs.get(n)
        if v is not None and str(v).strip() not in ("", "-", "null", "None"):
            return v
    return None


def parse_attributes(raw: dict[str, Any]) -> ForestInfo:
    attrs = {str(k).lower(): v for k, v in raw.items()}
    info = ForestInfo()
    comp = parse_composition(_pick(attrs, COMPOSITION_FIELDS))
    dom_code = _pick(attrs, SPECIES_FIELDS)
    if comp:
        info.species = [(g, s) for g, s in sorted(comp, key=lambda x: -x[1])]
    elif dom_code:
        genus = genus_for_code(str(dom_code))
        if genus:
            share = None
            share_raw = _pick(attrs, SHARE_FIELDS)
            try:
                n = float(str(share_raw).replace(",", "."))
                if 1 <= n <= 10:
                    share = n / 10.0
                elif 10 < n <= 100:
                    share = n / 100.0
            except (TypeError, ValueError):
                share = None
            info.species = [(genus, share)]
    if dom_code:
        info.species_codes = [str(dom_code).strip()]
    age = _pick(attrs, AGE_FIELDS)
    try:
        age_f = float(age) if age is not None else None
        info.stand_age = age_f if age_f is not None and 0 < age_f < 400 else None
    except (TypeError, ValueError):
        info.stand_age = None
    site = _pick(attrs, SITE_FIELDS)
    info.site_type = str(site).strip() if site is not None else None
    addr = _pick(attrs, ADDRESS_FIELDS)
    info.address = str(addr).strip() if addr is not None else None
    return info


def _rings_to_polys(geometry: dict[str, Any] | None) -> list[Polygon]:
    out = []
    for ring in (geometry or {}).get("rings") or []:
        if len(ring) >= 4:
            try:
                p = Polygon(ring)
                if not p.is_empty:
                    out.append(p)
            except (ValueError, TypeError):
                continue
    return out


def match_points(points: list[tuple[float, float]], features: list[dict[str, Any]]) -> list[ForestInfo | None]:
    """points are (lat, lon). Even-odd rule over rings handles holes and multipart polygons."""
    polys: list[Polygon] = []
    owner: list[int] = []
    infos: list[ForestInfo] = []
    for fi, feat in enumerate(features):
        infos.append(parse_attributes(feat.get("attributes") or {}))
        for poly in _rings_to_polys(feat.get("geometry")):
            polys.append(poly)
            owner.append(fi)
    result: list[ForestInfo | None] = [None] * len(points)
    if not polys:
        return result
    tree = STRtree(polys)
    for i, (lat, lon) in enumerate(points):
        pt = Point(lon, lat)
        hits: dict[int, int] = {}
        for idx in tree.query(pt):
            if polys[idx].covers(pt):
                hits[owner[idx]] = hits.get(owner[idx], 0) + 1
        for fi, n in hits.items():
            if n % 2 == 1:
                result[i] = infos[fi]
                break
    return result


async def _query(points: list[tuple[float, float]], simplify_deg: float) -> tuple[list[dict], bool]:
    geometry = {"points": [[round(lon, 6), round(lat, 6)] for lat, lon in points],
                "spatialReference": {"wkid": 4326}}
    data = {
        "f": "json",
        "geometry": json.dumps(geometry, separators=(",", ":")),
        "geometryType": "esriGeometryMultipoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "6",
        "maxAllowableOffset": f"{simplify_deg:.6f}",
    }
    try:
        r = await get_client().post(f"{config.BDL_LAYER_URL}/query", data=data)
    except httpx.HTTPError as e:
        raise SourceError("bdl", f"connection error: {e}") from e
    if r.status_code != 200:
        raise SourceError("bdl", f"HTTP {r.status_code}")
    try:
        body = r.json()
    except ValueError as e:
        raise SourceError("bdl", "non-JSON response") from e
    if "error" in body:
        raise SourceError("bdl", f"service error: {body['error']}")
    return body.get("features") or [], bool(body.get("exceededTransferLimit"))


async def query_points(points: list[tuple[float, float]], simplify_deg: float = 0.00005,
                       _depth: int = 0) -> list[ForestInfo | None]:
    """ForestInfo (or None = no State Forests subdivision at the point) for each (lat, lon)."""
    if not points:
        return []
    features, exceeded = await _query(points, simplify_deg)
    if exceeded and len(points) > 1 and _depth < MAX_SPLIT_DEPTH:
        mid = len(points) // 2
        return (await query_points(points[:mid], simplify_deg, _depth + 1)
                + await query_points(points[mid:], simplify_deg, _depth + 1))
    if exceeded:
        log.warning("BDL transfer limit exceeded for %d points", len(points))
    return match_points(points, features)
