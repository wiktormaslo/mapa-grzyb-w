from fastapi.testclient import TestClient

from app.main import app

BBOX = {"west": 21.30, "south": 52.02, "east": 21.48, "north": 52.08, "zoom": 12}


def test_health_and_species(mock_sources):
    c = TestClient(app)
    assert c.get("/api/v1/health").json()["status"] == "ok"
    sp = c.get("/api/v1/species").json()["species"]
    ids = {s["id"] for s in sp}
    assert len(ids) == 10
    assert {"boletus_edulis", "imleria_badia", "suillus_luteus", "lactarius_deliciosus",
            "cantharellus_cibarius", "macrolepiota_procera"} <= ids


def test_bbox_end_to_end(mock_sources):
    c = TestClient(app)
    r = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "boletus_edulis"})
    assert r.status_code == 200, r.text
    fc = r.json()
    assert fc["meta"]["errors"] == []
    assert fc["meta"]["resolution_m"] == 500
    feats = fc["features"]
    assert len(feats) > 20
    # pine cells (west half) score high, alder cells (east half) score low
    def lon(f):
        return f["geometry"]["coordinates"][0]
    pine = [f["properties"]["score"] for f in feats if lon(f) < 21.39]
    alder = [f["properties"]["score"] for f in feats if lon(f) > 21.41]
    assert min(pine) > 60 and max(alder) < 25
    # grouped requests: few BDL calls, one weather call for many cells
    assert mock_sources.calls["bdl"] <= 18  # one per 16x16 tile and BDL layer, not per cell
    assert mock_sources.calls["open-meteo"] == 1


def test_bbox_all_species_returns_best(mock_sources):
    c = TestClient(app)
    fc = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "all"}).json()
    p = fc["features"][0]["properties"]
    assert p["score"] >= p["second_score"]
    assert p["species"] != p["second"]


def test_bbox_bdl_down_returns_no_fake_data(mock_sources):
    mock_sources.fail.add("bdl")
    fc = TestClient(app).get("/api/v1/predictions/bbox", params=BBOX).json()
    assert fc["features"] == [] and fc["meta"]["errors"]


def test_bbox_open_meteo_429_uses_fallback_grid(mock_sources):
    mock_sources.fail.add("open-meteo")
    c = TestClient(app)
    fc = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "boletus_edulis"}).json()
    assert fc["meta"]["errors"] == []
    assert fc["meta"]["weather_source"] == "grid"
    assert 50 < fc["features"][0]["properties"]["confidence"] < 90  # coarse weather penalty
    # zoomed in: browser is asked to refine the coarse weather
    assert fc["meta"]["weather_missing"]
    # cooldown: second request does not hit Open-Meteo again
    calls = mock_sources.calls["open-meteo"]
    c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "suillus_luteus"})
    assert mock_sources.calls["open-meteo"] == calls


def test_bbox_weather_down_gives_partial_low_confidence(mock_sources):
    c = TestClient(app)
    ok = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "boletus_edulis"}).json()
    from app.prediction import service
    from app.sources import open_meteo
    service._response_cache._data.clear()
    open_meteo._cache._data.clear()
    mock_sources.fail.update({"open-meteo", "grid"})
    bad = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "boletus_edulis"}).json()
    assert bad["meta"]["errors"]
    assert bad["features"][0]["properties"]["confidence"] < ok["features"][0]["properties"]["confidence"] - 25


def test_point_details(mock_sources):
    r = TestClient(app).get("/api/v1/prediction", params={"lat": 52.05, "lon": 21.35})
    body = r.json()
    assert body["in_forest"] and body["forest"]["trees"][0]["name_pl"] == "sosna"
    assert len(body["results"]) == 10
    top = body["results"][0]
    assert {"score", "confidence", "components", "positive_factors", "negative_factors"} <= set(top)
    assert top["features"]["soil_source"] == "soilgrids"


def test_point_outside_forest(mock_sources):
    body = TestClient(app).get("/api/v1/prediction", params={"lat": 53.0, "lon": 23.0}).json()
    assert body["in_forest"] is False and body["results"] == []


def test_invalid_input(mock_sources):
    c = TestClient(app)
    assert c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "xyz"}).status_code == 422
    assert c.get("/api/v1/predictions/bbox", params={**BBOX, "date": "2001-01-01"}).status_code == 422


