from datetime import date

import pytest

from app.prediction.engine import host_score, habitat_score, prior_score
from app.prediction.features import lagged_rain
from app.prediction.scoring import piecewise, rain_kernel, season_score, trapezoid, weighted_mean
from app.prediction.engine import ForestInfo
from app.species import SPECIES
from app.species.sites import parse_site_type
from app.species.trees import genus_for_code, parse_composition


def test_trapezoid_is_continuous():
    assert trapezoid(0, 1, 2, 3, 4) == 0
    assert trapezoid(1.5, 1, 2, 3, 4) == pytest.approx(0.5)
    assert trapezoid(2.5, 1, 2, 3, 4) == 1
    assert trapezoid(3.9, 1, 2, 3, 4) == pytest.approx(0.1)
    # no jumps
    xs = [i / 100 for i in range(0, 500)]
    ys = [trapezoid(x, 1, 2, 3, 4) for x in xs]
    assert max(abs(a - b) for a, b in zip(ys, ys[1:])) < 0.02


def test_piecewise_flat_outside():
    pts = [(0, 0.2), (10, 1.0)]
    assert piecewise(-5, pts) == 0.2
    assert piecewise(50, pts) == 1.0


def test_season_curve_smooth_and_peaks():
    cfg = SPECIES["boletus_edulis"]
    vals = [season_score(d, *cfg.season) for d in range(1, 366)]
    assert max(abs(a - b) for a, b in zip(vals, vals[1:])) < 0.05
    assert season_score(date(2026, 9, 20).timetuple().tm_yday, *cfg.season) > 0.95
    assert season_score(15, *cfg.season) < 0.05


def test_rain_kernel_normalized_and_peaked():
    k = rain_kernel(10, 4, 10, 35)
    assert sum(k) == pytest.approx(1.0)
    assert k.index(max(k)) == 9  # k=10


def test_lagged_rain_ignores_today():
    k = rain_kernel(10, 4, 10, 35)
    precip = [0.0] * 40 + [50.0]
    assert lagged_rain(precip, 40, k) == 0.0
    precip2 = [0.0] * 30 + [50.0] + [0.0] * 10  # 10 days before target
    assert lagged_rain(precip2, 40, k) > 2


def test_weighted_mean_skips_missing():
    v, cov = weighted_mean([(1.0, 1), (None, 1)])
    assert v == 1.0 and cov == 0.5
    assert weighted_mean([(None, 1)]) == (None, 0.0)


def test_host_share_matters():
    cfg = SPECIES["suillus_luteus"]
    much = ForestInfo(species=[("Pinus", 0.8), ("Alnus", 0.2)])
    little = ForestInfo(species=[("Pinus", 0.05), ("Alnus", 0.95)])
    assert host_score(cfg, much) > 0.9
    assert host_score(cfg, little) < 0.15
    assert host_score(cfg, ForestInfo(species=[])) is None


def test_dominant_only_host():
    cfg = SPECIES["boletus_edulis"]
    assert host_score(cfg, ForestInfo(species=[("Picea", None)])) == 1.0
    assert host_score(cfg, ForestInfo(species=[("Alnus", None)])) < 0.2


def test_site_type_parsing():
    s = parse_site_type("BMśw")
    assert (s.fertility, s.moisture, s.mountain) == ("BM", "SW", False)
    assert parse_site_type("Bs").moisture == "S"
    assert parse_site_type("LMw").fertility == "LM"
    g = parse_site_type("BMGśw")
    assert g.mountain and g.moisture == "SW"
    assert parse_site_type("LWyżśw").mountain
    assert parse_site_type("Ol").fertility == "OL"
    assert parse_site_type("Lł").fertility == "LL"
    assert parse_site_type("BMSW").fertility == "BM"
    assert parse_site_type("") is None


def test_habitat_prefers_right_sites():
    lut = SPECIES["suillus_luteus"]
    assert habitat_score(lut, ForestInfo(site_type="Bśw")) > habitat_score(lut, ForestInfo(site_type="Lw"))
    assert habitat_score(lut, ForestInfo(site_type=None)) is None


def test_tree_codes():
    assert genus_for_code("SO") == "Pinus"
    assert genus_for_code("ŚW") == "Picea"
    assert genus_for_code("DB.S") == "Quercus"
    assert genus_for_code("BRZ") == "Betula"
    assert genus_for_code("XYZ") is None
    comp = dict(parse_composition("6SO 3BRZ 1DB"))
    assert comp["Pinus"] == pytest.approx(0.6)


def test_prior_neutral_without_records():
    assert prior_score(0) == 0.5
    assert prior_score(None) is None
    assert 0.9 < prior_score(10) <= 1.0
