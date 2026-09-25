"""Polish forestry tree species codes (BDL / SILP) -> genus."""
from __future__ import annotations

import re
import unicodedata

# prefix of normalized code -> genus
CODE_TO_GENUS: dict[str, str] = {
    "SO": "Pinus", "KOS": "Pinus", "LIM": "Pinus",
    "SW": "Picea",
    "JD": "Abies",
    "MD": "Larix",
    "DG": "Pseudotsuga",
    "CIS": "Taxus", "JAL": "Juniperus", "ZYW": "Thuja",
    "BK": "Fagus",
    "DB": "Quercus",
    "GB": "Carpinus",
    "BRZ": "Betula", "BR": "Betula",
    "OL": "Alnus",
    "OS": "Populus", "TP": "Populus",
    "JS": "Fraxinus",
    "KL": "Acer", "JW": "Acer",
    "LP": "Tilia",
    "WZ": "Ulmus", "WIA": "Ulmus", "WZ.S": "Ulmus",
    "WB": "Salix", "IW": "Salix", "WI": "Salix",
    "AK": "Robinia", "ROB": "Robinia",
    "CZR": "Prunus", "CZM": "Prunus", "CZ": "Prunus",
    "JRZ": "Sorbus", "JAR": "Sorbus", "BRE": "Sorbus",
    "KSZ": "Castanea", "KAS": "Castanea",
    "GR": "Pyrus", "JB": "Malus",
    "LSZ": "Corylus", "LESZ": "Corylus",
}

GENUS_PL = {
    "Pinus": "sosna", "Picea": "świerk", "Abies": "jodła", "Larix": "modrzew",
    "Pseudotsuga": "daglezja", "Fagus": "buk", "Quercus": "dąb", "Carpinus": "grab",
    "Betula": "brzoza", "Alnus": "olsza", "Populus": "topola/osika", "Fraxinus": "jesion",
    "Acer": "klon/jawor", "Tilia": "lipa", "Ulmus": "wiąz", "Salix": "wierzba",
    "Robinia": "robinia", "Prunus": "czeremcha/czereśnia", "Sorbus": "jarząb",
    "Castanea": "kasztan jadalny", "Taxus": "cis", "Juniperus": "jałowiec",
    "Thuja": "żywotnik", "Pyrus": "grusza", "Malus": "jabłoń", "Corylus": "leszczyna",
}


def normalize_code(code: str) -> str:
    s = unicodedata.normalize("NFKD", code.strip().upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("Ł", "L")


def genus_for_code(code: str | None) -> str | None:
    if not code:
        return None
    c = normalize_code(code)
    if not c:
        return None
    base = re.split(r"[.\s/_-]", c)[0]
    for key in sorted(CODE_TO_GENUS, key=len, reverse=True):
        if base == key or c == key:
            return CODE_TO_GENUS[key]
    for key in sorted(CODE_TO_GENUS, key=len, reverse=True):
        if base.startswith(key):
            return CODE_TO_GENUS[key]
    return None


_COMPOSITION_RE = re.compile(r"(\d{1,2})\s*([A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]{2,4}(?:\.[A-Za-z]{1,3})?)")


def parse_composition(text: str | None) -> list[tuple[str, float]]:
    """Parse a 'skład gatunkowy' string like '6SO 3BRZ 1DB' -> [(genus, share)]."""
    if not text:
        return []
    out: dict[str, float] = {}
    for num, code in _COMPOSITION_RE.findall(text):
        genus = genus_for_code(code)
        if genus is None:
            continue
        out[genus] = out.get(genus, 0.0) + int(num) / 10.0
    total = sum(out.values())
    if total <= 0 or total > 1.05:
        return []
    return list(out.items())
