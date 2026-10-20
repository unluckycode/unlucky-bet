"""Silnik strategii martingale dla rynków: remis, Over/Under 2.5, BTTS.

Zasady (wspólne dla backtestu i śledzenia "na żywo"):
* Mecze przetwarzane są chronologicznie wg kickoffu. Jeśli kilka meczów startuje
  o tej samej godzinie, obstawiamy tylko pierwszy z nich (wg nazwy gospodarza), a seria
  aktualizuje się o wyniki wszystkich: trafienie rynku w którymkolwiek zeruje serię.
* Cykl startuje, gdy seria bez zdarzenia przed meczem >= X. Trwa do wygranej albo stop-loss.
* Stawka w kroku n: stawka_bazowa * mnożnik^(n-1). Wygrana = stawka * (1 - podatek) * kurs.
* Po stop-lossie kolejny cykl zaczyna się dopiero po nowym trafieniu i ponownej serii X.
* Jeśli bankroll jest ustawiony i nie starcza na stawkę – bankructwo.
"""

from dataclasses import dataclass, field

from .analysis import advance, kickoff_groups
from .markets import get_market


@dataclass
class Params:
    threshold: int = 5
    base_stake: float = 10.0
    multiplier: float = 2.0
    max_steps: int = 8
    bankroll: float = 0.0
    odds_mode: str = "avg"
    fixed_odds: float = 3.2
    tax: float = 0.12
    market: str = "draw"
    side: str = ""

    @classmethod
    def from_row(cls, row):
        row = dict(row)
        mk = get_market(row.get("market") or "draw")
        side = mk.normalize_side(row.get("side") or "")
        tax = float(row["tax"]) if row.get("tax") is not None else 0.12
        fixed = float(row["fixed_odds"] or 0) or mk.default_odds
        return cls(
            threshold=int(row["threshold"]), base_stake=float(row["base_stake"]),
            multiplier=float(row["multiplier"]), max_steps=int(row["max_steps"]),
            bankroll=float(row["bankroll"]), odds_mode=row["odds_mode"], fixed_odds=fixed,
            tax=tax, market=mk.key, side=side,
        )

    def stake(self, step):
        return round(self.base_stake * self.multiplier ** (step - 1), 2)


@dataclass
class State:
    streak: int = 0
    in_cycle: bool = False
    step: int = 1
    cycle_loss: float = 0.0
    waiting_reset: bool = False
    pnl: float = 0.0
    ruined: bool = False


@dataclass
class Result:
    bets: list = field(default_factory=list)
    cycles: list = field(default_factory=list)
    equity: list = field(default_factory=list)
    state: State = field(default_factory=State)
    total_staked: float = 0.0
    max_drawdown: float = 0.0
    max_step: int = 0
    missing_odds: int = 0
    ruin_date: str = None

    @property
    def wins(self):
        return sum(1 for c in self.cycles if c["outcome"] == "wygrana")

    @property
    def stops(self):
        return sum(1 for c in self.cycles if c["outcome"] == "stop-loss")

    @property
    def roi(self):
        return self.state.pnl / self.total_staked if self.total_staked else 0.0


def pick_odds(m, p: Params):
    mk = get_market(p.market)
    if p.odds_mode == "fixed" or not mk.odds_keys:
        return p.fixed_odds or mk.default_odds, p.odds_mode != "fixed" and not mk.odds_keys
    key = mk.odds_keys.get(p.odds_mode)
    v = m.get(key) if key else None
    if not v:
        return p.fixed_odds or mk.default_odds, True
    return v, False


