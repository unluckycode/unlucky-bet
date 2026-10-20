"""Katalog lig: 168 lig krajowych z FotMob + opcjonalne mapowanie na football-data.co.uk.

Kod ligi:
  • znane ligi z football-data zachowują stare kody (POL, ROU, E0…) – strategie w Neon
    i historia kursów działają bez migracji;
  • pozostałe: F{fotmob_id} (np. F337).

Źródło wyników/terminarza na żywo: FotMob (`fotmob_id`). football-data służy do kursów
i długiej historii w backteście.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent / "catalog" / "ligi-swiat.json"

# fotmob_id -> kod football-data.co.uk (gdy liga jest w CSV)
FOTMOB_TO_FD = {
    47: "E0", 48: "E1", 108: "E2", 109: "E3", 117: "EC",
    64: "SC0", 123: "SC1", 124: "SC2", 125: "SC3",
    54: "D1", 146: "D2",
    55: "I1", 86: "I2",
    87: "SP1", 140: "SP2",
    53: "F1", 110: "F2",
    57: "N1", 40: "B1", 61: "P1", 71: "T1", 135: "G1",
    112: "ARG", 38: "AUT", 268: "BRA", 120: "CHN",
    46: "DNK", 51: "FIN", 126: "IRL", 223: "JPN",
    230: "MEX", 59: "NOR", 196: "POL", 189: "ROU",
    63: "RUS", 67: "SWE", 69: "SWZ", 130: "USA",
}

FD_MAIN = {
    "E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "I1", "I2", "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1",
}
FD_EXTRA = {
    "ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN", "MEX", "NOR",
    "POL", "ROU", "RUS", "SWE", "SWZ", "USA",
}
FD_CODES = FD_MAIN | FD_EXTRA


@dataclass(frozen=True)
class League:
    code: str
    name: str
    country: str
    fotmob_id: int
    fit: str = "nie"          # pasuje / częściowo / nie
    overlap: float | None = None
    continent: str = ""
    tier_order: int = 1
    fd_code: str = ""
    name_en: str = ""
    ccode: str = ""
    active: bool = True

    @property
    def source(self):
        """'main'/'extra' = football-data CSV; 'fotmob' = tylko FotMob."""
        if self.fd_code in FD_MAIN:
            return "main"
        if self.fd_code in FD_EXTRA:
            return "extra"
        return "fotmob"

    @property
    def watched_default(self):
        return self.fit == "pasuje"


def _build():
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    leagues = []
    used = set()
    for row in cat["leagues"]:
        fid = int(row["fotmob_id"])
        fd = FOTMOB_TO_FD.get(fid, "")
        if fd not in FD_CODES:
            fd = ""
        code = fd if fd and fd not in used else f"F{fid}"
        used.add(code)
        name_pl = row["name_pl"]
        short = name_pl.split(" – ", 1)[1] if " – " in name_pl else row["name"]
        leagues.append(League(
            code=code,
            name=short,
            country=row["country_pl"],
            fotmob_id=fid,
            fit=row.get("fit") or "nie",
            overlap=row.get("overlap"),
            continent=row.get("continent_pl") or "",
            tier_order=int(row.get("tier_order") or 1),
            fd_code=fd,
            name_en=row["name"],
            ccode=row.get("ccode") or "",
            active=bool(row.get("active", True)),
        ))
    fit_rank = {"pasuje": 0, "częściowo": 1, "nie": 2}
    leagues.sort(key=lambda lg: (
        fit_rank.get(lg.fit, 9),
        lg.overlap if lg.overlap is not None else 9,
        lg.country, lg.tier_order, lg.name,
    ))
    return leagues, cat.get("generated_utc")


LEAGUES, CATALOG_GENERATED = _build()
BY_CODE = {lg.code: lg for lg in LEAGUES}
BY_FOTMOB = {lg.fotmob_id: lg for lg in LEAGUES}
FITTING = [lg for lg in LEAGUES if lg.fit == "pasuje"]

EXTRA_COUNTRY_TO_CODE = {
    "Argentina": "ARG", "Austria": "AUT", "Brazil": "BRA", "China": "CHN",
    "Denmark": "DNK", "Finland": "FIN", "Ireland": "IRL", "Japan": "JPN",
    "Mexico": "MEX", "Norway": "NOR", "Poland": "POL", "Romania": "ROU",
    "Russia": "RUS", "Sweden": "SWE", "Switzerland": "SWZ", "USA": "USA",
}
