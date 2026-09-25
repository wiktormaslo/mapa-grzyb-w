"""Smooth scoring primitives. All return values in [0, 1] unless stated otherwise."""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def piecewise(x: float, points: Sequence[tuple[float, float]]) -> float:
    """Linear interpolation through (x, y) points; flat outside the range."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def trapezoid(x: float, a: float, b: float, c: float, d: float) -> float:
    """0 below a, rises to 1 at b, stays 1 until c, falls to 0 at d."""
    return piecewise(x, [(a, 0.0), (b, 1.0), (c, 1.0), (d, 0.0)])


def gaussian(x: float, mu: float, sigma: float) -> float:
    return math.exp(-0.5 * ((x - mu) / sigma) ** 2)


def _cos_ramp(t: float) -> float:
    """Smooth 0->1 ramp for t in [0, 1]."""
    t = clamp(t)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def season_score(doy: float, rise_start: float, peak_start: float, peak_end: float,
                 fall_end: float, floor: float = 0.02) -> float:
    """Continuous seasonal curve over day-of-year with cosine flanks."""
    if doy <= rise_start or doy >= fall_end:
        v = 0.0
    elif doy < peak_start:
        v = _cos_ramp((doy - rise_start) / (peak_start - rise_start))
    elif doy <= peak_end:
        v = 1.0
    else:
        v = 1.0 - _cos_ramp((doy - peak_end) / (fall_end - peak_end))
    return floor + (1.0 - floor) * v


def rain_kernel(peak_day: float, width_before: float, width_after: float,
                max_lag: int = 35) -> list[float]:
    """Asymmetric Gaussian lag weights for k = 1..max_lag (index 0 -> k=1), sum = 1."""
    w = []
    for k in range(1, max_lag + 1):
        width = width_before if k < peak_day else width_after
        w.append(gaussian(k, peak_day, width))
    s = sum(w)
    return [x / s for x in w]


def weighted_mean(items: Iterable[tuple[float | None, float]]) -> tuple[float | None, float]:
    """Weighted mean over items whose value is not None.

    Returns (mean or None, fraction of total weight that was available)."""
    total_w = 0.0
    used_w = 0.0
    acc = 0.0
    for value, weight in items:
        total_w += weight
        if value is None:
            continue
        used_w += weight
        acc += value * weight
    if used_w == 0:
        return None, 0.0
    return acc / used_w, used_w / total_w if total_w else 0.0
