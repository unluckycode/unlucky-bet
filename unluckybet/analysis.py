"""Statystyki lig: serie bez remisu, odsetek remisów, nakładanie się godzin meczów, test niezależności.

Seria = kolejne mecze całej ligi (wszystkie drużyny) uporządkowane po dokładnej godzinie
rozpoczęcia (kickoff). Mecze o tej samej godzinie dzielą stan serii: remis w którymkolwiek
ją zeruje. Wyniki na żywo pochodzą z FotMob; football-data uzupełnia starszą historię i kursy.
"""

import math
import threading
from collections import Counter, OrderedDict, defaultdict
from datetime import date, timedelta

from . import db
from .leagues import BY_CODE, LEAGUES
from .markets import get_market

SEQUENTIAL_OK = 0.10
SEQUENTIAL_PARTIAL = 0.20

MAX_CACHED_LEAGUES = 24

_cache = {"key": None, "matches": OrderedDict(), "fixtures": None, "memo": {}}
_lock = threading.RLock()


def _check_key():
    key = (db.get_meta("last_refresh"), db.get_meta("live_refresh"))
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


def _sort_key(m):
    return (m.get("kickoff_utc") or f"{m['date']}T{m.get('time') or '00:00'}:00Z",
            m["date"], m.get("time") or "", m["home"])


def matches(code):
    """Zakończone mecze ligi chronologicznie: FotMob (świeże) + starsze football-data."""
    with _lock:
        _check_key()
        cached = _cache["matches"]
        if code in cached:
            cached.move_to_end(code)
            return cached[code]
        with db.session() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT season, date, time, home, away, hg, ag, res, odds_d_avg, odds_d_max, odds_d_b365, "
                "kickoff_utc, event_id, source "
                "FROM matches WHERE league=? AND res IS NOT NULL AND res != ''", (code,)).fetchall()]
        # Gdy jest FotMob – seria i „następny mecz” wyłącznie z niego (spójny czas UTC→PL).
        # football-data zostaje w tabeli pod kursy/backtest (analysis.matches_history).
        fm = [m for m in rows if m.get("source") == "fotmob"]
        rows = sorted(fm or rows, key=_sort_key)
        cached[code] = rows
        while len(cached) > MAX_CACHED_LEAGUES:
            cached.popitem(last=False)
        return rows


def matches_history(code):
    """Historia do backtestu: football-data (kursy) + FotMob dla brakujących meczów."""
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT season, date, time, home, away, hg, ag, res, odds_d_avg, odds_d_max, odds_d_b365, "
            "kickoff_utc, event_id, source "
            "FROM matches WHERE league=? AND res IS NOT NULL AND res != ''", (code,)).fetchall()]
    fm = [m for m in rows if m.get("source") == "fotmob"]
    fd = [m for m in rows if m.get("source") != "fotmob"]
    if not fm:
        return sorted(fd, key=_sort_key)
    first = min(m["kickoff_utc"] for m in fm if m.get("kickoff_utc")) if any(m.get("kickoff_utc") for m in fm) else ""
    older = [m for m in fd if (m.get("kickoff_utc") or f"{m['date']}T00:00:00Z") < first]
    return sorted(older + fm, key=_sort_key)


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
    """Grupuje mecze o tej samej godzinie rozpoczęcia (kickoff_utc albo date+time)."""
    groups = []
    for m in rows:
        k = m.get("kickoff_utc") or (m["date"], m.get("time") or "")
        if groups and groups[-1][0] == k:
            groups[-1][1].append(m)
        else:
            groups.append((k, [m]))
    return groups


def advance(streak, group, hit_fn=None):
    """Seria po slotcie godzinowym: trafienie rynku w którymkolwiek meczu zeruje serię."""
    if hit_fn is None:
        hit_fn = lambda m: m.get("res") == "D"  # noqa: E731 – domyślnie remis
    return 0 if any(hit_fn(m) for m in group) else streak + len(group)


def with_streaks(rows, market="draw", side=None):
    mk = get_market(market)
    side = mk.normalize_side(side)
    hit = lambda m: mk.hit(m, side)  # noqa: E731
    out, streak = [], 0
    for _, group in kickoff_groups(rows):
        streak = advance(streak, group, hit)
        out += [{**m, "streak": streak} for m in group]
    return out


