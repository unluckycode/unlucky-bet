"""Rynki strategii: remis, Over/Under 2.5, BTTS.

Każdy rynek definiuje:
  • hit(m) – czy zdarzenie „wygrywające zakład” wystąpiło w meczu,
  • serię czekania = kolejne mecze bez tego zdarzenia (po kickoffie, sloty godzinowe),
  • domyślną stronę (side) i etykiety PL.
"""

from __future__ import annotations

from dataclasses import dataclass


def goals(m):
    hg, ag = m.get("hg"), m.get("ag")
    if hg is None or ag is None:
        return None
    return int(hg) + int(ag)


def is_over25(m):
    g = goals(m)
    return g is not None and g >= 3


def is_under25(m):
    g = goals(m)
    return g is not None and g <= 2


def is_btts_yes(m):
    hg, ag = m.get("hg"), m.get("ag")
    return hg is not None and ag is not None and int(hg) > 0 and int(ag) > 0


def is_btts_no(m):
    hg, ag = m.get("hg"), m.get("ag")
    return hg is not None and ag is not None and (int(hg) == 0 or int(ag) == 0)


def is_draw(m):
    return m.get("res") == "D"


@dataclass(frozen=True)
class Market:
    key: str
    name: str                 # krótka nazwa w nawigacji
    title: str                # nagłówek pulpitu
    blurb: str                # jedno zdanie pod nagłówkiem
    default_side: str
    sides: tuple              # dozwolone strony
    side_labels: dict         # side -> etykieta przycisku
    streak_labels: dict       # side -> „seria bez …”
    bet_labels: dict          # side -> „stawiamy na …”
    default_odds: float
    default_threshold: int
    odds_keys: dict           # odds_mode -> klucz w meczu (puste = tylko fixed)

    def normalize_side(self, side):
        s = (side or self.default_side).lower()
        return s if s in self.sides else self.default_side

    def hit(self, m, side=None):
        side = self.normalize_side(side)
        return _HIT[self.key][side](m)

    def streak_label(self, side=None):
        return self.streak_labels[self.normalize_side(side)]

    def bet_label(self, side=None):
        return self.bet_labels[self.normalize_side(side)]


_HIT = {
    "draw": {"draw": is_draw},
    "ou25": {"over": is_over25, "under": is_under25},
    "btts": {"yes": is_btts_yes, "no": is_btts_no},
}

MARKETS = {
    "draw": Market(
        key="draw",
        name="Remisy",
        title="Pulpit – remisy",
        blurb="Po X meczach ligi bez remisu stawiamy na remis (martingale).",
        default_side="draw",
        sides=("draw",),
        side_labels={"draw": "Remis"},
        streak_labels={"draw": "meczów bez remisu"},
        bet_labels={"draw": "remis"},
        default_odds=3.2,
        default_threshold=5,
        odds_keys={"avg": "odds_d_avg", "max": "odds_d_max", "b365": "odds_d_b365"},
    ),
    "ou25": Market(
        key="ou25",
        name="Over/Under",
        title="Pulpit – Over/Under 2.5",
        blurb="Domyślnie: po serii meczów bez Over 2.5 stawiamy na Over 2.5. Możesz odwrócić stronę.",
        default_side="over",
        sides=("over", "under"),
        side_labels={"over": "Over 2.5", "under": "Under 2.5"},
        streak_labels={
            "over": "meczów bez Over 2.5 (≤2 goli)",
            "under": "meczów bez Under 2.5 (≥3 goli)",
        },
        bet_labels={"over": "Over 2.5", "under": "Under 2.5"},
        default_odds=1.90,
        default_threshold=4,
        odds_keys={},
    ),
    "btts": Market(
        key="btts",
        name="BTTS",
        title="Pulpit – BTTS",
        blurb="Domyślnie: po serii meczów bez BTTS (obie strzelą) stawiamy na BTTS Tak.",
        default_side="yes",
        sides=("yes", "no"),
        side_labels={"yes": "BTTS Tak", "no": "BTTS Nie"},
        streak_labels={
            "yes": "meczów bez BTTS (obie strzelą)",
            "no": "meczów bez BTTS Nie (czyli z BTTS)",
        },
        bet_labels={"yes": "BTTS Tak", "no": "BTTS Nie"},
        default_odds=1.85,
        default_threshold=4,
        odds_keys={},
    ),
}

MARKET_ORDER = ("draw", "ou25", "btts")


def get_market(key):
    return MARKETS.get(key or "draw") or MARKETS["draw"]
