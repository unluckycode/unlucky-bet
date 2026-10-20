"""Pobieranie i import danych z football-data.co.uk (darmowe, bez klucza API)."""

import csv
import io
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from . import db
from .leagues import BY_CODE, EXTRA_COUNTRY_TO_CODE, LEAGUES

BASE_URL = os.environ.get("UNLUCKYBET_SOURCE_URL", "https://www.football-data.co.uk")
SEASONS_BACK = int(os.environ.get("UNLUCKYBET_SEASONS", "10"))
EXTRA_FROM_YEAR = int(os.environ.get("UNLUCKYBET_EXTRA_FROM_YEAR", "2013"))
CACHE_MAX_AGE = 6 * 3600
RAW_DIR = db.DATA_DIR / "raw"


def current_season_start(today=None):
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def season_codes(n=SEASONS_BACK, today=None):
    start = current_season_start(today)
    years = range(start - n + 1, start + 1)
    return [f"{y % 100:02d}{(y + 1) % 100:02d}" for y in years]


def _fetch(url, path, max_age):
    if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
        return path.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "unlucky-bet/1.0"})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return data
        except Exception as err:  # noqa: BLE001 - sieć bywa kapryśna
            last_err = err
            time.sleep(2 * (attempt + 1))
    if path.exists():
        return path.read_bytes()
    raise last_err


def _rows(raw):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return list(csv.DictReader(io.StringIO(text)))


def _date(value):
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _float(row, *keys):
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            try:
                f = float(v)
                if f > 1:
                    return f
            except ValueError:
                pass
    return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _clean(v):
    return (v or "").strip()


def parse_main(code, season_code, raw):
    season = f"20{season_code[:2]}/20{season_code[2:]}"
    out = []
    for r in _rows(raw):
        d = _date(r.get("Date"))
        res = _clean(r.get("FTR"))
        home, away = _clean(r.get("HomeTeam") or r.get("HT")), _clean(r.get("AwayTeam") or r.get("AT"))
        if not d or res not in ("H", "D", "A") or not home:
            continue
        out.append((
            code, season, d, _clean(r.get("Time")), home, away,
            _int(r.get("FTHG")), _int(r.get("FTAG")), res,
            _float(r, "AvgD", "BbAvD", "AvgCD"),
            _float(r, "MaxD", "BbMxD", "MaxCD"),
            _float(r, "B365D", "B365CD"),
        ))
    return out


def parse_extra(code, raw):
    out = []
    for r in _rows(raw):
        d = _date(r.get("Date"))
        res = _clean(r.get("Res"))
        if not d or res not in ("H", "D", "A") or int(d[:4]) < EXTRA_FROM_YEAR:
            continue
        out.append((
            code, _clean(r.get("Season")), d, _clean(r.get("Time")),
            _clean(r.get("Home")), _clean(r.get("Away")),
            _int(r.get("HG")), _int(r.get("AG")), res,
            _float(r, "AvgCD", "AvgD"), _float(r, "MaxCD", "MaxD"), _float(r, "B365CD", "B365D"),
        ))
    return out


def parse_fixtures(raw, extra):
    out = []
    for r in _rows(raw):
        if extra:
            code = EXTRA_COUNTRY_TO_CODE.get(_clean(r.get("Country")))
            home, away = _clean(r.get("Home")), _clean(r.get("Away"))
        else:
            code = _clean(r.get("Div"))
            home, away = _clean(r.get("HomeTeam")), _clean(r.get("AwayTeam"))
        d = _date(r.get("Date"))
        if code not in BY_CODE or not d or not home:
            continue
        out.append((code, d, _clean(r.get("Time")), home, away,
                    _float(r, "AvgD"), _float(r, "MaxD"), _float(r, "B365D")))
    return out


MATCH_SQL = """
INSERT INTO matches(league, season, date, time, home, away, hg, ag, res, odds_d_avg, odds_d_max, odds_d_b365)
VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(league, date, home, away) DO UPDATE SET
  season=excluded.season, time=excluded.time, hg=excluded.hg, ag=excluded.ag, res=excluded.res,
  odds_d_avg=excluded.odds_d_avg, odds_d_max=excluded.odds_d_max, odds_d_b365=excluded.odds_d_b365
"""


def _prefetch(selected, codes, current, stored, full):
    """Równoległe pobranie plików do cache – serwer źródła odpowiada wolno (kilka s na plik)."""
    jobs = []
    for lg in selected:
        if lg.source == "main":
            for sc in codes:
                if not full and sc != current and (lg.code, f"20{sc[:2]}/20{sc[2:]}") in stored:
                    continue
                max_age = 0 if full else (CACHE_MAX_AGE if sc == current else None)
                jobs.append((f"{BASE_URL}/mmz4281/{sc}/{lg.code}.csv", RAW_DIR / sc / f"{lg.code}.csv", max_age))
        else:
            jobs.append((f"{BASE_URL}/new/{lg.code}.csv", RAW_DIR / "new" / f"{lg.code}.csv",
                         0 if full else CACHE_MAX_AGE))

    def safe(job):
        try:
            _fetch(*job)
        except Exception:  # noqa: BLE001 - błąd zostanie zgłoszony przy właściwym imporcie
            pass

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(safe, jobs))
    # Właściwy import korzysta już ze świeżego cache.
    return len(jobs)