def test_browser_weather_fallback_flow(mock_sources):
    """Server gets 429 and no grid -> tells the browser which points to fetch -> browser uploads."""
    from tests.mock_sources import open_meteo_location
    mock_sources.fail.update({"open-meteo", "grid"})
    c = TestClient(app)
    params = {**BBOX, "species": "boletus_edulis"}
    first = c.get("/api/v1/predictions/bbox", params=params).json()
    missing = first["meta"]["weather_missing"]
    assert missing and "daily" in first["meta"]["weather_request"]["params"]
    data = [open_meteo_location(lat, lon) for lat, lon in missing]
    r = c.post("/api/v1/weather", json={"points": missing, "data": data})
    assert r.json()["stored"] == len(missing)
    second = c.get("/api/v1/predictions/bbox", params=params).json()
    assert "weather_missing" not in second["meta"]
    assert second["features"][0]["properties"]["confidence"] > first["features"][0]["properties"]["confidence"]


def test_weather_upload_rejects_garbage(mock_sources):
    from tests.mock_sources import open_meteo_location
    c = TestClient(app)
    bad = open_meteo_location(52.0, 21.3)
    bad["daily"]["precipitation_sum"][0] = 5000  # implausible
    assert c.post("/api/v1/weather", json={"points": [[52.0, 21.3]], "data": [bad]}).json()["stored"] == 0
    far = open_meteo_location(50.0, 19.0)
    assert c.post("/api/v1/weather", json={"points": [[52.0, 21.3]], "data": [far]}).json()["stored"] == 0
    assert c.post("/api/v1/weather", json={"points": [[52.0, 21.3]], "data": []}).status_code == 422


def test_browser_refines_coarse_grid_weather(mock_sources):
    from tests.mock_sources import open_meteo_location
    mock_sources.fail.add("open-meteo")
    c = TestClient(app)
    params = {**BBOX, "species": "boletus_edulis"}
    coarse = c.get("/api/v1/predictions/bbox", params=params).json()
    missing = coarse["meta"]["weather_missing"]
    c.post("/api/v1/weather", json={"points": missing,
                                    "data": [open_meteo_location(a, b) for a, b in missing]})
    fine = c.get("/api/v1/predictions/bbox", params=params).json()
    assert fine["meta"]["weather_source"] == "open-meteo"
    assert "weather_missing" not in fine["meta"]
    assert fine["features"][0]["properties"]["confidence"] > coarse["features"][0]["properties"]["confidence"]


def test_zoomed_out_does_not_ask_browser_to_refine(mock_sources):
    mock_sources.fail.add("open-meteo")
    fc = TestClient(app).get("/api/v1/predictions/bbox", params={
        "west": 20.5, "south": 51.5, "east": 22.5, "north": 52.6, "zoom": 7}).json()
    assert fc["meta"]["resolution_m"] > 4000
    assert "weather_missing" not in fc["meta"]


def test_zoom_levels_are_consistent(mock_sources):
    """A 500 m cell is the mean of its four 250 m cells (same data at every zoom)."""
    from collections import defaultdict
    from app.prediction import grid
    c = TestClient(app)
    params = {"west": 21.38, "south": 52.03, "east": 21.42, "north": 52.05, "species": "boletus_edulis"}
    fine = c.get("/api/v1/predictions/bbox", params={**params, "zoom": 14}).json()
    coarse = c.get("/api/v1/predictions/bbox", params={**params, "zoom": 12}).json()
    assert fine["meta"]["resolution_m"] == 250 and coarse["meta"]["resolution_m"] == 500
    d250 = grid.Cell(0, 0, 250)
    fine_by_parent = defaultdict(list)
    for f in fine["features"]:
        lon, lat = f["geometry"]["coordinates"]
        i, j = int(lon // d250.dlon), int(lat // d250.dlat)
        fine_by_parent[(i // 2, j // 2)].append(f["properties"]["score"])
    d500 = grid.Cell(0, 0, 500)
    checked = 0
    for f in coarse["features"]:
        lon, lat = f["geometry"]["coordinates"]
        kids = fine_by_parent.get((int(lon // d500.dlon), int(lat // d500.dlat)))
        if kids and len(kids) == 4:
            assert abs(f["properties"]["score"] - sum(kids) / 4) <= 1
            checked += 1
    assert checked >= 3
