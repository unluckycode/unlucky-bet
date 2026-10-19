"""Minimal FotMob client (unofficial public JSON used by fotmob.com, no API key).

Endpoints:
  /api/data/allLeagues                     -> countries -> leagues
  /api/data/matches?date=YYYYMMDD          -> every match of the day, all leagues
  /api/data/leagues?id=ID[&season=S]       -> league details + fixtures.allMatches
"""
import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://www.fotmob.com/api/data"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
CACHE_DIR = os.environ.get("FOTMOB_CACHE", "/tmp/fotmob-cache")


def get(path, params=None, cache=True, retries=4):
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE}/{path}{qs}"
    key = os.path.join(CACHE_DIR, urllib.parse.quote(path + qs, safe="") + ".json")
    if cache and os.path.exists(key):
        with open(key) as f:
            return json.load(f)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            if cache:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(key, "w") as f:
                    json.dump(data, f)
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url}: {last}")


def all_leagues():
    return get("allLeagues")


def day_matches(yyyymmdd, cache=True):
    return get("matches", {"date": yyyymmdd}, cache=cache)


def league(league_id, season=None, cache=True):
    params = {"id": league_id}
    if season:
        params["season"] = season
    return get("leagues", params, cache=cache)
