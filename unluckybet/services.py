"""Logika aplikacji współdzielona przez widoki, zadanie cykliczne i powiadomienia."""

import logging
import os
import threading
import time
from datetime import date, datetime

from . import analysis, db, ingest, strategy

log = logging.getLogger(__name__)

REFRESH_INTERVAL_MIN = int(os.environ.get("REFRESH_INTERVAL_MIN", "60"))

DEFAULT_STRATEGY = {
    "watched": 1, "active": 0, "threshold": 5, "base_stake": 10.0, "multiplier": 2.0,
    "max_steps": 8, "bankroll": 0.0, "odds_mode": "avg", "fixed_odds": 3.2, "tax": 0.12, "start_date": "",
}

_refresh_lock = threading.Lock()
_refresh_state = {"running": False, "started": None, "log": []}


def get_strategy(code):
    with db.session() as conn:
        row = conn.execute("SELECT * FROM strategies WHERE league=?", (code,)).fetchone()
    return dict(row) if row else None


def all_strategies():
    with db.session() as conn:
        return {r["league"]: dict(r) for r in conn.execute("SELECT * FROM strategies").fetchall()}


def save_strategy(code, values):
    current = get_strategy(code) or {**DEFAULT_STRATEGY, "league": code}
    current.update(values)
    current["league"] = code
    cols = ["league", "watched", "active", "threshold", "base_stake", "multiplier", "max_steps",
            "bankroll", "odds_mode", "fixed_odds", "tax", "start_date"]
    with db.session() as conn:
        conn.execute(
            f"INSERT INTO strategies({','.join(cols)}) VALUES({','.join('?' * len(cols))}) "
            "ON CONFLICT(league) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in cols[1:]),
            [current[c] for c in cols],
        )
    return current


def live_state(st):
    """Stan strategii "na żywo" (paper trading) od daty aktywacji na rzeczywistych wynikach."""
    rows = analysis.matches(st["league"])
    p = strategy.Params.from_row(st)
    start = st.get("start_date") or date.today().isoformat()
    before = [m for m in rows if m["date"] < start]
    after = [m for m in rows if m["date"] >= start]
    _, initial = analysis.streak_runs(before)
    res = strategy.run(after, p, initial_streak=initial)
    action = strategy.next_action(res, p)
    return {"params": p, "result": res, "action": action, "start": start}


def refresh_running():
    return _refresh_state["running"]


def refresh_status():
    return dict(_refresh_state, log=list(_refresh_state["log"][-12:]))


def _do_refresh(full=False):
    if not _refresh_lock.acquire(blocking=False):
        return False
    _refresh_state.update(running=True, started=datetime.now().strftime("%H:%M:%S"), log=[])
    try:
        ingest.refresh(full=full, log=lambda msg: _refresh_state["log"].append(msg))
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


def refresh_async(full=False):
    if refresh_running():
        return False
    threading.Thread(target=_do_refresh, kwargs={"full": full}, daemon=True).start()
    return True


def refresh_due():
    last = db.get_meta("last_refresh")
    if not last:
        return True
    try:
        age = datetime.now() - datetime.fromisoformat(last)
    except ValueError:
        return True
    return age.total_seconds() > REFRESH_INTERVAL_MIN * 60


def has_data():
    with db.session() as conn:
        return conn.execute("SELECT 1 FROM matches LIMIT 1").fetchone() is not None


def start_background_scheduler():
    """Odświeża dane co REFRESH_INTERVAL_MIN minut, dopóki proces działa.

    Na darmowym Renderze proces usypia po ~15 min bez ruchu – wtedy budzi go zewnętrzny
    pinger wywołujący /api/cron (patrz README)."""
    def loop():
        time.sleep(5)
        while True:
            try:
                if refresh_due():
                    _do_refresh()
            except Exception:  # noqa: BLE001
                log.exception("Błąd harmonogramu")
            time.sleep(300)

    threading.Thread(target=loop, daemon=True, name="scheduler").start()
