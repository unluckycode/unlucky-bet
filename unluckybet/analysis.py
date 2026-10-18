"""Statystyki lig: serie bez remisu, odsetek remisów, nakładanie się godzin meczów, test niezależności."""

import math
import threading
from collections import Counter, OrderedDict, defaultdict
from datetime import date, timedelta

from . import db
from .leagues import BY_CODE, LEAGUES

SEQUENTIAL_OK = 0.15
SEQUENTIAL_PARTIAL = 0.35

MAX_CACHED_LEAGUES = 8

# Pamięć podręczna unieważniana po każdym odświeżeniu danych (klucz = znacznik czasu odświeżenia).
_cache = {"key": None, "matches": OrderedDict(), "fixtures": None, "memo": {}}
_lock = threading.RLock()


def _check_key():
    key = db.get_meta("last_refresh")
    if _cache["key"] != key:
        _cache.update(key=key, matches=OrderedDict(), fixtures=None, memo={})


def invalidate():
    with _lock:
        _cache["key"] = object()


def memo(name, fn):
    with _lock:
        _check_key()
        if name not in _cache["memo"]:
            _cache["memo"][name] = fn()
        return _cache["memo"][name]


def matches(code):
    with _lock:
        _check_key()
        cached = _cache["matches"]
        if code in cached:
            cached.move_to_end(code)
            return cached[code]
        with db.session() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT season, date, time, home, away, hg, ag, res, odds_d_avg, odds_d_max, odds_d_b365 "
                "FROM matches WHERE league=? ORDER BY date, time, home", (code,)).fetchall()]
        cached[code] = rows
        while len(cached) > MAX_CACHED_LEAGUES:
            cached.popitem(last=False)
        return rows


def _fixtures():
    with _lock:
        _check_key()
        if _cache["fixtures"] is None:
            fx = defaultdict(list)
            with db.session() as conn:
                for r in conn.execute("SELECT * FROM fixtures ORDER BY league, date, time, home").fetchall():
                    fx[r["league"]].append(dict(r))
            _cache["fixtures"] = dict(fx)
        return _cache["fixtures"]


def kickoff_groups(rows):
    """Grupuje mecze rozgrywane o tej samej godzinie (ta sama data i godzina)."""
    groups = []
    for m in rows:
        k = (m["date"], m["time"])
        if groups and groups[-1][0] == k:
            groups[-1][1].append(m)
        else:
            groups.append((k, [m]))
    return groups


def next_fixtures(code):
    rows = matches(code)
    last = (rows[-1]["date"], rows[-1]["time"]) if rows else ("", "")
    played = {(m["date"], m["home"]) for m in rows[-60:]}
    upcoming = [f for f in _fixtures().get(code, [])
                if (f["date"], f["time"]) > last and (f["date"], f["home"]) not in played]
    return upcoming[:6]


def overlap_stats(rows):
    """Odsetek meczów, które mają tę samą datę i godzinę co inny mecz tej ligi."""
    timed = [m for m in rows if m["time"]]
    if not timed:
        return None
    seasons = sorted({m["season"] for m in timed})
    recent_seasons = set(seasons[-3:])
    recent = [m for m in timed if m["season"] in recent_seasons]
    last_season = seasons[-1]

    # Bez ostatnich kolejek: pomijamy ostatnie 7 dni każdego zakończonego sezonu.
    season_end = {}
    for m in recent:
        season_end[m["season"]] = max(season_end.get(m["season"], ""), m["date"])
    def in_final_rounds(m):
        if m["season"] == last_season:
            return False
        end = date.fromisoformat(season_end[m["season"]])
        return date.fromisoformat(m["date"]) > end - timedelta(days=7)

    def rate(sample):
        if not sample:
            return None
        c = Counter((m["date"], m["time"]) for m in sample)
        shared = sum(1 for m in sample if c[(m["date"], m["time"])] > 1)
        return shared / len(sample)

    c = Counter((m["date"], m["time"]) for m in recent)
    return {
        "rate": rate(recent),
        "rate_excl_final": rate([m for m in recent if not in_final_rounds(m)]),
        "rate_current": rate([m for m in recent if m["season"] == last_season]),
        "max_parallel": max(c.values()) if c else 0,
        "seasons": sorted(recent_seasons),
        "n": len(recent),
    }


def streak_runs(rows):
    """Zwraca listę zakończonych serii bez remisu (długości) oraz bieżącą serię."""
    runs, cur = [], 0
    for m in rows:
        if m["res"] == "D":
            runs.append(cur)
            cur = 0
        else:
            cur += 1
    return runs, cur


def longest_run(rows):
    best, cur, start, best_span = 0, 0, None, (None, None)
    for m in rows:
        if m["res"] == "D":
            cur = 0
            start = None
        else:
            if cur == 0:
                start = m["date"]
            cur += 1
            if cur > best:
                best, best_span = cur, (start, m["date"])
    return best, best_span


