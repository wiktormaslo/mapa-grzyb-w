"""Build a coarse national weather grid from Open-Meteo (run by the weather-grid GitHub workflow).

Free Render instances share outbound IPs, so Open-Meteo often answers 429 there. This file,
refreshed every few hours from GitHub Actions and served from the `weather-data` branch,
is the backend's fallback weather source.

usage: python -m scripts.build_weather_grid OUT_FILE.json.gz
"""
from __future__ import annotations

import asyncio
import gzip
import json
import sys
from datetime import datetime, timezone

from app.sources import open_meteo
from app.sources.http import SourceError

LAT0, LAT1, DLAT = 49.0, 54.9, 0.3
LON0, LON1, DLON = 14.1, 24.2, 0.45
CHUNK = 40
PAUSE_S = 25  # stay well below Open-Meteo's per-minute limit
DIGITS = {"precip": 1, "tmean": 1, "tmax": 1, "tmin": 1, "rh": 0, "et0": 2, "vpd": 2,
          "soil_moisture": 3, "soil_temp": 1}


def grid_points() -> list[tuple[float, float]]:
    pts = []
    lat = LAT0
    while lat <= LAT1 + 1e-9:
        lon = LON0
        while lon <= LON1 + 1e-9:
            pts.append((round(lat, 3), round(lon, 3)))
            lon += DLON
        lat += DLAT
    return pts


def _r(v, d):
    return None if v is None else round(v, d)


async def main(out: str) -> None:
    pts = grid_points()
    rows = []
    dates: list[str] | None = None
    for i in range(0, len(pts), CHUNK):
        chunk = pts[i:i + CHUNK]
        for attempt in range(3):
            try:
                series = await open_meteo._request(chunk)
                break
            except SourceError as e:
                print(f"chunk {i}: {e}, retry {attempt + 1}", flush=True)
                await asyncio.sleep(60)
        else:
            raise SystemExit("Open-Meteo unavailable")
        for (lat, lon), s in zip(chunk, series):
            if dates is None:
                dates = s.dates
            if s.dates != dates:
                continue
            rows.append({"lat": lat, "lon": lon, "elev": s.elevation,
                         "d": {k: [_r(v, DIGITS.get(k, 2)) for v in vals] for k, vals in s.daily.items()}})
        print(f"{min(i + CHUNK, len(pts))}/{len(pts)} points", flush=True)
        if i + CHUNK < len(pts):
            await asyncio.sleep(PAUSE_S)
    doc = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "step": [DLAT, DLON], "dates": dates, "points": rows}
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"))
    print(f"wrote {out}: {len(rows)} points, {len(dates or [])} days")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "weather_grid.json.gz"))
