"""Seria ligowa po kickoffie + scalanie FotMob."""

from unluckybet.analysis import advance, kickoff_groups, streak_runs, with_streaks


def _m(date, time, home, res, kickoff_utc=None, source="fotmob"):
    return {
        "date": date, "time": time, "home": home, "away": "X",
        "res": res, "hg": 1 if res == "H" else 0, "ag": 1 if res == "A" else (1 if res == "D" else 0),
        "kickoff_utc": kickoff_utc or f"{date}T{time}:00Z", "source": source, "season": "2026/2027",
        "odds_d_avg": None, "odds_d_max": None, "odds_d_b365": None, "event_id": home,
    }


def test_streak_resets_on_draw():
    rows = [
        _m("2026-10-16", "16:00", "A", "H"),
        _m("2026-10-16", "18:30", "B", "D"),
        _m("2026-10-17", "12:45", "C", "H"),
        _m("2026-10-17", "15:30", "D", "A"),
    ]
    _, cur = streak_runs(rows)
    assert cur == 2


def test_same_kickoff_draw_resets_whole_slot():
    rows = [
        _m("2026-10-18", "15:00", "A", "H", "2026-10-18T15:00:00Z"),
        _m("2026-10-18", "15:00", "B", "D", "2026-10-18T15:00:00Z"),  # remis w slocie
        _m("2026-10-18", "18:00", "C", "H", "2026-10-18T18:00:00Z"),
    ]
    groups = kickoff_groups(rows)
    assert len(groups) == 2
    assert advance(5, groups[0][1]) == 0
    _, cur = streak_runs(rows)
    assert cur == 1


def test_with_streaks_shared_in_slot():
    rows = [
        _m("2026-10-18", "15:00", "A", "H", "2026-10-18T15:00:00Z"),
        _m("2026-10-18", "15:00", "B", "A", "2026-10-18T15:00:00Z"),
    ]
    out = with_streaks(rows)
    assert out[0]["streak"] == out[1]["streak"] == 2
