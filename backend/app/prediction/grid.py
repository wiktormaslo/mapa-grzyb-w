"""Globally aligned analysis grid with zoom-adaptive resolution and cache-friendly tiles."""
from __future__ import annotations

import math
from dataclasses import dataclass

M_PER_DEG_LAT = 111_320.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(52.0))  # fixed reference latitude

LADDER = [250, 500, 1000, 2000, 4000, 8000, 16000, 32000]
MAX_CELLS = 2500
TILE = 16  # cells per tile side (one BDL request per tile)

# Poland bounding box (with a small margin)
PL_BBOX = (14.07, 48.99, 24.16, 54.85)


@dataclass(frozen=True)
class Cell:
    i: int
    j: int
    res: int

    @property
    def dlon(self) -> float:
        return self.res / M_PER_DEG_LON

    @property
    def dlat(self) -> float:
        return self.res / M_PER_DEG_LAT

    @property
    def center(self) -> tuple[float, float]:
        """(lat, lon)"""
        return ((self.j + 0.5) * self.dlat, (self.i + 0.5) * self.dlon)

    def polygon(self) -> list[list[float]]:
        w, s = self.i * self.dlon, self.j * self.dlat
        e, n = w + self.dlon, s + self.dlat
        return [[round(w, 6), round(s, 6)], [round(e, 6), round(s, 6)], [round(e, 6), round(n, 6)],
                [round(w, 6), round(n, 6)], [round(w, 6), round(s, 6)]]


def min_res_for_zoom(zoom: float) -> int:
    if zoom >= 13:
        return 250
    if zoom >= 12:
        return 500
    if zoom >= 10.5:
        return 1000
    if zoom >= 9:
        return 2000
    if zoom >= 8:
        return 4000
    return 8000


def clip_to_poland(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float] | None:
    w, s, e, n = bbox
    w, s = max(w, PL_BBOX[0]), max(s, PL_BBOX[1])
    e, n = min(e, PL_BBOX[2]), min(n, PL_BBOX[3])
    if w >= e or s >= n:
        return None
    return (w, s, e, n)


def count_cells(bbox, res: int) -> int:
    w, s, e, n = bbox
    return math.ceil((e - w) * M_PER_DEG_LON / res + 1) * math.ceil((n - s) * M_PER_DEG_LAT / res + 1)


def choose_resolution(bbox, zoom: float) -> int:
    floor = min_res_for_zoom(zoom)
    for res in LADDER:
        if res >= floor and count_cells(bbox, res) <= MAX_CELLS:
            return res
    return LADDER[-1]


def cell_range(bbox, res: int) -> tuple[int, int, int, int]:
    w, s, e, n = bbox
    dlon, dlat = res / M_PER_DEG_LON, res / M_PER_DEG_LAT
    return (math.floor(w / dlon), math.floor(s / dlat), math.floor(e / dlon), math.floor(n / dlat))


def tiles_for(bbox, res: int) -> list[tuple[int, int]]:
    i0, j0, i1, j1 = cell_range(bbox, res)
    return [(ti, tj) for ti in range(i0 // TILE, i1 // TILE + 1)
            for tj in range(j0 // TILE, j1 // TILE + 1)]


def tile_cells(ti: int, tj: int, res: int) -> list[Cell]:
    """Cells of a tile whose centre lies inside the Poland bbox, row-major (spatially ordered)."""
    out = []
    for j in range(tj * TILE, (tj + 1) * TILE):
        for i in range(ti * TILE, (ti + 1) * TILE):
            c = Cell(i, j, res)
            lat, lon = c.center
            if PL_BBOX[0] <= lon <= PL_BBOX[2] and PL_BBOX[1] <= lat <= PL_BBOX[3]:
                out.append(c)
    return out


def cell_in_bbox(c: Cell, bbox) -> bool:
    lat, lon = c.center
    w, s, e, n = bbox
    return w - c.dlon / 2 <= lon <= e + c.dlon / 2 and s - c.dlat / 2 <= lat <= n + c.dlat / 2


def weather_step(res: int) -> tuple[float, float]:
    """(dlat, dlon) of the weather grid; much coarser than forest data.
    Open-Meteo models for Poland are ~2-7 km, so ~5 km is the finest useful step."""
    if res <= 500:
        return (0.05, 0.075)
    if res <= 1000:
        return (0.1, 0.15)
    if res <= 4000:
        return (0.2, 0.3)
    return (0.4, 0.6)


def snap_weather(lat: float, lon: float, res: int) -> tuple[float, float]:
    dlat, dlon = weather_step(res)
    return (round(round(lat / dlat) * dlat, 4), round(round(lon / dlon) * dlon, 4))


# the fallback grid is ~0.3 deg; asking the browser for finer data only helps below this
REFINE_MAX_RES = 4000
