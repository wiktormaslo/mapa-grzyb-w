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
        other = await bdl._query_layer(config.BDL_OTHER_LAYER_URL, pts, 0.0002)
        print(f"BDL other-ownership layer: {sum(1 for x in other if x)} of {len(pts)} points; examples:",
              [x.__dict__ for x in other if x][:2])
    except Exception as e:  # noqa: BLE001
        print("BDL other-ownership ERROR", repr(e))
    try:
        infos = await bdl.query_points(pts)
        found = [i for i in infos if i]
        show("BDL parsed (app parser)", {"points": len(pts), "in_forest": len(found),
                                         "examples": [i.__dict__ for i in found[:5]]})
    except Exception as e:  # noqa: BLE001
        show("BDL parsed ERROR", repr(e))


async def probe_bdl_layers():
    """All layers of the BDL services - looking for forests of other ownership (private etc.)."""
    c = get_client()
    root = config.BDL_LAYER_URL.rsplit("/MapServer", 1)[0].rsplit("/", 1)[0]
    try:
        r = await c.get(root, params={"f": "json"})
        services = [sv["name"] for sv in r.json().get("services", [])]
        print("BDL services:", services)
    except Exception as e:  # noqa: BLE001
        print("BDL services ERROR", repr(e))
        services = ["WMS_BDL"]
    for name in services:
        if "MapServer" not in str(name) and not any(k in name for k in ("BDL", "Wydziel", "Las", "las")):
            continue
        try:
            r = await c.get(f"{root}/{name}/MapServer/layers", params={"f": "json"})
            for lyr in r.json().get("layers", []):
                fields = [f["name"] for f in lyr.get("fields") or []]
                print(f"  {name}/{lyr.get('id')}: {lyr.get('name')} | geom={lyr.get('geometryType')} "
                      f"| maxRec={lyr.get('maxRecordCount')} | fields={fields[:18]}")
        except Exception as e:  # noqa: BLE001
            print(f"  {name} ERROR {e!r}")


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
            if body and body.get("meta", {}).get("weather_missing"):
                # emulate the browser: fetch the missing weather ourselves, upload, ask again
                meta = body["meta"]
                pts = meta["weather_missing"][:50]
                q = {"latitude": ",".join(f"{p[0]:.4f}" for p in pts),
                     "longitude": ",".join(f"{p[1]:.4f}" for p in pts),
                     **meta["weather_request"]["params"]}
                wr = await c.get(meta["weather_request"]["url"], params=q)
                up = await c.post(base + "/api/v1/weather", json={"points": pts, "data": wr.json()})
                print(f"browser-emulation: {len(pts)} points, open-meteo {wr.status_code}, "
                      f"upload {up.status_code} {up.text[:100]}")
                status, body = await get(f"/api/v1/predictions/bbox?west={west}&south={south}"
                                         f"&east={east}&north={north}&zoom={zoom}&species=all")
            if body and "features" in body:
                if body["features"] and cell is None:
                    lon_c, lat_c = body["features"][0]["geometry"]["coordinates"]
                    cell = (lat_c, lon_c)
                body = {"meta": body["meta"], "n": len(body["features"]),
                        "first": [f["properties"] for f in body["features"][:3]]}
            show("APP bbox", {"status": status, "body": body})
        if cell:
            status, body = await get(f"/api/v1/prediction?lat={cell[0]:.5f}&lon={cell[1]:.5f}&species=all")
            if body and body.get("results"):
                for r in body["results"]:
                    r.pop("components", None)
            show("APP point (forest cell)", {"status": status, "body": body})


async def probe_frontend_services():
    """Third-party services used directly by the browser."""
    urls = {
        "OpenFreeMap TileJSON": "https://tiles.openfreemap.org/planet",
        "OpenFreeMap glyphs": "https://tiles.openfreemap.org/fonts/Noto%20Sans%20Regular/0-255.pbf",
        "OpenFreeMap glyphs bold": "https://tiles.openfreemap.org/fonts/Noto%20Sans%20Bold/0-255.pbf",
        "Photon search": "https://photon.komoot.io/api/?q=Puszcza%20Kampinoska&limit=2&bbox=14.0,49.0,24.2,54.9",
        "Nominatim search": "https://nominatim.openstreetmap.org/search?q=Celestyn%C3%B3w&format=jsonv2&countrycodes=pl&limit=2",
    }
    browser_like = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/140.0 Safari/537.36",
        "Referer": "https://mapa-grzybow.onrender.com/",
        "Origin": "https://mapa-grzybow.onrender.com",
        "Accept-Language": "pl,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=browser_like) as c:
        for name, url in urls.items():
            try:
                r = await c.get(url)
                extra = ""
                if "TileJSON" in name:
                    j = r.json()
                    extra = f" layers={[v.get('id') for v in j.get('vector_layers', [])]}"
                elif "Photon" in name:
                    try:
                        extra = " " + json.dumps([f["properties"].get("name") for f in r.json().get("features", [])],
                                                 ensure_ascii=False)
                    except ValueError:
                        extra = " non-JSON: " + r.text[:200]
                elif "Nominatim" in name:
                    extra = " " + r.text[:150]
                print(f"{name}: {r.status_code} ({len(r.content)} B){extra}")
            except Exception as e:  # noqa: BLE001
                print(f"{name}: ERROR {e!r}")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if len(sys.argv) > 1 and sys.argv[1]:
        await probe_app(sys.argv[1])  # first, while the server is fresh
    await probe_frontend_services()
    await probe_bdl_layers()
    await probe_bdl()
    await probe_meteo()
    await probe_gbif()
    await probe_soil()


if __name__ == "__main__":
    asyncio.run(main())
