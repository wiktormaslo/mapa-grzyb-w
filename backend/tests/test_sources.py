import asyncio

from app.sources import bdl, gbif, open_meteo, soilgrids
from tests.mock_sources import PINE, open_meteo_location


def test_bdl_attribute_parsing():
    info = bdl.parse_attributes(PINE["attributes"])
    assert info.species == [("Pinus", None)]  # part_cd 'DRZ' is not a share
    assert info.site_type == "BMśw" and info.stand_age == 65
    info2 = bdl.parse_attributes({"SPECIES_CD": "DB", "part_cd": "7"})
    assert info2.species == [("Quercus", 0.7)]
    empty = bdl.parse_attributes({"foo": 1})
    assert empty.species == [] and empty.site_type is None and empty.stand_age is None


def test_bdl_point_matching_with_hole():
    feat = {"attributes": {"species_cd_d": "SO"}, "geometry": {"rings": [
        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
        [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
    ]}}
    res = bdl.match_points([(1, 1), (5, 5), (20, 20)], [feat])
    assert res[0] is not None and res[1] is None and res[2] is None


def test_bdl_query_grouped(mock_sources):
    pts = [(52.05, 21.35), (52.05, 21.45), (53.0, 23.0)]
    res = asyncio.run(bdl.query_points(pts))
    assert mock_sources.calls["bdl"] == 1
    assert res[0].species[0][0] == "Pinus"
    assert res[1].species[0][0] == "Alnus"
    assert res[2] is None


def test_open_meteo_parse_and_grouping(mock_sources):
    s = open_meteo.parse_location(open_meteo_location(52, 21))
    assert len(s.dates) == 46 and abs(s.daily["soil_moisture"][0] - 0.26) < 1e-9
    pts = [(52.0, 21.0), (52.1, 21.15), (52.2, 21.3)]
    data, errors = asyncio.run(open_meteo.fetch_weather(pts))
    assert not errors and len(data) == 3
    assert mock_sources.calls["open-meteo"] == 1
    assert int(mock_sources.last_meteo_params["past_days"]) >= 36
    asyncio.run(open_meteo.fetch_weather(pts))
    assert mock_sources.calls["open-meteo"] == 1  # cached


def test_open_meteo_failure_reports_error(mock_sources):
    mock_sources.fail.add("open-meteo")
    data, errors = asyncio.run(open_meteo.fetch_weather([(52.0, 21.0)]))
    assert data == {} and errors and "429" in errors[0]


def test_soilgrids_parse(mock_sources):
    s = asyncio.run(soilgrids.fetch_soil(52.05, 21.35))
    assert abs(s.ph - 4.5) < 1e-9 and abs(s.sand - 85) < 1e-9
    mock_sources.fail.add("soilgrids")
    assert asyncio.run(soilgrids.fetch_soil(50.0, 20.0)) is None


def test_gbif_filtering_and_counts():
    recs = [
        {"decimalLatitude": 52.0, "decimalLongitude": 21.0, "eventDate": "2020-09-01", "year": 2020},
        {"decimalLatitude": 52.0, "decimalLongitude": 21.0, "eventDate": "2020-09-01", "year": 2020},  # dup
        {"decimalLatitude": 52.0, "decimalLongitude": 21.0, "year": 1950},  # old
        {"decimalLatitude": 52.1, "decimalLongitude": 21.1, "coordinateUncertaintyInMeters": 50000},
        {"decimalLongitude": 21.0},
    ]
    pts = gbif.filter_records(recs)
    assert pts == [(52.0, 21.0)]
    gbif.reset()
    assert gbif.count_near("x", 52, 21) is None
    gbif.set_points("x", pts)
    assert gbif.count_near("x", 52.01, 21.01) == 1
    assert gbif.count_near("x", 54.0, 18.0) == 0


def test_bdl_real_attribute_format():
    # attribute layout observed in the live BDL service (WMS_BDL/MapServer/5)
    real = {"adress_forest": "17-01-1-03-291   -a   -00", "area_type_cd": "D-STAN    ",
            "site_type_cd": "BŚW    ", "species_cd_d": "SO       ", "part_cd": "8  ",
            "species_age": 11, "stand_struct_cd": "DRZEW  "}
    info = bdl.parse_attributes(real)
    assert info.species == [("Pinus", 0.8)]
    assert info.site_type == "BŚW" and info.stand_age == 11
    assert bdl.is_stand(real)
    assert bdl.parse_attributes({**real, "part_cd": "10 "}).species == [("Pinus", 1.0)]
    assert not bdl.is_stand({**real, "area_type_cd": "ZRĄB      "})
    assert not bdl.is_stand({**real, "area_type_cd": "L ENERG   "})


def test_bdl_clear_cut_is_not_forest():
    clear_cut = {"attributes": {"area_type_cd": "ZRĄB", "site_type_cd": "BŚW"},
                 "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}
    assert bdl.match_points([(0.5, 0.5)], [clear_cut]) == [None]
