"""Live check of external sources and of the deployed app (run manually / from the Probe workflow).

usage: python -m scripts.probe_sources [APP_URL]
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

import httpx

from app import config
from app.prediction import grid, service
from app.prediction.features import compute_weather_features
from app.sources import bdl, open_meteo, soilgrids
from app.sources.http import get_client

LAT, LON = 52.05, 21.35  # forests near Celestynów (Mazowsze)


def show(title: str, obj) -> None:
    print(f"\n===== {title} =====")
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str, indent=1)
    print(text[:4000])


async def probe_bdl():
    c = get_client()
    try:
        r = await c.get(config.BDL_LAYER_URL, params={"f": "json"})
        meta = r.json()
        show("BDL layer meta", {"status": r.status_code, "name": meta.get("name"),
                                "maxRecordCount": meta.get("maxRecordCount"),
                                "capabilities": meta.get("capabilities"),
                                "fields": [(f.get("name"), f.get("type"), f.get("alias"))
                                           for f in meta.get("fields") or []]})
    except Exception as e:  # noqa: BLE001
        show("BDL layer meta ERROR", repr(e))
    try:
        r = await c.get(f"{config.BDL_LAYER_URL}/query", params={
            "geometry": f"{LON - 0.01},{LAT - 0.01},{LON + 0.01},{LAT + 0.01}",
            "geometryType": "esriGeometryEnvelope", "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
            "returnGeometry": "false", "f": "json", "resultRecordCount": "8"})
        body = r.json()
        show("BDL sample attributes", [f.get("attributes") for f in (body.get("features") or [])[:8]]
             or body)
    except Exception as e:  # noqa: BLE001
        show("BDL sample ERROR", repr(e))
    for n in (16, 32):
        big = [(LAT - 0.04 + j * 0.08 / n, LON - 0.06 + i * 0.12 / n) for j in range(n) for i in range(n)]
        t0 = time.monotonic()
        try:
            res = await bdl.query_points(big, simplify_deg=0.0002)
            print(f"BDL timing {n * n} points: {time.monotonic() - t0:.1f}s, "
                  f"in stand: {sum(1 for x in res if x)}")
        except Exception as e:  # noqa: BLE001
            print(f"BDL timing {n * n} points ERROR after {time.monotonic() - t0:.1f}s: {e!r}")
    pts = [(LAT + dy * 0.004, LON + dx * 0.006) for dy in range(-3, 4) for dx in range(-3, 4)]
    try:
        infos = await bdl.query_points(pts)
        found = [i for i in infos if i]
        show("BDL parsed (app parser)", {"points": len(pts), "in_forest": len(found),
                                         "examples": [i.__dict__ for i in found[:5]]})
    except Exception as e:  # noqa: BLE001
        show("BDL parsed ERROR", repr(e))


async def probe_meteo():
    pts = [grid.snap_weather(LAT, LON, 1000), grid.snap_weather(53.5, 22.0, 1000)]
    data, errors = await open_meteo.fetch_weather(pts)
    out = {"errors": errors, "variant_used": open_meteo.VARIANTS[open_meteo._variant_idx]}
    for p, s in data.items():
        t = s.index_of(service.today_pl().isoformat())
        f = compute_weather_features(s, t) if t is not None else {}
        out[str(p)] = {
            "days": len(s.dates), "first": s.dates[0] if s.dates else None,
            "elevation": s.elevation, "keys": sorted(s.daily),
            "non_null": {k: sum(v is not None for v in vals) for k, vals in s.daily.items()},
            "features_today": {k: v for k, v in f.items() if not isinstance(v, list)},
        }
    show("Open-Meteo", out)


async def probe_gbif():
    c = get_client()
    r = await c.get(config.GBIF_URL, params={"scientificName": "Imleria badia", "country": "PL",
                                             "hasCoordinate": "true", "limit": 3})
    body = r.json()
    show("GBIF", {"status": r.status_code, "count": body.get("count"),
                  "sample": [{k: x.get(k) for k in ("scientificName", "decimalLatitude", "decimalLongitude",
                                                   "year", "coordinateUncertaintyInMeters")}
                             for x in body.get("results") or []]})
    for name in ("Boletus edulis", "Imleria badia", "Suillus luteus", "Lactarius deliciosus"):
        r = await c.get(config.GBIF_URL, params={"scientificName": name, "country": "PL",
                                                 "hasCoordinate": "true", "limit": 0})
        print(f"GBIF count {name}: {r.json().get('count')}")


async def probe_soil():
    s = await soilgrids.fetch_soil(LAT, LON)
    show("SoilGrids", s.__dict__ if s else "no data / unavailable")


async def probe_app(url: str):
    base = url.rstrip("/")
    async with httpx.AsyncClient(timeout=180) as c:
        async def get(path):
            t0 = time.monotonic()
            try:
                r = await c.get(base + path)
                print(f"APP {path[:60]} took {time.monotonic() - t0:.1f}s")
                return r.status_code, r.json()
            except Exception as e:  # noqa: BLE001
                show(f"APP {path[:40]} ERROR after {time.monotonic() - t0:.0f}s", repr(e))
                return None, None

        status, body = await get("/api/v1/health")
        show("APP health", {"status": status, "body": body})
        cell = None
        for west, south, east, north, zoom in ((LON - 0.02, LAT - 0.01, LON + 0.02, LAT + 0.01, 14),
                                               (LON - 0.08, LAT - 0.04, LON + 0.08, LAT + 0.04, 12)):
            status, body = await get(f"/api/v1/predictions/bbox?west={west}&south={south}&east={east}"
                                     f"&north={north}&zoom={zoom}&species=all")
            if body and "features" in body:
                if body["features"] and cell is None:
                    ring = body["features"][0]["geometry"]["coordinates"][0]
                    cell = (sum(p[1] for p in ring[:4]) / 4, sum(p[0] for p in ring[:4]) / 4)
                body = {"meta": body["meta"], "n": len(body["features"]),
                        "first": [f["properties"] for f in body["features"][:3]]}
            show("APP bbox", {"status": status, "body": body})
        if cell:
            status, body = await get(f"/api/v1/prediction?lat={cell[0]:.5f}&lon={cell[1]:.5f}&species=all")
            if body and body.get("results"):
                for r in body["results"]:
                    r.pop("components", None)
            show("APP point (forest cell)", {"status": status, "body": body})


async def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if len(sys.argv) > 1 and sys.argv[1]:
        await probe_app(sys.argv[1])  # first, while the server is fresh
    await probe_bdl()
    await probe_meteo()
    await probe_gbif()
    await probe_soil()


if __name__ == "__main__":
    asyncio.run(main())
