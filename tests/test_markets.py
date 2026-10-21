"""Rynki Over/Under 2.5 i BTTS – serie i martingale."""

from unluckybet.analysis import recommendations, streak_runs
from unluckybet.markets import get_market, is_btts_yes, is_over25
from unluckybet.strategy import Params, run


def _m(date, time, home, hg, ag, kickoff=None):
    res = "H" if hg > ag else ("A" if hg < ag else "D")
    return {
        "date": date, "time": time, "home": home, "away": "X",
        "hg": hg, "ag": ag, "res": res,
        "kickoff_utc": kickoff or f"{date}T{time}:00Z",
        "source": "fotmob", "season": "2026/2027",
        "odds_d_avg": None, "odds_d_max": None, "odds_d_b365": None, "event_id": home,
    }


def test_over25_detection():
    assert is_over25(_m("2026-01-01", "12:00", "A", 2, 1))
    assert not is_over25(_m("2026-01-01", "12:00", "A", 1, 1))


def test_btts_detection():
    assert is_btts_yes(_m("2026-01-01", "12:00", "A", 1, 1))
    assert not is_btts_yes(_m("2026-01-01", "12:00", "A", 2, 0))


def test_ou_streak_no_over():
    rows = [
        _m("2026-10-01", "12:00", "A", 1, 0),  # under
        _m("2026-10-01", "15:00", "B", 0, 0),  # under
        _m("2026-10-02", "12:00", "C", 2, 2),  # over → reset
        _m("2026-10-02", "18:00", "D", 1, 0),  # under
    ]
    _, cur = streak_runs(rows, "ou25", "over")
    assert cur == 1


def test_btts_streak_no_yes():
    rows = [
        _m("2026-10-01", "12:00", "A", 1, 0),
        _m("2026-10-01", "15:00", "B", 2, 0),
        _m("2026-10-02", "12:00", "C", 1, 1),  # btts → reset
    ]
    _, cur = streak_runs(rows, "btts", "yes")
    assert cur == 0


def test_ou_martingale_bets_over_after_streak():
    # 4 under then one under (still under) – with X=3 should bet from 4th match
    rows = [
        _m("2026-10-01", "10:00", "A", 0, 0),
        _m("2026-10-01", "12:00", "B", 1, 0),
        _m("2026-10-01", "14:00", "C", 0, 1),
        _m("2026-10-01", "16:00", "D", 1, 0),  # streak before = 3 → bet Over, loses
        _m("2026-10-01", "18:00", "E", 2, 1),  # Over wins
    ]
    p = Params(threshold=3, base_stake=10, multiplier=2, max_steps=5,
               odds_mode="fixed", fixed_odds=1.9, tax=0.12, market="ou25", side="over")
    r = run(rows, p)
    assert len(r.bets) >= 1
    assert r.bets[0]["home"] == "D"
    assert r.bets[0]["won"] is False
    assert any(b["won"] for b in r.bets)


def test_market_labels():
    mk = get_market("ou25")
    assert "Over" in mk.bet_label("over")
    assert "Under" in mk.streak_label("over") or "≤2" in mk.streak_label("over")
