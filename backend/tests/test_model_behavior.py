"""Behavioral tests A-G from the spec."""
from datetime import date

from app.prediction.engine import predict
from app.species import SPECIES
from tests.helpers import (
    TARGET, alder_bog, ctx, drought_rain, good_rain, pine_forest, series,
)

ALL = list(SPECIES.values())


def test_a_good_forest_good_season_good_weather_is_high():
    for cfg in ALL:
        age = 25 if cfg.id in ("suillus_luteus", "lactarius_deliciosus") else 70
        r = predict(cfg, ctx(pine_forest(age=age), series(good_rain())), TARGET)
        assert r["score"] >= 65, (cfg.id, r)
        assert "HOST_TREE_STRONG" in r["positive_factors"]


def test_b_bad_forest_ideal_weather_is_low():
    for cfg in ALL:
        r = predict(cfg, ctx(alder_bog(), series(good_rain())), TARGET)
        assert r["score"] <= 20, (cfg.id, r["score"])
        assert "HOST_MISSING" in r["negative_factors"]


def test_c_ideal_forest_long_drought_is_low():
    for cfg in ALL:
        s = series(drought_rain(), soil_moisture=0.07, rh=60, vpd=1.8, et0=3.0)
        r = predict(cfg, ctx(pine_forest(age=40), s), TARGET)
        assert r["score"] <= 35, (cfg.id, r["score"])
        assert "RECENT_DROUGHT" in r["negative_factors"]


def test_d_good_forest_january_is_low():
    for cfg in ALL:
        r = predict(cfg, ctx(pine_forest(age=40), series(good_rain(), tmean=0.0, soil_temp=1.0)),
                    date(2026, 1, 15))
        assert r["score"] <= 10, (cfg.id, r["score"])
        assert "OUTSIDE_SEASON" in r["negative_factors"]


def test_e_missing_soilgrids_still_works():
    cfg = SPECIES["boletus_edulis"]
    r = predict(cfg, ctx(pine_forest(), series(good_rain()), soil=None), TARGET)
    assert r["score"] > 0
    assert r["features"]["soil_source"] == "site_proxy"
    assert "SOILGRIDS_MISSING" in r["missing_data"]


def test_f_missing_gbif_still_works():
    cfg = SPECIES["imleria_badia"]
    without = predict(cfg, ctx(pine_forest(), series(good_rain()), gbif_count=None), TARGET)
    with_rec = predict(cfg, ctx(pine_forest(), series(good_rain()), gbif_count=5), TARGET)
    assert without["score"] > 50
    assert "GBIF_MISSING" in without["missing_data"]
    # prior is small: records change the score only slightly
    assert 0 <= with_rec["score"] - without["score"] <= 10
    assert with_rec["confidence"] > without["confidence"]


def test_g_rain_today_after_drought_does_not_jump():
    for cfg in ALL:
        dry = drought_rain()
        wet_today = dry[:-1] + [40.0]
        s_dry = series(dry, soil_moisture=0.07, rh=60, vpd=1.8, et0=3.0)
        sm = [0.07] * (len(dry) - 1) + [0.30]
        s_wet = series(wet_today, soil_moisture=sm, rh=60, vpd=1.8, et0=3.0)
        a = predict(cfg, ctx(pine_forest(age=40), s_dry), TARGET)["score"]
        b = predict(cfg, ctx(pine_forest(age=40), s_wet), TARGET)["score"]
        assert b <= 40, (cfg.id, b)
        assert b - a <= 12, (cfg.id, a, b)


def test_high_score_low_confidence_is_possible():
    cfg = SPECIES["boletus_edulis"]
    r = predict(cfg, ctx(pine_forest(), series(good_rain()), resolution_m=8000, lead_days=5),
                TARGET)
    assert r["score"] >= 60
    assert r["confidence"] < r["score"]


def test_missing_weather_gives_partial_score_and_low_confidence():
    cfg = SPECIES["boletus_edulis"]
    full = predict(cfg, ctx(pine_forest(), series(good_rain())), TARGET)
    part = predict(cfg, ctx(pine_forest(), None), TARGET)
    assert "WEATHER_MISSING" in part["missing_data"]
    assert part["confidence"] <= full["confidence"] - 30
    assert part["score"] < full["score"]


def test_unknown_host_is_not_treated_as_absent():
    from app.prediction.engine import ForestInfo
    cfg = SPECIES["suillus_luteus"]
    unknown = ForestInfo(species=[], site_type="Bśw", stand_age=25)
    r_unknown = predict(cfg, ctx(unknown, series(good_rain())), TARGET)
    r_bad = predict(cfg, ctx(alder_bog(), series(good_rain())), TARGET)
    assert r_unknown["score"] > r_bad["score"] + 20
    assert "TREE_SPECIES_MISSING" in r_unknown["missing_data"]