def refresh(full=False, log=print, leagues=None):
    """Pobiera dane. Starsze sezony są cache'owane na dysku, bieżący odświeżany co 6 h."""
    db.init_db()
    codes = season_codes()
    current = codes[-1]
    selected = [lg for lg in LEAGUES if leagues is None or lg.code in leagues]
    total = 0
    errors = []
    with db.session() as conn:
        stored = {(r["league"], r["season"]) for r in conn.execute(
            "SELECT DISTINCT league, season FROM matches").fetchall()}
        _prefetch(selected, codes, current, stored, full)
        for lg in selected:
            n = 0
            try:
                if lg.source == "main":
                    for sc in codes:
                        season = f"20{sc[:2]}/20{sc[2:]}"
                        # Zakończone sezony, które już są w bazie, nie wymagają ponownego pobrania
                        # (ważne na hostingu z ulotnym dyskiem – cache CSV znika przy restarcie).
                        if not full and sc != current and (lg.code, season) in stored:
                            continue
                        max_age = CACHE_MAX_AGE if (full or sc == current) else None
                        try:
                            raw = _fetch(f"{BASE_URL}/mmz4281/{sc}/{lg.code}.csv", RAW_DIR / sc / f"{lg.code}.csv", max_age)
                        except Exception as err:  # noqa: BLE001
                            if sc != current:
                                log(f"  {lg.code} {sc}: brak pliku ({err})")
                            continue
                        rows = parse_main(lg.code, sc, raw)
                        conn.execute(
                            "DELETE FROM matches WHERE league=? AND season=? AND COALESCE(source,'football-data')!='fotmob'",
                            (lg.code, season))
                        conn.executemany(MATCH_SQL, rows)
                        n += len(rows)
                else:
                    raw = _fetch(f"{BASE_URL}/new/{lg.code}.csv", RAW_DIR / "new" / f"{lg.code}.csv", CACHE_MAX_AGE)
                    rows = parse_extra(lg.code, raw)
                    conn.execute(
                        "DELETE FROM matches WHERE league=? AND COALESCE(source,'football-data')!='fotmob'",
                        (lg.code,))
                    conn.executemany(MATCH_SQL, rows)
                    n = len(rows)
            except Exception as err:  # noqa: BLE001
                errors.append(f"{lg.code}: {err}")
                log(f"BŁĄD {lg.code}: {err}")
                continue
            conn.commit()
            total += n
            log(f"{lg.code:4s} {lg.country} – {lg.name}: {n} meczów zaktualizowanych")

        fixtures = []
        for name, extra in (("fixtures.csv", False), ("new_league_fixtures.csv", True)):
            try:
                raw = _fetch(f"{BASE_URL}/{name}", RAW_DIR / name, 0 if full else CACHE_MAX_AGE)
                fixtures += parse_fixtures(raw, extra)
            except Exception as err:  # noqa: BLE001
                errors.append(f"{name}: {err}")
        # Terminarz „na żywo” utrzymuje FotMob (live.py). Tutaj tylko dokładamy kursy
        # z football-data bez kasowania wpisów FotMob.
        conn.executemany(
            "INSERT INTO fixtures(league, date, time, home, away, odds_d_avg, odds_d_max, odds_d_b365) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING", fixtures)
        log(f"Terminarz football-data: {len(fixtures)} meczów (kursy; wyniki z FotMob)")

        settled = settle_pending_bets(conn)
        if settled:
            log(f"Automatycznie rozliczono zakładów: {settled}")

    db.set_meta("fd_refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # last_refresh ustawiane też przez live – nie nadpisuj świeższego FotMob starszym FD, jeśli live nowszy
    live_ts = db.get_meta("live_refresh")
    db.set_meta("last_refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    db.set_meta("refresh_errors", "; ".join(errors))
    return total, errors


def settle_pending_bets(conn):
    n = 0
    for bet in conn.execute("SELECT * FROM bets WHERE status='pending'").fetchall():
        m = conn.execute(
            "SELECT res FROM matches WHERE league=? AND date=? AND home=? AND away=?",
            (bet["league"], bet["match_date"], bet["home"], bet["away"]),
        ).fetchone()
        if m:
            conn.execute("UPDATE bets SET status=? WHERE id=?", ("won" if m["res"] == "D" else "lost", bet["id"]))
            n += 1
    return n
