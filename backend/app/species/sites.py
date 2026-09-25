"""Forest site type (typ siedliskowy lasu) parsing, e.g. 'BMśw', 'LMw', 'BMGśw', 'LWyżśw', 'Ol'."""
from __future__ import annotations

from dataclasses import dataclass

from app.species.trees import normalize_code

# rough soil proxies for each fertility class (used when SoilGrids is unavailable)
FERTILITY_SOIL_PROXY = {
    "B": {"ph": 4.0, "sand": 92.0},
    "BM": {"ph": 4.4, "sand": 82.0},
    "LM": {"ph": 5.0, "sand": 65.0},
    "L": {"ph": 5.8, "sand": 45.0},
    "OL": {"ph": 5.5, "sand": 50.0},
    "LL": {"ph": 6.5, "sand": 40.0},
}

FERTILITY_PL = {"B": "bór", "BM": "bór mieszany", "LM": "las mieszany", "L": "las",
                "OL": "ols", "LL": "łęg"}
MOISTURE_PL = {"S": "suchy", "SW": "świeży", "W": "wilgotny", "B": "bagienny"}


@dataclass(frozen=True)
class SiteType:
    raw: str
    fertility: str | None      # B, BM, LM, L, OL, LL
    moisture: str | None       # S, SW, W, B
    mountain: bool

    def label_pl(self) -> str:
        parts = [FERTILITY_PL.get(self.fertility or "", "")]
        if self.moisture:
            parts.append(MOISTURE_PL[self.moisture])
        if self.mountain:
            parts.append("(wyżynny/górski)")
        return " ".join(p for p in parts if p) or self.raw


def parse_site_type(code: str | None) -> SiteType | None:
    if not code or not code.strip():
        return None
    raw = code.strip()
    # keep Ł distinct before normalizing (Lł = łęg)
    if raw.upper().startswith("LŁ"):
        return SiteType(raw, "LL", "W", False)
    c = normalize_code(raw).replace(" ", "")
    fert = None
    for prefix, name in (("OLJ", "OL"), ("OL", "OL"), ("BM", "BM"), ("LM", "LM"),
                         ("LL", "LL"), ("B", "B"), ("L", "L")):
        if c.startswith(prefix):
            fert = name
            rest = c[len(prefix):]
            break
    if fert is None:
        return None
    mountain = False
    for marker in ("WYZ", "G"):
        if rest.startswith(marker):
            mountain = True
            rest = rest[len(marker):]
    moisture = {"SW": "SW", "S": "S", "W": "W", "B": "B"}.get(rest)
    if fert == "OL" and moisture is None:
        moisture = "B"
    return SiteType(raw, fert, moisture, mountain)
