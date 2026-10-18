"""Scan FotMob leagues worldwide and compute draw-streak statistics.

Usage: python3 scripts/world_leagues/analyze.py [--out results.json] [--workers 6] [--refresh]

For each domestic league (cups, women's, youth and qualification/playoff
competitions excluded by name) the latest two seasons are fetched and:
  overlap        share of finished matches kicking off at exactly the same UTC
                 time as another match of the league (final round of every
                 season excluded)
  streak_now     league-wide matches since the last draw (chronological over
                 both seasons, ordered by kickoff)
  draw_rate      draws / finished matches
  streak_record  longest run without a draw in the window
  next_match     first scheduled, unplayed match
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import fotmob  # noqa: E402

EXCLUDE = re.compile(
    r"cup|pokal|copa|coupe|coppa|beker|ta[cç]a|puchar|\bkup|cupa|kupa|shield|troph|trofeo|recopa|"
    r"qualif|playoff|relegation|women|femen|f[eé]minin|femminile|frauen|vrouwen|kvinner|\(w\)|"
    r"liga f$|we league|nwsl|toppserien|damallsvenskan|elitettan|northern super league|baller|"
    r"premier league 2|revela|next pro|verano|campe[oó]n de campeones|baiano|carioca|ga[uú]cho|"
    r"goiano|mineiro|paulista|durand|president|emperor|l[øo]gmanssteypi|norgesmesterskapet|hazfi|"
    r"throne|nedbank|8 cup|c[uú]p qu|kansallinen|supercopa|super ?cup|superliga$|campeones|"
    r"norsk tipping|swf|highland|a-liga|national north|super league women|"
    r"usl super league|u1[789]|u2[01]|wsl|swpl",
    re.I,
)
# names that would be wrongly excluded by the generic rules above
FORCE_INCLUDE = {540, 335}  # Uzbekistan Superliga, El Salvador Primera Division
EXCLUDE_IDS = {8947, 9837, 285}  # ENG Premier Division (non-league), Canadian Championship (cup), AUT Landesliga


def candidates():
    out = []
    for c in fotmob.all_leagues()["countries"]:
        tier = 0
        for lg in c["leagues"]:
            if lg["id"] in EXCLUDE_IDS or (lg["id"] not in FORCE_INCLUDE and EXCLUDE.search(lg["name"])):
                continue
            tier += 1
            out.append({"id": lg["id"], "name": lg["name"], "ccode": c["ccode"],
                        "country": c["name"], "order": tier})
    return out


def parse_score(s):
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def round_num(r):
    try:
        return int(r)
    except (TypeError, ValueError):
        return None


def season_matches(data, now):
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
        rows.append({
            "id": m.get("id"),
            "round": m.get("round"),
            "utc": utc,
            "home": (m.get("home") or {}).get("name"),
            "away": (m.get("away") or {}).get("name"),
            "finished": finished,
            "score": parse_score(st.get("scoreStr")) if finished else None,
        })
    return rows


def overlap_stats(rows):
    fin = [r for r in rows if r["finished"] and r["score"]]
    rounds = [round_num(r["round"]) for r in rows if round_num(r["round"]) is not None]
    last_round = max(rounds) if rounds else None
    season_complete = rows and all(r["finished"] for r in rows)
    if season_complete and last_round is not None:
        fin = [r for r in fin if round_num(r["round"]) != last_round]
    cnt = Counter(r["utc"] for r in fin)
    same = sum(1 for r in fin if cnt[r["utc"]] > 1)
    return same, len(fin)


def analyze_league(c, now, refresh=False):
    latest = fotmob.league(c["id"], cache=not refresh)
    seasons = latest.get("allAvailableSeasons") or []
    details = latest.get("details") or {}
    if details.get("gender") and details["gender"] != "male":
        return None
    per_season = {}
    if seasons:
        per_season[seasons[0]] = season_matches(latest, now)
    # latest + previous season; one more if the latest has not kicked off yet,
    # and twice as many for Apertura/Clausura split seasons
    extra = 2 if seasons and not any(r["finished"] for r in per_season[seasons[0]]) else 1
    if seasons and " - " in seasons[0]:
        extra *= 2
    for s in seasons[1:1 + extra]:
        per_season[s] = season_matches(fotmob.league(c["id"], s), now)
    if not per_season:
        return None

    all_rows = [r for rows in per_season.values() for r in rows]
    fin = sorted((r for r in all_rows if r["finished"] and r["score"]), key=lambda r: (r["utc"], str(r["id"])))
    if len(fin) < 30:
        return None

    same = tot = 0
    season_out = []
    for s, rows in per_season.items():
        a, b = overlap_stats(rows)
        same += a
        tot += b
        f = [r for r in rows if r["finished"] and r["score"]]
        season_out.append({
            "season": s,
            "matches_total": len(rows),
            "matches_finished": len(f),
            "draws": sum(1 for r in f if r["score"][0] == r["score"][1]),
            "overlap": round(a / b, 4) if b else None,
        })

    draws = [r["score"][0] == r["score"][1] for r in fin]
    streak_now = 0
    for d in reversed(draws):
        if d:
            break
        streak_now += 1
    best = run = 0
    for d in draws:
        run = 0 if d else run + 1
        best = max(best, run)

    cur_rows = per_season[seasons[0]] if seasons else []
    upcoming = sorted((r for r in cur_rows if not r["finished"] and r["utc"] >= now - timedelta(hours=3)),
                      key=lambda r: r["utc"])
    nxt = upcoming[0] if upcoming else None
    last = fin[-1]
    last_draw = next((r for r in reversed(fin) if r["score"][0] == r["score"][1]), None)
    active = bool(nxt and nxt["utc"] - now <= timedelta(days=21))

    return {
        **c,
        "fotmob_id": c["id"],
        "fotmob_name": details.get("name", c["name"]),
        "seasons": season_out,
        "current_season": seasons[0] if seasons else None,
        "matches_finished": len(fin),
        "overlap": round(same / tot, 4) if tot else None,
        "overlap_current": season_out[0]["overlap"],
        "draw_rate": round(sum(draws) / len(draws), 4),
        "streak_now": streak_now,
        "streak_record": best,
        "last_match": {"utc": last["utc"].isoformat(), "home": last["home"], "away": last["away"],
                       "score": f"{last['score'][0]}-{last['score'][1]}"},
        "last_draw_utc": last_draw["utc"].isoformat() if last_draw else None,
        "next_match": ({"utc": nxt["utc"].isoformat(), "home": nxt["home"], "away": nxt["away"]} if nxt else None),
        "remaining_in_season": len(upcoming),
        "active": active,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="world_leagues_results.json")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true", help="refetch latest seasons (ignore cache)")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    cands = candidates()
    print(f"{len(cands)} candidate leagues", file=sys.stderr)
    results, errors = [], []
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(analyze_league, c, now, args.refresh): c for c in cands}
        for f in as_completed(futs):
            c = futs[f]
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception as e:  # noqa: BLE001
                errors.append({"id": c["id"], "name": c["name"], "error": str(e)})
    results.sort(key=lambda r: (r["overlap"] if r["overlap"] is not None else 9, -r["streak_now"]))
    with open(args.out, "w") as f:
        json.dump({"generated_utc": now.isoformat(), "source": "fotmob", "leagues": results,
                   "errors": errors}, f, ensure_ascii=False, indent=1)
    print(f"{len(results)} leagues analysed, {len(errors)} errors -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