def conditional_draws(rows, max_x=12):
    """P(remis | seria bez remisu przed meczem >= X). Mecze o tej samej godzinie dzielą stan serii."""
    counts = [[0, 0] for _ in range(max_x + 1)]  # [mecze, remisy]
    streak = 0
    for _, group in kickoff_groups(rows):
        for m in group:
            d = m["res"] == "D"
            for x in range(0, min(streak, max_x) + 1):
                counts[x][0] += 1
                counts[x][1] += d
        for m in group:
            streak = 0 if m["res"] == "D" else streak + 1
    return counts


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def z_score(k, n, p):
    if n == 0 or p <= 0 or p >= 1:
        return None
    return (k - n * p) / math.sqrt(n * p * (1 - p))


def fit_label(rate):
    if rate is None:
        return ("brak godzin", "muted")
    if rate <= SEQUENTIAL_OK:
        return ("pasuje", "good")
    if rate <= SEQUENTIAL_PARTIAL:
        return ("częściowo", "warn")
    return ("nie pasuje", "bad")


def league_summary(code):
    rows = matches(code)
    lg = BY_CODE[code]
    if not rows:
        return {"code": code, "league": lg, "n": 0}
    draws = sum(1 for m in rows if m["res"] == "D")
    runs, cur = streak_runs(rows)
    longest, span = longest_run(rows)
    ov = overlap_stats(rows)
    fx = next_fixtures(code)
    last_draw = next((m for m in reversed(rows) if m["res"] == "D"), None)
    ov_rate = ov["rate_excl_final"] if ov else None
    label, tone = fit_label(ov_rate)
    p = draws / len(rows)
    return {
        "code": code,
        "league": lg,
        "n": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "draws": draws,
        "draw_rate": p,
        "current_streak": cur,
        "longest": longest,
        "longest_span": span,
        "p_longest_now": (1 - p) ** cur if cur else 1.0,
        "overlap": ov,
        "overlap_rate": ov_rate,
        "fit": label,
        "fit_tone": tone,
        "next": fx,
        "last_draw": last_draw,
        "avg_draw_odds": _avg([m["odds_d_avg"] for m in rows[-500:]]),
        "stale": rows[-1]["date"] < (date.today() - timedelta(days=30)).isoformat() and not fx,
    }


def _avg(values):
    vals = [v for v in values if v]
    return sum(vals) / len(vals) if vals else None


def all_summaries():
    return memo("summaries", lambda: [s for s in (league_summary(lg.code) for lg in LEAGUES) if s["n"]])


def summary(code):
    return next((s for s in all_summaries() if s["code"] == code), None) or league_summary(code)


def run_length_distribution(rows, max_len=20):
    """Rozkład długości serii bez remisu vs. oczekiwany rozkład geometryczny."""
    runs, _ = streak_runs(rows)
    if not runs:
        return []
    p = sum(1 for m in rows if m["res"] == "D") / len(rows)
    c = Counter(min(r, max_len) for r in runs)
    out = []
    for k in range(0, max_len + 1):
        expected = p * (1 - p) ** k if k < max_len else (1 - p) ** max_len
        out.append({"len": k, "observed": c.get(k, 0), "expected": expected * len(runs)})
    return out


def independence_table(codes=None, max_x=12):
    """Zbiorczy test: czy P(remis | seria >= X) różni się od bazowego odsetka remisów w lidze."""
    key = "indep:" + ",".join(codes or []) + f":{max_x}"
    return memo(key, lambda: _independence_table(codes, max_x))


def _independence_table(codes, max_x):
    codes = codes or [lg.code for lg in LEAGUES]
    agg = [[0, 0, 0.0, 0.0] for _ in range(max_x + 1)]  # n, k, oczekiwane k, wariancja
    for code in codes:
        rows = matches(code)
        if not rows:
            continue
        p = sum(1 for m in rows if m["res"] == "D") / len(rows)
        for x, (n, k) in enumerate(conditional_draws(rows, max_x)):
            agg[x][0] += n
            agg[x][1] += k
            agg[x][2] += n * p
            agg[x][3] += n * p * (1 - p)
    out = []
    for x, (n, k, e, var) in enumerate(agg):
        if n == 0:
            continue
        lo, hi = wilson(k, n)
        out.append({
            "x": x, "n": n, "draws": k, "rate": k / n, "expected": e / n,
            "lo": lo, "hi": hi, "z": (k - e) / math.sqrt(var) if var else None,
        })
    return out


def league_conditional(code, max_x=12):
    rows = matches(code)
    if not rows:
        return []
    p = sum(1 for m in rows if m["res"] == "D") / len(rows)
    out = []
    for x, (n, k) in enumerate(conditional_draws(rows, max_x)):
        if n == 0:
            continue
        lo, hi = wilson(k, n)
        out.append({"x": x, "n": n, "draws": k, "rate": k / n, "expected": p,
                    "lo": lo, "hi": hi, "z": z_score(k, n, p)})
    return out