def next_fixtures(code, limit=6):
    rows = matches(code)
    last_k = _sort_key(rows[-1]) if rows else ("", "", "", "")
    played = {(m["date"], m["home"], m["away"]) for m in rows[-80:]}
    upcoming = []
    for f in _fixtures().get(code, []):
        if (f["date"], f["home"], f["away"]) in played:
            continue
        if _sort_key(f) <= last_k and f.get("status") != "playing":
            continue
        upcoming.append(f)
    upcoming.sort(key=_sort_key)
    return upcoming[:limit]


def overlap_stats(rows):
    timed = [m for m in rows if m.get("kickoff_utc") or m.get("time")]
    if not timed:
        return None
    seasons = sorted({m["season"] for m in timed if m.get("season")})
    recent_seasons = set(seasons[-3:]) if seasons else set()
    recent = [m for m in timed if not seasons or m.get("season") in recent_seasons]
    last_season = seasons[-1] if seasons else None

    season_end = {}
    for m in recent:
        season_end[m["season"]] = max(season_end.get(m["season"], ""), m["date"])

    def in_final_rounds(m):
        if not last_season or m["season"] == last_season:
            return False
        end = date.fromisoformat(season_end[m["season"]])
        return date.fromisoformat(m["date"]) > end - timedelta(days=7)

    def rate(sample):
        if not sample:
            return None
        keys = [m.get("kickoff_utc") or (m["date"], m.get("time")) for m in sample]
        c = Counter(keys)
        shared = sum(1 for k in keys if c[k] > 1)
        return shared / len(sample)

    keys = [m.get("kickoff_utc") or (m["date"], m.get("time")) for m in recent]
    c = Counter(keys)
    return {
        "rate": rate(recent),
        "rate_excl_final": rate([m for m in recent if not in_final_rounds(m)]),
        "rate_current": rate([m for m in recent if m.get("season") == last_season]),
        "max_parallel": max(c.values()) if c else 0,
        "seasons": sorted(recent_seasons),
        "n": len(recent),
    }


def streak_runs(rows, market="draw", side=None):
    """Zakończone serie bez zdarzenia rynku + bieżąca seria (sloty godzinowe)."""
    mk = get_market(market)
    side = mk.normalize_side(side)
    hit = lambda m: mk.hit(m, side)  # noqa: E731
    runs, cur = [], 0
    for _, group in kickoff_groups(rows):
        hits = sum(1 for m in group if hit(m))
        if hits:
            runs += [cur] + [0] * (hits - 1)
            cur = 0
        else:
            cur += len(group)
    return runs, cur


def longest_run(rows, market="draw", side=None):
    mk = get_market(market)
    side = mk.normalize_side(side)
    hit = lambda m: mk.hit(m, side)  # noqa: E731
    best, cur, start, best_span = 0, 0, None, (None, None)
    for key, group in kickoff_groups(rows):
        if any(hit(m) for m in group):
            cur, start = 0, None
            continue
        d = group[0]["date"]
        if cur == 0:
            start = d
        cur += len(group)
        if cur > best:
            best, best_span = cur, (start, d)
    return best, best_span


def conditional_draws(rows, max_x=12, market="draw", side=None):
    """P(trafienie | seria bez trafienia przed meczem >= X)."""
    mk = get_market(market)
    side = mk.normalize_side(side)
    hit = lambda m: mk.hit(m, side)  # noqa: E731
    counts = [[0, 0] for _ in range(max_x + 1)]
    streak = 0
    for _, group in kickoff_groups(rows):
        for m in group:
            h = hit(m)
            for x in range(0, min(streak, max_x) + 1):
                counts[x][0] += 1
                counts[x][1] += h
        streak = advance(streak, group, hit)
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


