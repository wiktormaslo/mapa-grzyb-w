from fastapi.testclient import TestClient

from app.main import app

BBOX = {"west": 21.30, "south": 52.02, "east": 21.48, "north": 52.08, "zoom": 12}


def test_health_and_species(mock_sources):
    c = TestClient(app)
    assert c.get("/api/v1/health").json()["status"] == "ok"
    sp = c.get("/api/v1/species").json()["species"]
    assert {s["id"] for s in sp} == {"boletus_edulis", "imleria_badia", "suillus_luteus",
                                     "lactarius_deliciosus"}


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
        return f["geometry"]["coordinates"][0][0][0]
    pine = [f["properties"]["score"] for f in feats if lon(f) < 21.39]
    alder = [f["properties"]["score"] for f in feats if lon(f) > 21.41]
    assert min(pine) > 60 and max(alder) < 25
    # grouped requests: few BDL calls, one weather call for many cells
    assert mock_sources.calls["bdl"] <= 9  # one per 16x16 tile, not per cell
    assert mock_sources.calls["open-meteo"] == 1


def test_bbox_all_species_returns_best(mock_sources):
    c = TestClient(app)
    fc = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "all"}).json()
    p = fc["features"][0]["properties"]
    assert p["score"] == max(p["scores"].values())
    assert p["species"] in p["scores"]


def test_bbox_bdl_down_returns_no_fake_data(mock_sources):
    mock_sources.fail.add("bdl")
    fc = TestClient(app).get("/api/v1/predictions/bbox", params=BBOX).json()
    assert fc["features"] == [] and fc["meta"]["errors"]


def test_bbox_weather_down_gives_partial_low_confidence(mock_sources):
    c = TestClient(app)
    ok = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "boletus_edulis"}).json()
    from app.prediction import service
    from app.sources import open_meteo
    service._response_cache._data.clear()
    open_meteo._cache._data.clear()
    mock_sources.fail.add("open-meteo")
    bad = c.get("/api/v1/predictions/bbox", params={**BBOX, "species": "boletus_edulis"}).json()
    assert bad["meta"]["errors"]
    assert bad["features"][0]["properties"]["confidence"] < ok["features"][0]["properties"]["confidence"] - 25


def test_point_details(mock_sources):
    r = TestClient(app).get("/api/v1/prediction", params={"lat": 52.05, "lon": 21.35})
    body = r.json()
    assert body["in_forest"] and body["forest"]["trees"][0]["name_pl"] == "sosna"
    assert len(body["results"]) == 4
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
