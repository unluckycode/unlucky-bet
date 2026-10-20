"""Świeże wyniki i terminarz z FotMob – źródło minutowe dla serii i „następnego meczu”.

football-data.co.uk zostaje do kursów i długiej historii; serie i pulpit bazują na FotMob.
Adapter na ligę: `League.fotmob_id` → `fotmob.fetch_league_matches`.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, fotmob
from .leagues import BY_CODE, FITTING, LEAGUES

log = logging.getLogger(__name__)

PL = ZoneInfo("Europe/Warsaw")
UK = ZoneInfo("Europe/London")
LIVE_REFRESH_MIN = int(os.environ.get("LIVE_REFRESH_MIN", "15"))
LIVE_WORKERS = int(os.environ.get("LIVE_WORKERS", "4"))


def utc_to_pl(ts: str):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(PL)
    return dt.date().isoformat(), dt.strftime("%H:%M")


def uk_to_pl(d, t):
    if not d or not t:
        return d, t or ""
    dt = datetime.fromisoformat(f"{d}T{t}").replace(tzinfo=UK).astimezone(PL)
    return dt.date().isoformat(), dt.strftime("%H:%M")


def kickoff_pl(row):
    """Zwraca (date, time) w czasie polskim – z kickoff_utc albo z pól date/time (UK)."""
    if row.get("kickoff_utc"):
        return utc_to_pl(row["kickoff_utc"])
    return uk_to_pl(row.get("date"), row.get("time") or "00:00")


def default_codes():
    """Ligi odświeżane cyklicznie: LIVE_LEAGUES / obserwowane / domyślnie 27 pasujących."""
    env = os.environ.get("LIVE_LEAGUES", "").strip()
    if env.lower() == "all":
        return [lg.code for lg in LEAGUES]
    codes = [c.strip() for c in env.split(",") if c.strip()]
    with db.session() as conn:
        codes += [r["league"] for r in conn.execute(
            "SELECT league FROM strategies WHERE watched=1 OR active=1").fetchall()]
    if not codes:
        codes = [lg.code for lg in FITTING]
    # zachowaj kolejność, unikaj duplikatów
    out = []
    for c in codes:
        if c in BY_CODE and c not in out:
            out.append(c)
    return out


def _upsert_league(code, payload, conn):
    lg = BY_CODE[code]
    season = (payload.get("current_season") or "").replace(" - ", "/")
    rows_m, rows_f = [], []
    for m in payload["matches"]:
        d, t = utc_to_pl(m["kickoff_utc"])
        if m["status"] == "finished" and m["res"]:
            rows_m.append((
                code, m.get("season") or season, d, t, m["home"], m["away"],
                m["hg"], m["ag"], m["res"], m["kickoff_utc"], m["event_id"], "fotmob",
            ))
        elif m["status"] in ("upcoming", "playing"):
            rows_f.append((
                code, d, t, m["home"], m["away"], None, None, None,
                m["kickoff_utc"], m["event_id"], m["status"],
            ))
    # Usuń poprzednie wiersze z FotMob dla tej ligi (zostaw historię football-data).
    conn.execute("DELETE FROM matches WHERE league=? AND source='fotmob'", (code,))
    conn.execute("DELETE FROM fixtures WHERE league=?", (code,))
    if rows_m:
        conn.executemany(
            "INSERT INTO matches(league, season, date, time, home, away, hg, ag, res, "
            "kickoff_utc, event_id, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT DO NOTHING",
            rows_m,
        )
    if rows_f:
        conn.executemany(
            "INSERT INTO fixtures(league, date, time, home, away, odds_d_avg, odds_d_max, odds_d_b365, "
            "kickoff_utc, event_id, status) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT DO NOTHING",
            rows_f,
        )
    # Dopisz kursy z football-data do fixtures, gdy da się dopasować po dacie±1 i nazwach.
    _attach_odds(conn, code)
    return len(rows_m), len(rows_f)


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").replace("ł", "l").replace("Ł", "L"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return "".join(ch if ch.isalnum() else " " for ch in s).split()


def _similar(a, b):
    ta, tb = _norm(a), _norm(b)
    if not ta or not tb:
        return False
    if ta == tb or ta[0] == tb[0] and len(ta[0]) >= 4:
        return True
    return any(x in tb for x in ta if len(x) >= 4) or any(x in ta for x in tb if len(x) >= 4)


def _attach_odds(conn, code):
    """Przenosi kursy z historycznych fixtures football-data / matches na bieżący terminarz FotMob."""
    # Kursy są w tabeli matches (history) – bierzemy średnie z ostatnich meczów drużyn? 
    # Prościej: jeśli ingest football-data zapisał fixtures przed live, zdążyły zostać skasowane.
    # Zostawiamy odds puste; backtest używa historycznych odds_d_* z matches football-data.
    return


def refresh(codes=None, log_fn=print, workers=None):
    db.init_db()
    codes = codes if codes is not None else default_codes()
    workers = workers or LIVE_WORKERS
    errors, total_m, total_f = [], 0, 0

    def one(code):
        lg = BY_CODE[code]
        return code, fotmob.fetch_league_matches(lg.fotmob_id, cache=True, ttl=LIVE_REFRESH_MIN * 60)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one, c): c for c in codes}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                code, payload = fut.result()
                with db.session() as conn:
                    nm, nf = _upsert_league(code, payload, conn)
                total_m += nm
                total_f += nf
                log_fn(f"FotMob {code:6s} {BY_CODE[code].name}: {nm} wyników, {nf} w terminarzu")
            except Exception as err:  # noqa: BLE001
                errors.append(f"{code}: {err}")
                log_fn(f"FotMob {code}: błąd ({err})")
                log.exception("live refresh %s", code)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.set_meta("live_refresh", now)
    db.set_meta("last_refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    db.set_meta("live_errors", "; ".join(errors))
    # rozlicz zakłady po świeżych wynikach
    with db.session() as conn:
        from . import ingest
        settled = ingest.settle_pending_bets(conn)
        if settled:
            log_fn(f"Automatycznie rozliczono zakładów: {settled}")
    return total_m + total_f, errors


def live_refresh_due():
    last = db.get_meta("live_refresh")
    if not last:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    return age.total_seconds() > LIVE_REFRESH_MIN * 60


def ensure_default_watches():
    """Delegacja do services – wiersze strategii per liga × rynek."""
    from . import services
    return services.ensure_default_watches()
