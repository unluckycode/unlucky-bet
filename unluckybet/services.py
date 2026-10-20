"""Logika aplikacji współdzielona przez widoki, zadanie cykliczne i powiadomienia."""

import logging
import os
import threading
import time
from datetime import date, datetime

from . import analysis, db, ingest, live, strategy
from .leagues import FITTING
from .markets import MARKET_ORDER, get_market

log = logging.getLogger(__name__)

REFRESH_INTERVAL_MIN = int(os.environ.get("REFRESH_INTERVAL_MIN", "360"))
LIVE_REFRESH_MIN = live.LIVE_REFRESH_MIN

DEFAULT_STRATEGY = {
    "watched": 1, "active": 0, "threshold": 5, "base_stake": 10.0, "multiplier": 2.0,
    "max_steps": 8, "bankroll": 0.0, "odds_mode": "avg", "fixed_odds": 3.2, "tax": 0.12,
    "start_date": "", "side": "",
}

_refresh_lock = threading.Lock()
_refresh_state = {"running": False, "started": None, "log": [], "kind": ""}


def default_for(market):
    mk = get_market(market)
    return {
        **DEFAULT_STRATEGY,
        "market": mk.key,
        "side": mk.default_side,
        "threshold": mk.default_threshold,
        "fixed_odds": mk.default_odds,
        "odds_mode": "avg" if mk.odds_keys else "fixed",
    }


def get_strategy(code, market="draw"):
    mk = get_market(market)
    with db.session() as conn:
        row = conn.execute(
            "SELECT * FROM strategies WHERE league=? AND market=?", (code, mk.key)
        ).fetchone()
    return dict(row) if row else None


def all_strategies(market=None):
    """Gdy market podany – dict[league]=row; inaczej dict[(league,market)]=row."""
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM strategies").fetchall()]
    if market is None:
        return {(r["league"], r.get("market") or "draw"): r for r in rows}
    mk = get_market(market)
    return {r["league"]: r for r in rows if (r.get("market") or "draw") == mk.key}


def save_strategy(code, values, market="draw"):
    mk = get_market(market)
    current = get_strategy(code, mk.key) or {**default_for(mk.key), "league": code}
    current.update(values)
    current["league"] = code
    current["market"] = mk.key
    current["side"] = mk.normalize_side(current.get("side"))
    cols = ["league", "market", "side", "watched", "active", "threshold", "base_stake", "multiplier",
            "max_steps", "bankroll", "odds_mode", "fixed_odds", "tax", "start_date"]
    with db.session() as conn:
        conn.execute(
            f"INSERT INTO strategies({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
            "ON CONFLICT(league, market) DO UPDATE SET "
            + ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("league", "market")),
            [current[c] for c in cols],
        )
    return current


def live_state(st):
    market = st.get("market") or "draw"
    side = st.get("side")
    rows = analysis.matches(st["league"])
    p = strategy.Params.from_row(st)
    start = st.get("start_date") or date.today().isoformat()
    before = [m for m in rows if m["date"] < start]
    after = [m for m in rows if m["date"] >= start]
    _, initial = analysis.streak_runs(before, market, side)
    res = strategy.run(after, p, initial_streak=initial)
    action = strategy.next_action(res, p)
    return {"params": p, "result": res, "action": action, "start": start}


def refresh_running():
    return _refresh_state["running"]


def refresh_status():
    return dict(_refresh_state, log=list(_refresh_state["log"][-12:]))


def _do_refresh(full=False, kind="live"):
    if not _refresh_lock.acquire(blocking=False):
        return False
    _refresh_state.update(running=True, started=datetime.now().strftime("%H:%M:%S"), log=[], kind=kind)
    try:
        ensure_default_watches()
        if kind in ("live", "all"):
            live.refresh(log_fn=lambda msg: _refresh_state["log"].append(msg))
        if kind in ("history", "all") or full:
            from .leagues import LEAGUES
            fd = [lg.code for lg in LEAGUES if lg.fd_code]
            ingest.refresh(full=full, log=lambda msg: _refresh_state["log"].append(msg), leagues=fd)
        analysis.invalidate()
        from . import notify
        result = notify.check_and_notify()
        _refresh_state["log"].append(f"Powiadomienia: {result['alerts']} zdarzeń, wysłano {result['pushes']}")
    except Exception as err:  # noqa: BLE001
        log.exception("Odświeżanie nie powiodło się")
        _refresh_state["log"].append(f"BŁĄD: {err}")
    finally:
        _refresh_state["running"] = False
        _refresh_lock.release()
    return True


def refresh_async(full=False, kind="live"):
    if refresh_running():
        return False
    threading.Thread(target=_do_refresh, kwargs={"full": full, "kind": kind}, daemon=True).start()
    return True


def refresh_due():
    return live.live_refresh_due()


def has_data():
    with db.session() as conn:
        return conn.execute("SELECT 1 FROM matches WHERE source='fotmob' LIMIT 1").fetchone() is not None


def ensure_default_watches():
    """Dla każdej z 27 pasujących lig – wiersz strategii w każdym rynku (jeśli brak)."""
    added = 0
    with db.session() as conn:
        existing = {(r["league"], (r["market"] if "market" in r.keys() and r["market"] else "draw"))
                    for r in conn.execute("SELECT league, market FROM strategies").fetchall()}
        for lg in FITTING:
            for mkey in MARKET_ORDER:
                if (lg.code, mkey) in existing:
                    continue
                d = default_for(mkey)
                conn.execute(
                    "INSERT INTO strategies(league, market, side, watched, active, threshold, base_stake, "
                    "multiplier, max_steps, bankroll, odds_mode, fixed_odds, tax, start_date) "
                    "VALUES(?,?,?,?,0,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (lg.code, mkey, d["side"], 1, d["threshold"], d["base_stake"], d["multiplier"],
                     d["max_steps"], d["bankroll"], d["odds_mode"], d["fixed_odds"], d["tax"], ""),
                )
                added += 1
    return added


# Kompatybilność: live.ensure_default_watches woła starszą wersję – nadpiszemy w live.py
def start_background_scheduler():
    def loop():
        time.sleep(5)
        try:
            ensure_default_watches()
            if not has_data():
                _do_refresh(kind="live")
        except Exception:  # noqa: BLE001
            log.exception("Pierwsze odświeżanie")
        while True:
            try:
                if live.live_refresh_due():
                    _do_refresh(kind="live")
            except Exception:  # noqa: BLE001
                log.exception("Błąd harmonogramu")
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="scheduler").start()
