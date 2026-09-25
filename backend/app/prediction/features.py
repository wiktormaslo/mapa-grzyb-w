"""Weather feature engineering from daily series (history + forecast)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# daily series keys used across the app
SERIES_KEYS = ("precip", "tmean", "tmax", "tmin", "rh", "et0", "vpd", "soil_moisture", "soil_temp")

MIN_COVERAGE = 0.8


@dataclass
class WeatherSeries:
    dates: list[str]                                   # ISO dates, ascending, consecutive
    daily: dict[str, list[float | None]] = field(default_factory=dict)
    elevation: float | None = None
    lat: float | None = None
    lon: float | None = None

    def index_of(self, iso_date: str) -> int | None:
        try:
            return self.dates.index(iso_date)
        except ValueError:
            return None


def _window(values: list[float | None] | None, start: int, end: int) -> list[float | None] | None:
    """values[start:end] (end exclusive), None if out of range."""
    if values is None or start < 0 or end > len(values) or start >= end:
        return None
    return values[start:end]


def _mean(vals: list[float | None] | None) -> float | None:
    if not vals:
        return None
    ok = [v for v in vals if v is not None]
    if len(ok) < MIN_COVERAGE * len(vals):
        return None
    return sum(ok) / len(ok)


def _sum(vals: list[float | None] | None) -> float | None:
    m = _mean(vals)
    return None if m is None else m * len(vals)


def _days_since(precip: list[float | None], end: int, threshold: float, max_days: int = 60) -> float | None:
    """Days from `end` (inclusive) back to the latest day with rain >= threshold."""
    if end >= len(precip):
        return None
    for d in range(0, max_days):
        i = end - d
        if i < 0:
            return float(d)  # no rain in available history: at least d days
        v = precip[i]
        if v is not None and v >= threshold:
            return float(d)
    return float(max_days)


def _rolling_sum(values: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        w = [v for v in values[max(0, i - n + 1): i + 1] if v is not None]
        out.append(sum(w) if w else None)
    return out


def lagged_rain(precip: list[float | None], t: int, kernel: list[float]) -> float | None:
    """sum_k rain[t-k] * w[k] for k = 1..len(kernel); rain on day t itself is ignored."""
    acc = 0.0
    used = 0.0
    for k, w in enumerate(kernel, start=1):
        i = t - k
        if i < 0:
            continue
        v = precip[i]
        if v is None:
            continue
        acc += v * w
        used += w
    if used < MIN_COVERAGE:
        return None
    return acc / used


def compute_weather_features(s: WeatherSeries, t: int, min_effect_lag: int = 3) -> dict[str, Any]:
    """Features for target day index t. Missing inputs -> None (never 0)."""
    d = s.daily
    p = d.get("precip")
    f: dict[str, Any] = {}

    def rain_sum(days: int, end: int | None = None) -> float | None:
        e = t + 1 if end is None else end
        return _sum(_window(p, e - days, e))

    for n in (3, 7, 14, 21, 30):
        f[f"rain_{n}d"] = rain_sum(n)
    w14 = _window(p, t - 13, t + 1)
    f["rain_days_14d"] = None if w14 is None or _mean(w14) is None else float(
        sum(1 for v in w14 if v is not None and v >= 1.0))
    f["days_since_rain_5mm"] = None if p is None else _days_since(p, t, 5.0)
    f["days_since_rain_10mm"] = None if p is None else _days_since(p, t, 10.0)

    # drought measures on a window that ends before rain could have had an effect
    te = t - min_effect_lag
    f["rain_30d_effective"] = rain_sum(30, te + 1)
    # "event" = at least 10 mm within 3 consecutive days (frequent moderate rain is not drought)
    f["dry_days_effective"] = None if p is None or te < 0 else _days_since(_rolling_sum(p, 3), te, 10.0)

    for n in (7, 14, 21):
        f[f"temperature_mean_{n}d"] = _mean(_window(d.get("tmean"), t - n + 1, t + 1))
    f["tmax_mean_7d"] = _mean(_window(d.get("tmax"), t - 6, t + 1))
    tmin7 = _window(d.get("tmin"), t - 6, t + 1)
    f["tmin_7d"] = None if tmin7 is None or _mean(tmin7) is None else min(v for v in tmin7 if v is not None)
    f["tmin_7d_values"] = tmin7
    f["precip_series"] = p
    f["t_index"] = t

    f["soil_moisture_mean_7d"] = _mean(_window(d.get("soil_moisture"), t - 6, t + 1))
    f["soil_moisture_mean_14d"] = _mean(_window(d.get("soil_moisture"), t - 13, t + 1))
    f["soil_temperature"] = _mean(_window(d.get("soil_temp"), t - 6, t + 1))
    f["humidity"] = _mean(_window(d.get("rh"), t - 6, t + 1))
    f["vpd"] = _mean(_window(d.get("vpd"), t - 6, t + 1))
    et0_14 = _sum(_window(d.get("et0"), t - 13, t + 1))
    f["et0_14d"] = et0_14
    f["water_balance_14d"] = None if et0_14 is None or f["rain_14d"] is None else f["rain_14d"] - et0_14
    return f
