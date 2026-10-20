"""Klient FotMob (publiczne JSON-y strony fotmob.com, bez klucza API).

Adapter świeżych wyników: każdy wpis ligi ma `fotmob_id`. Kolejni dostawcy
mogą dostać własny moduł z tą samą powierzchnią (`fetch_league_matches`).

Endpointy:
  /api/data/allLeagues
  /api/data/matches?date=YYYYMMDD
  /api/data/leagues?id=ID[&season=S]
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

BASE = "https://www.fotmob.com/api/data"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")
CACHE_DIR = Path(os.environ.get("FOTMOB_CACHE", os.environ.get("UNLUCKYBET_DATA_DIR", "data") + "/fotmob-cache"))
MIN_INTERVAL = float(os.environ.get("FOTMOB_MIN_INTERVAL", "0.35"))
CACHE_TTL = int(os.environ.get("FOTMOB_CACHE_TTL", "600"))  # sekundy; 0 = tylko pamięć dyskowa bez TTL

_lock = threading.Lock()
_last_call = 0.0


def _cache_path(path: str, params: dict | None) -> Path:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    return CACHE_DIR / (urllib.parse.quote(path + qs, safe="") + ".json")


def get(path, params=None, cache=True, retries=4, ttl=None):
    """GET z limitem częstości i cache na dysku (TTL w sekundach)."""
    global _last_call
    ttl = CACHE_TTL if ttl is None else ttl
    key = _cache_path(path, params)
    if cache and key.exists():
        age = time.time() - key.stat().st_mtime
        if ttl <= 0 or age < ttl:
            return json.loads(key.read_text(encoding="utf-8"))
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE}/{path}{qs}"
    last = None
    for attempt in range(retries):
        with _lock:
            wait = _last_call + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            if cache:
                key.parent.mkdir(parents=True, exist_ok=True)
                key.write_text(json.dumps(data), encoding="utf-8")
            return data
        except urllib.error.HTTPError as err:
            last = err
            time.sleep(15 if err.code == 429 else 2 ** attempt)
        except Exception as err:  # noqa: BLE001
            last = err
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url}: {last}")


def all_leagues(cache=True):
    return get("allLeagues", cache=cache)


def day_matches(yyyymmdd, cache=True, ttl=120):
    return get("matches", {"date": yyyymmdd}, cache=cache, ttl=ttl)


def league(league_id, season=None, cache=True, ttl=None):
    params = {"id": int(league_id)}
    if season:
        params["season"] = season
    return get("leagues", params, cache=cache, ttl=ttl)


def parse_score(s):
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def season_matches(data, now=None):
    """Parsuje fixtures.allMatches z endpointu ligi do jednolitych rekordów."""
    now = now or datetime.now(timezone.utc)
    fx = (data.get("fixtures") or {}).get("allMatches") or []
    rows = []
    for m in fx:
        st = m.get("status") or {}
        if st.get("cancelled"):
            continue
        t = st.get("utcTime")
        if not t:
            continue
        utc = datetime.fromisoformat(t.replace("Z", "+00:00"))
        finished = bool(st.get("finished")) and utc <= now
        score = parse_score(st.get("scoreStr")) if finished else None
        if finished and not score:
            continue
        home = ((m.get("home") or {}).get("name") or "").strip()
        away = ((m.get("away") or {}).get("name") or "").strip()
        if not home or not away:
            continue
        status = "finished" if finished else ("playing" if st.get("started") and not finished else "upcoming")
        rows.append({
            "event_id": str(m.get("id")),
            "round": str(m.get("round") or ""),
            "kickoff_utc": utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home": home,
            "away": away,
            "finished": finished,
            "status": status,
            "hg": score[0] if score else None,
            "ag": score[1] if score else None,
            "res": ("H" if score[0] > score[1] else ("A" if score[0] < score[1] else "D")) if score else None,
        })
    rows.sort(key=lambda r: (r["kickoff_utc"], r["home"]))
    return rows


def seasons_to_fetch(latest):
    """Bieżący sezon + poprzedni; więcej przy Apertura/Clausura lub gdy bieżący pusty."""
    seasons = latest.get("allAvailableSeasons") or []
    if not seasons:
        return []
    first = season_matches(latest)
    empty = not any(r["finished"] for r in first)
    extra = 2 if empty else 1
    if " - " in seasons[0]:
        extra *= 2
    return [None] + seasons[1:1 + extra]  # None = już pobrany latest


def fetch_league_matches(league_id, now=None, cache=True, ttl=None):
    """Wszystkie mecze (zakończone + nadchodzące) z wybranych sezonów ligi."""
    now = now or datetime.now(timezone.utc)
    latest = league(league_id, cache=cache, ttl=ttl)
    details = latest.get("details") or {}
    season_name = (latest.get("allAvailableSeasons") or [None])[0]
    by_id = {}
    for season in seasons_to_fetch(latest):
        data = latest if season is None else league(league_id, season, cache=cache, ttl=ttl)
        sn = season or season_name or ""
        for row in season_matches(data, now):
            row = {**row, "season": sn.replace(" - ", "/")}
            by_id[row["event_id"]] = row
    return {
        "league_id": int(league_id),
        "name": details.get("name") or "",
        "current_season": season_name,
        "matches": sorted(by_id.values(), key=lambda r: (r["kickoff_utc"], r["home"])),
    }
