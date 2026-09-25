"""Behavioral tests A-G from the spec, for every configured species."""
from datetime import date

import pytest

from app.prediction.engine import ForestInfo, predict
from app.species import SPECIES
from tests.helpers import (
    alder_bog, bad_forest, ctx, drought_rain, good_forest, good_series, peak_date, series,
)

ALL = list(SPECIES.values())
ids = [c.id for c in ALL]


@pytest.mark.parametrize("cfg", ALL, ids=ids)
def test_a_good_forest_good_season_good_weather_is_high(cfg):
    r = predict(cfg, ctx(good_forest(cfg), good_series(cfg)), peak_date(cfg))
    assert r["score"] >= 65, r
    assert "HOST_TREE_STRONG" in r["positive_factors"]


@pytest.mark.parametrize("cfg", ALL, ids=ids)
def test_b_bad_forest_ideal_weather_is_low(cfg):
    r = predict(cfg, ctx(bad_forest(), good_series(cfg)), peak_date(cfg))
    assert r["score"] <= 20, r["score"]
    assert "HOST_MISSING" in r["negative_factors"]


def test_b_alder_bog_is_low_for_mycorrhizal_pine_species():
    for sid in ("suillus_luteus", "lactarius_deliciosus", "imleria_badia", "boletus_edulis"):
        cfg = SPECIES[sid]
        assert predict(cfg, ctx(alder_bog(), good_series(cfg)), peak_date(cfg))["score"] <= 20


@pytest.mark.parametrize("cfg", ALL, ids=ids)
def test_c_ideal_forest_long_drought_is_low(cfg):
    s = good_series(cfg, rain=drought_rain())
    s.daily["soil_moisture"] = [0.07] * len(s.dates)
    s.daily["rh"] = [60.0] * len(s.dates)
    s.daily["vpd"] = [1.8] * len(s.dates)
    s.daily["et0"] = [3.0] * len(s.dates)
    r = predict(cfg, ctx(good_forest(cfg), s), peak_date(cfg))
    assert r["score"] <= 35, r["score"]
    assert "RECENT_DROUGHT" in r["negative_factors"]


@pytest.mark.parametrize("cfg", ALL, ids=ids)
def test_d_good_forest_january_is_low(cfg):
    r = predict(cfg, ctx(good_forest(cfg), series([8.0 if i % 3 == 0 else 0.0 for i in range(40)],
                                                   tmean=0.0, soil_temp=1.0)), date(2026, 1, 15))
    assert r["score"] <= 10, r["score"]
    assert "OUTSIDE_SEASON" in r["negative_factors"]


def test_e_missing_soilgrids_still_works():
    cfg = SPECIES["boletus_edulis"]
    r = predict(cfg, ctx(good_forest(cfg), good_series(cfg), soil=None), peak_date(cfg))
    assert r["score"] > 0
    assert r["features"]["soil_source"] == "site_proxy"
    assert "SOILGRIDS_MISSING" in r["missing_data"]


def test_f_missing_gbif_still_works():
    cfg = SPECIES["imleria_badia"]
    d = peak_date(cfg)
    without = predict(cfg, ctx(good_forest(cfg), good_series(cfg), gbif_count=None), d)
    with_rec = predict(cfg, ctx(good_forest(cfg), good_series(cfg), gbif_count=5), d)
    assert without["score"] > 50
    assert "GBIF_MISSING" in without["missing_data"]
    # prior is small: records change the score only slightly
    assert 0 <= with_rec["score"] - without["score"] <= 10
    assert with_rec["confidence"] > without["confidence"]


@pytest.mark.parametrize("cfg", ALL, ids=ids)
def test_g_rain_today_after_drought_does_not_jump(cfg):
    def dry_series(rain, sm):
        s = good_series(cfg, rain=rain)
        n = len(s.dates)
        s.daily.update(soil_moisture=sm, rh=[60.0] * n, vpd=[1.8] * n, et0=[3.0] * n)
        return s

    dry = drought_rain()
    a = predict(cfg, ctx(good_forest(cfg), dry_series(dry, [0.07] * 40)), peak_date(cfg))["score"]
    b = predict(cfg, ctx(good_forest(cfg), dry_series(dry[:-1] + [40.0], [0.07] * 39 + [0.30])),
                peak_date(cfg))["score"]
    assert b <= 40, b
    assert b - a <= 12, (a, b)


def test_high_score_low_confidence_is_possible():
    cfg = SPECIES["boletus_edulis"]
    r = predict(cfg, ctx(good_forest(cfg), good_series(cfg), resolution_m=8000, lead_days=5),
                peak_date(cfg))
    assert r["score"] >= 60
    assert r["confidence"] < r["score"]


def test_missing_weather_gives_partial_score_and_low_confidence():
    cfg = SPECIES["boletus_edulis"]
    full = predict(cfg, ctx(good_forest(cfg), good_series(cfg)), peak_date(cfg))
    part = predict(cfg, ctx(good_forest(cfg), None), peak_date(cfg))
    assert "WEATHER_MISSING" in part["missing_data"]
    assert part["confidence"] <= full["confidence"] - 30
    assert part["score"] < full["score"]


def test_unknown_host_is_not_treated_as_absent():
    cfg = SPECIES["suillus_luteus"]
    unknown = ForestInfo(species=[], site_type="Bśw", stand_age=25)
    r_unknown = predict(cfg, ctx(unknown, good_series(cfg)), peak_date(cfg))
    r_bad = predict(cfg, ctx(alder_bog(), good_series(cfg)), peak_date(cfg))
    assert r_unknown["score"] > r_bad["score"] + 20
    assert "TREE_SPECIES_MISSING" in r_unknown["missing_data"]


def test_species_prefer_their_own_hosts():
    """Birch stand: babka high, maślak low; oak stand: borowik letni high, rydz low."""
    birch = ForestInfo(species=[("Betula", 0.9)], site_type="BMśw", stand_age=40)
    oak = ForestInfo(species=[("Quercus", 0.9)], site_type="LMśw", stand_age=90)
    s = SPECIES
    d = date(2026, 8, 20)

    def sc(sid, forest):
        return predict(s[sid], ctx(forest, good_series(s[sid])), d)["score"]

    assert sc("leccinum_scabrum", birch) > sc("suillus_luteus", birch) + 30
    assert sc("boletus_reticulatus", oak) > sc("lactarius_deliciosus", oak) + 30
