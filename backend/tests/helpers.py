"""Synthetic inputs for model tests."""
from datetime import date, timedelta

from app.prediction.engine import Context, ForestInfo
from app.prediction.features import WeatherSeries, compute_weather_features

TARGET = date(2026, 9, 25)
N_HIST = 40


def series(rain, tmean=13.0, soil_moisture=0.25, rh=85.0, vpd=0.6, et0=1.5, tmin=None,
           soil_temp=12.0) -> WeatherSeries:
    """rain: list of daily mm, last element = target day."""
    n = len(rain)
    dates = [(TARGET - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]

    def arr(v):
        return list(v) if isinstance(v, list) else [v] * n

    tm = arr(tmean)
    return WeatherSeries(dates=dates, daily={
        "precip": list(rain), "tmean": tm, "tmax": [t + 6 for t in tm],
        "tmin": arr(tmin) if tmin is not None else [t - 5 for t in tm],
        "rh": arr(rh), "et0": arr(et0), "vpd": arr(vpd),
        "soil_moisture": arr(soil_moisture), "soil_temp": arr(soil_temp),
    }, elevation=120.0)


def good_rain():
    # regular rain: 8 mm every 3 days
    return [8.0 if i % 3 == 0 else 0.0 for i in range(N_HIST)]


def drought_rain():
    return [0.0] * N_HIST


def features(s: WeatherSeries):
    return compute_weather_features(s, len(s.dates) - 1)


def pine_forest(age=60, site="BMśw"):
    return ForestInfo(species=[("Pinus", 0.8), ("Betula", 0.2)], species_codes=["SO", "BRZ"],
                      site_type=site, stand_age=age)


def alder_bog():
    return ForestInfo(species=[("Alnus", 1.0)], species_codes=["OL"], site_type="Ol", stand_age=60)


def ctx(forest, weather_series=None, **kw):
    w = features(weather_series) if weather_series is not None else None
    return Context(forest=forest, weather=w, elevation=120.0, **kw)


# ---- species-specific "ideal" and "bad" inputs (derived from each config) ----
from datetime import date as _date  # noqa: E402
from app.prediction.engine import ForestInfo as _FI  # noqa: E402


def good_forest(cfg, share=0.8):
    host = max(cfg.host_trees, key=cfg.host_trees.get)
    fert = max(cfg.site_fertility, key=cfg.site_fertility.get)
    site = {"B": "Bśw", "BM": "BMśw", "LM": "LMśw", "L": "Lśw", "OL": "Ol", "LL": "Lł"}[fert]
    a, b, c, d = cfg.stand_age_pref
    return _FI(species=[(host, share), ("Salix", round(1 - share, 2))], site_type=site,
               stand_age=(b + c) / 2)


def bad_forest():
    # willow (no species here is mycorrhizal with it) on a bog pine site
    return _FI(species=[("Salix", 1.0)], site_type="Bb", stand_age=40)


def peak_date(cfg, year=2026):
    doy = int((cfg.season[1] + cfg.season[2]) / 2)
    return _date(year, 1, 1) + timedelta(days=doy - 1)


def plateau_mid(points):
    ones = [x for x, y in points if y >= 1.0]
    return (min(ones) + max(ones)) / 2


def good_series(cfg, rain=None):
    return series(rain if rain is not None else good_rain(),
                  tmean=plateau_mid(cfg.temperature_pref),
                  soil_temp=plateau_mid(cfg.soil_temperature_pref))