def league_summary(code, market="draw", side=None):
    mk = get_market(market)
    side = mk.normalize_side(side)
    rows = matches(code)
    lg = BY_CODE[code]
    catalog_fit = lg.fit
    catalog_tone = {"pasuje": "good", "częściowo": "warn", "nie": "bad"}.get(catalog_fit, "muted")
    if not rows:
        return {
            "code": code, "league": lg, "n": 0, "market": mk.key, "side": side,
            "fit": catalog_fit if catalog_fit != "nie" else "nie pasuje",
            "fit_tone": catalog_tone if catalog_fit != "nie" else "bad",
            "overlap_rate": lg.overlap, "current_streak": 0, "next": [], "stale": True,
            "draw_rate": 0, "hit_rate": 0, "hits": 0, "draws": 0, "longest": 0,
            "longest_span": (None, None), "avg_draw_odds": None, "last_date": None,
            "last": None, "live_added": 0, "last_hit": None,
        }
    hits = sum(1 for m in rows if mk.hit(m, side))
    runs, cur = streak_runs(rows, mk.key, side)
    longest, span = longest_run(rows, mk.key, side)
    ov = overlap_stats(rows)
    fx = next_fixtures(code)
    last_hit = next((m for m in reversed(rows) if mk.hit(m, side)), None)
    ov_rate = ov["rate_excl_final"] if ov else lg.overlap
    if ov and ov["rate_excl_final"] is not None:
        label, tone = fit_label(ov_rate)
    else:
        label = {"pasuje": "pasuje", "częściowo": "częściowo", "nie": "nie pasuje"}[catalog_fit]
        tone = catalog_tone if catalog_fit != "nie" else "bad"
        if catalog_fit == "nie":
            label = "nie pasuje"
    p = hits / len(rows)
    return {
        "code": code,
        "league": lg,
        "market": mk.key,
        "side": side,
        "n": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "last": rows[-1],
        "live_added": sum(1 for m in rows[-80:] if m.get("source") == "fotmob"),
        "hits": hits,
        "hit_rate": p,
        "draws": hits if mk.key == "draw" else sum(1 for m in rows if m["res"] == "D"),
        "draw_rate": p if mk.key == "draw" else sum(1 for m in rows if m["res"] == "D") / len(rows),
        "current_streak": cur,
        "longest": longest,
        "longest_span": span,
        "p_longest_now": (1 - p) ** cur if cur else 1.0,
        "overlap": ov,
        "overlap_rate": ov_rate,
        "fit": label,
        "fit_tone": tone,
        "next": fx,
        "last_hit": last_hit,
        "last_draw": last_hit if mk.key == "draw" else next((m for m in reversed(rows) if m["res"] == "D"), None),
        "avg_draw_odds": _avg([m["odds_d_avg"] for m in rows[-500:]]),
        "stale": rows[-1]["date"] < (date.today() - timedelta(days=30)).isoformat() and not fx,
    }


def _avg(values):
    vals = [v for v in values if v]
    return sum(vals) / len(vals) if vals else None


def all_summaries(market="draw", side=None):
    mk = get_market(market)
    side = mk.normalize_side(side)
    key = f"summaries:{mk.key}:{side}"
    return memo(key, lambda: [league_summary(lg.code, mk.key, side) for lg in LEAGUES])


def summary(code, market="draw", side=None):
    rows = all_summaries(market, side)
    return next((s for s in rows if s["code"] == code), None) or league_summary(code, market, side)


def recommendations(market="draw", side=None, threshold=None, limit=8):
    """Top lig do obserwacji: pasujące (fit) z najdłuższą serią ≥ X, potem score dopasowania."""
    mk = get_market(market)
    side = mk.normalize_side(side)
    x = int(threshold if threshold is not None else mk.default_threshold)
    rows = [s for s in all_summaries(mk.key, side) if s.get("n") and s.get("fit_tone") == "good"]
    above = [s for s in rows if s["current_streak"] >= x]
    above.sort(key=lambda s: (-s["current_streak"], -(s.get("hit_rate") or 0), s.get("overlap_rate") or 1))
    rest = [s for s in rows if s["current_streak"] < x]
    rest.sort(key=lambda s: (-s["current_streak"], s.get("overlap_rate") or 1, -(s.get("hit_rate") or 0)))
    out = above + rest
    for s in out:
        s["rec_reason"] = (
            f"Seria {s['current_streak']} ≥ X={x}" if s["current_streak"] >= x
            else f"Pasuje (nakładanie {(s['overlap_rate'] or 0)*100:.0f}%), seria {s['current_streak']}"
        )
        s["rec_alert"] = s["current_streak"] >= x
    return out[:limit]


def run_length_distribution(rows, max_len=20):
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
    key = "indep:" + ",".join(codes or []) + f":{max_x}"
    return memo(key, lambda: _independence_table(codes, max_x))


def _independence_table(codes, max_x):
    codes = codes or [lg.code for lg in LEAGUES if lg.fit == "pasuje"]
    agg = [[0, 0, 0.0, 0.0] for _ in range(max_x + 1)]
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
