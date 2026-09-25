"""Mock HTTP transport emulating BDL (ArcGIS), Open-Meteo, GBIF and SoilGrids responses."""
import json
from datetime import timedelta
from urllib.parse import parse_qs

import httpx

from app.prediction.service import today_pl

PINE = {
    "attributes": {"adress_forest": "14-15-1-01-100-a-00", "site_type": "BMśw",
                   "species_cd_d": "SO", "species_age": 65, "part_cd": "DRZ"},
    "geometry": {"rings": [[[21.30, 52.00], [21.40, 52.00], [21.40, 52.10], [21.30, 52.10], [21.30, 52.00]]]},
}
ALDER = {
    "attributes": {"adress_forest": "14-15-1-01-101-b-00", "site_type": "Ol",
                   "species_cd_d": "OL", "species_age": 50},
    "geometry": {"rings": [[[21.40, 52.00], [21.50, 52.00], [21.50, 52.10], [21.40, 52.10], [21.40, 52.00]]]},
}


def open_meteo_location(lat, lon, rain_every=3, rain_mm=8.0):
    today = today_pl()
    days = [today + timedelta(days=d) for d in range(-40, 6)]
    dates = [d.isoformat() for d in days]
    n = len(dates)
    hours = [f"{d}T{h:02d}:00" for d in dates for h in range(24)]
    return {
        "latitude": lat, "longitude": lon, "elevation": 110.0,
        "daily": {
            "time": dates,
            "precipitation_sum": [rain_mm if i % rain_every == 0 else 0.0 for i in range(n)],
            "temperature_2m_mean": [13.0] * n, "temperature_2m_max": [18.0] * n,
            "temperature_2m_min": [8.0] * n, "relative_humidity_2m_mean": [85.0] * n,
            "et0_fao_evapotranspiration": [1.5] * n, "vapour_pressure_deficit_max": [0.6] * n,
        },
        "hourly": {"time": hours, "soil_moisture_3_to_9cm": [0.26] * len(hours),
                   "soil_temperature_6cm": [12.0] * len(hours)},
    }


class MockState:
    def __init__(self):
        self.calls = {"bdl": 0, "open-meteo": 0, "gbif": 0, "soilgrids": 0}
        self.fail = set()
        self.last_meteo_params = None


def make_transport(state: MockState) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "bdl" in host:
            state.calls["bdl"] += 1
            if "bdl" in state.fail:
                return httpx.Response(503, text="down")
            form = parse_qs(request.content.decode())
            assert form["geometryType"] == ["esriGeometryMultipoint"]
            return httpx.Response(200, json={"features": [PINE, ALDER]})
        if "open-meteo" in host:
            state.calls["open-meteo"] += 1
            if "open-meteo" in state.fail:
                return httpx.Response(429, json={"error": True, "reason": "Too many requests"})
            q = request.url.params
            state.last_meteo_params = dict(q)
            lats = [float(x) for x in q["latitude"].split(",")]
            lons = [float(x) for x in q["longitude"].split(",")]
            locs = [open_meteo_location(a, b) for a, b in zip(lats, lons)]
            return httpx.Response(200, content=json.dumps(locs if len(locs) > 1 else locs[0]))
        if "gbif" in host:
            state.calls["gbif"] += 1
            return httpx.Response(200, json={"endOfRecords": True, "results": [
                {"decimalLatitude": 52.05, "decimalLongitude": 21.35, "year": 2015,
                 "eventDate": "2015-09-20", "coordinateUncertaintyInMeters": 30},
            ]})
        if "githubusercontent" in host:
            if "grid" in state.fail:
                return httpx.Response(404)
            import gzip
            from datetime import datetime, timezone
            loc = open_meteo_location(52.0, 21.3, rain_every=4, rain_mm=6.0)
            names = {"precipitation_sum": "precip", "temperature_2m_mean": "tmean",
                     "temperature_2m_max": "tmax", "temperature_2m_min": "tmin",
                     "relative_humidity_2m_mean": "rh", "et0_fao_evapotranspiration": "et0",
                     "vapour_pressure_deficit_max": "vpd"}
            d = {v: loc["daily"][k] for k, v in names.items()}
            n = len(loc["daily"]["time"])
            d["soil_moisture"] = [0.2] * n
            d["soil_temp"] = [12.0] * n
            doc = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "step": [0.3, 0.45], "dates": loc["daily"]["time"],
                   "points": [{"lat": 51.9, "lon": 21.15, "elev": 100, "d": d},
                              {"lat": 52.2, "lon": 21.6, "elev": 100, "d": d}]}
            state.calls["grid"] = state.calls.get("grid", 0) + 1
            return httpx.Response(200, content=gzip.compress(json.dumps(doc).encode()))
        if "isric" in host:
            state.calls["soilgrids"] += 1
            if "soilgrids" in state.fail:
                return httpx.Response(500)
            return httpx.Response(200, json={"properties": {"layers": [
                {"name": "phh2o", "unit_measure": {"d_factor": 10},
                 "depths": [{"label": "0-5cm", "values": {"mean": 45}}]},
                {"name": "sand", "unit_measure": {"d_factor": 10},
                 "depths": [{"label": "0-5cm", "values": {"mean": 850}}]},
            ]}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)