def run(rows, p: Params, initial_streak=0):
    mk = get_market(p.market)
    side = mk.normalize_side(p.side)
    hit = lambda m: mk.hit(m, side)  # noqa: E731
    res = Result()
    st = res.state
    st.streak = initial_streak
    peak = 0.0
    cycle = None
    for _, group in kickoff_groups(rows):
        if st.ruined:
            break
        target = group[0]
        should_bet = st.in_cycle or (st.streak >= p.threshold and not st.waiting_reset)
        if should_bet:
            stake = p.stake(st.step)
            if p.bankroll and p.bankroll + st.pnl < stake:
                st.ruined = True
                res.ruin_date = target["date"]
                if cycle:
                    cycle.update(outcome="bankructwo", end=target["date"])
                break
            if not st.in_cycle:
                st.in_cycle = True
                cycle = {"start": target["date"], "streak_at_start": st.streak, "steps": 0,
                         "loss": 0.0, "outcome": "w toku", "end": None, "profit": 0.0}
                res.cycles.append(cycle)
            odds, missing = pick_odds(target, p)
            res.missing_odds += missing
            won = hit(target)
            profit = round(stake * (1 - p.tax) * odds - stake, 2) if won else -stake
            st.pnl = round(st.pnl + profit, 2)
            res.total_staked += stake
            res.max_step = max(res.max_step, st.step)
            cycle["steps"] = st.step
            res.bets.append({
                "date": target["date"], "time": target["time"], "home": target["home"], "away": target["away"],
                "score": f"{target['hg']}:{target['ag']}" if target.get("hg") is not None else "",
                "step": st.step, "stake": stake, "odds": odds, "won": won, "profit": profit,
                "pnl": st.pnl, "parallel": len(group), "market": mk.key, "side": side,
            })
            if won:
                cycle.update(outcome="wygrana", end=target["date"], profit=round(profit - st.cycle_loss, 2))
                st.in_cycle, st.step, st.cycle_loss = False, 1, 0.0
            else:
                st.cycle_loss = round(st.cycle_loss + stake, 2)
                cycle["loss"] = st.cycle_loss
                st.step += 1
                if p.max_steps and st.step > p.max_steps:
                    cycle.update(outcome="stop-loss", end=target["date"], profit=-st.cycle_loss)
                    st.in_cycle, st.step, st.cycle_loss = False, 1, 0.0
                    st.waiting_reset = True
            peak = max(peak, st.pnl)
            res.max_drawdown = max(res.max_drawdown, peak - st.pnl)
            res.equity.append((target["date"], st.pnl))
        st.streak = advance(st.streak, group, hit)
        if st.streak == 0:
            st.waiting_reset = False
    return res


def next_action(res: Result, p: Params):
    mk = get_market(p.market)
    side = mk.normalize_side(p.side)
    label = mk.bet_label(side)
    st = res.state
    if st.ruined:
        return {"bet": False, "reason": "Bankructwo – kapitał nie pokrywa kolejnej stawki."}
    if st.in_cycle:
        return {"bet": True, "step": st.step, "stake": p.stake(st.step), "cycle_loss": st.cycle_loss,
                "reason": f"Trwa cykl – krok {st.step} ({label}).", "label": label}
    if st.waiting_reset:
        return {"bet": False, "reason": f"Po stop-lossie – czekamy na {label} i nową serię.", "label": label}
    if st.streak >= p.threshold:
        return {"bet": True, "step": 1, "stake": p.stake(1), "cycle_loss": 0.0,
                "reason": f"Seria {st.streak} ≥ X={p.threshold} – start cyklu ({label}).", "label": label}
    return {"bet": False,
            "reason": f"Seria {st.streak} < X={p.threshold} – czekamy jeszcze {p.threshold - st.streak}.",
            "label": label}


def capital_needed(p: Params, steps=None):
    steps = steps or p.max_steps or 10
    return round(sum(p.stake(i) for i in range(1, steps + 1)), 2)


def sweep(rows, p: Params, xs=range(1, 13)):
    out = []
    for x in xs:
        q = Params(**{**p.__dict__, "threshold": x})
        r = run(rows, q)
        out.append({"x": x, "bets": len(r.bets), "cycles": len(r.cycles), "wins": r.wins, "stops": r.stops,
                    "pnl": r.state.pnl, "staked": r.total_staked, "roi": r.roi, "dd": r.max_drawdown,
                    "max_step": r.max_step, "ruin": r.ruin_date})
    return out
