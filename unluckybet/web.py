import hashlib
import hmac
import os
from datetime import date, timedelta
from pathlib import Path

import markdown
from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory,
                   session, url_for)

from . import analysis, db, notify, services, strategy
from .leagues import BY_CODE, LEAGUES

ROOT = Path(__file__).resolve().parent.parent
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
CRON_TOKEN = os.environ.get("CRON_TOKEN", "")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or hashlib.sha256(
    f"unlucky-bet::{APP_PASSWORD or 'local-dev'}".encode()).hexdigest()
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=60),
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "1" if APP_PASSWORD else "0") == "1",
)

PUBLIC_ENDPOINTS = {"login", "static", "manifest", "service_worker", "offline", "healthz", "cron"}


# ---------- formatowanie ----------

@app.template_filter("zl")
def fmt_zl(v, sign=False):
    if v is None:
        return "–"
    s = f"{abs(v):,.2f}".replace(",", " ").replace(".", ",")
    prefix = "−" if v < 0 else ("+" if sign and v > 0 else "")
    return f"{prefix}{s} zł"


@app.template_filter("pct")
def fmt_pct(v, digits=1):
    if v is None:
        return "–"
    return f"{v * 100:.{digits}f}".replace(".", ",") + "%"


@app.template_filter("num")
def fmt_num(v, digits=2):
    if v is None:
        return "–"
    return f"{v:,.{digits}f}".replace(",", " ").replace(".", ",")


MONTHS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]
WEEKDAYS = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]


@app.template_filter("dpl")
def fmt_date(v, weekday=False):
    if not v:
        return "–"
    d = date.fromisoformat(v)
    s = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return f"{WEEKDAYS[d.weekday()]}, {s}" if weekday else s


@app.context_processor
def inject():
    return {
        "last_refresh": (db.get_meta("last_refresh") or "")[:16],
        "refreshing": services.refresh_running(),
        "push_enabled": notify.enabled(),
        "vapid_public_key": notify.VAPID_PUBLIC_KEY,
        "auth_enabled": bool(APP_PASSWORD),
        "BY_CODE": BY_CODE,
    }


# ---------- autoryzacja ----------

@app.before_request
def require_login():
    if not APP_PASSWORD or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if session.get("auth") == _auth_token():
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Wymagane logowanie"), 401
    return redirect(url_for("login", next=request.full_path if request.method == "GET" else "/"))


def _auth_token():
    return hmac.new(app.secret_key.encode(), APP_PASSWORD.encode(), "sha256").hexdigest()


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if APP_PASSWORD and hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session.permanent = True
            session["auth"] = _auth_token()
            nxt = request.args.get("next") or "/"
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
        error = "Nieprawidłowe hasło."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- pomocnicze ----------

def _league_or_404(code):
    if code not in BY_CODE:
        abort(404)
    return BY_CODE[code]


def _strategy_form(form):
    def f(name, cast, default):
        try:
            return cast(form.get(name, default))
        except (TypeError, ValueError):
            return default

    values = {
        "threshold": max(1, f("threshold", int, 5)),
        "base_stake": max(0.01, f("base_stake", float, 10.0)),
        "multiplier": max(1.0, f("multiplier", float, 2.0)),
        "max_steps": max(0, f("max_steps", int, 8)),
        "bankroll": max(0.0, f("bankroll", float, 0.0)),
        "odds_mode": form.get("odds_mode") if form.get("odds_mode") in ("avg", "max", "b365", "fixed") else "avg",
        "fixed_odds": max(1.01, f("fixed_odds", float, 3.2)),
        "tax": min(0.5, max(0.0, f("tax_pct", float, 12.0) / 100)) if "tax_pct" in form else float(form.get("tax", 0.12)),
    }
    return values


def _card(code, st):
    s = analysis.summary(code)
    if not s or not s.get("n"):
        return None
    p = strategy.Params.from_row(st)
    live = services.live_state(st) if st["active"] else None
    if live:
        action = live["action"]
    else:
        action = strategy.next_action(strategy.Result(state=strategy.State(streak=s["current_streak"])), p)
    alert = s["current_streak"] >= p.threshold or (live and live["result"].state.in_cycle)
    return {"s": s, "st": st, "p": p, "live": live, "action": action, "alert": alert,
            "progress": min(1.0, s["current_streak"] / max(1, p.threshold))}


# ---------- widoki ----------

@app.route("/")
def dashboard():
    if not services.has_data():
        services.refresh_async()
        return render_template("loading.html")
    strategies = services.all_strategies()
    cards = [c for c in (_card(code, st) for code, st in strategies.items() if st["watched"]) if c]
    cards.sort(key=lambda c: (not c["alert"], -c["progress"], c["s"]["overlap_rate"] or 1))
    alerts = [c for c in cards if c["alert"]]
    suggestions = [s for s in analysis.all_summaries()
                   if s["fit_tone"] == "good" and s["code"] not in strategies][:4]
    with db.session() as conn:
        pending = conn.execute("SELECT COUNT(*) AS n FROM bets WHERE status='pending'").fetchone()["n"]
    return render_template("dashboard.html", cards=cards, alerts=alerts, suggestions=suggestions, pending=pending)


@app.route("/ligi")
def leagues():
    sort = request.args.get("sort", "overlap")
    keys = {
        "overlap": lambda s: s["overlap_rate"] if s["overlap_rate"] is not None else 9,
        "streak": lambda s: -s["current_streak"],
        "draws": lambda s: -s["draw_rate"],
        "longest": lambda s: -s["longest"],
    }
    rows = sorted(analysis.all_summaries(), key=keys.get(sort, keys["overlap"]))
    return render_template("leagues.html", rows=rows, sort=sort, strategies=services.all_strategies())


@app.route("/liga/<code>")
def league(code):
    lg = _league_or_404(code)
    s = analysis.summary(code)
    rows = analysis.matches(code)
    st = services.get_strategy(code)
    params = strategy.Params.from_row(st) if st else strategy.Params(**{
        k: services.DEFAULT_STRATEGY[k] for k in ("threshold", "base_stake", "multiplier", "max_steps",
                                                   "bankroll", "odds_mode", "fixed_odds", "tax")})
    live = services.live_state(st) if st and st["active"] else None
    recent, streak = [], 0
    for m in rows[-400:]:
        streak = 0 if m["res"] == "D" else streak + 1
        recent.append({**m, "streak": streak})
    return render_template(
        "league.html", lg=lg, s=s, st=st, params=params, live=live,
        recent=list(reversed(recent[-30:])),
        cond=analysis.league_conditional(code),
        dist=analysis.run_length_distribution(rows),
        capital=strategy.capital_needed(params),
    )


@app.route("/liga/<code>/strategia", methods=["POST"])
def save_strategy(code):
    _league_or_404(code)
    values = _strategy_form(request.form)
    values["watched"] = 1
    old = services.get_strategy(code)
    active = 1 if request.form.get("active") else 0
    values["active"] = active
    if active and (not old or not old["active"] or request.form.get("restart")):
        values["start_date"] = request.form.get("start_date") or date.today().isoformat()
    elif request.form.get("start_date"):
        values["start_date"] = request.form["start_date"]
    services.save_strategy(code, values)
    flash("Zapisano ustawienia strategii.", "ok")
    return redirect(url_for("league", code=code))


@app.route("/liga/<code>/obserwuj", methods=["POST"])
def toggle_watch(code):
    _league_or_404(code)
    st = services.get_strategy(code)
    if st and st["watched"]:
        services.save_strategy(code, {"watched": 0, "active": 0})
        flash(f"Usunięto {BY_CODE[code].name} z obserwowanych.", "ok")
    else:
        services.save_strategy(code, {"watched": 1})
        flash(f"Dodano {BY_CODE[code].name} do obserwowanych.", "ok")
    return redirect(request.form.get("back") or url_for("league", code=code))


@app.route("/backtest")
def backtest():
    code = request.args.get("league") or "POL"
    _league_or_404(code)
    st = services.get_strategy(code)
    base = st or services.DEFAULT_STRATEGY
    params = strategy.Params(**_strategy_form(request.args if "threshold" in request.args else base))
    seasons = sorted({m["season"] for m in analysis.matches(code)})
    since = request.args.get("since") or (seasons[0] if seasons else "")
    rows = [m for m in analysis.matches(code) if m["season"] >= since]
    result = strategy.run(rows, params)
    sweep = strategy.sweep(rows, params)
    link_args = {k: v for k, v in params.__dict__.items() if k != "threshold"}
    link_args.update(league=code, since=since)
    return render_template("backtest.html", code=code, params=params, result=result, sweep=sweep, link_args=link_args,
                           seasons=seasons, since=since, rows=rows,
                           summaries=analysis.all_summaries(), capital=strategy.capital_needed(params))


@app.route("/zaklady", methods=["GET", "POST"])
def bets():
    if request.method == "POST":
        f = request.form
        try:
            stake, odds = float(f["stake"].replace(",", ".")), float(f["odds"].replace(",", "."))
            tax = min(0.5, max(0.0, float((f.get("tax_pct") or "0").replace(",", ".")) / 100))
        except (KeyError, ValueError):
            flash("Podaj poprawną stawkę i kurs.", "err")
            return redirect(url_for("bets"))
        with db.session() as conn:
            conn.execute(
                "INSERT INTO bets(league, match_date, home, away, stake, odds, tax, step, status, note, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f["league"], f["match_date"], f["home"].strip(), f["away"].strip(), stake, odds, tax,
                 int(f.get("step") or 1), "pending", f.get("note", "").strip(), date.today().isoformat()))
        flash("Dodano zakład. Zostanie rozliczony automatycznie po pojawieniu się wyniku.", "ok")
        return redirect(url_for("bets"))
    with db.session() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM bets ORDER BY match_date DESC, id DESC").fetchall()]
    pnl, staked, history = 0.0, 0.0, []
    for b in sorted(rows, key=lambda b: (b["match_date"], b["id"])):
        if b["status"] == "won":
            b["profit"] = round(b["stake"] * (1 - b["tax"]) * b["odds"] - b["stake"], 2)
        elif b["status"] == "lost":
            b["profit"] = -b["stake"]
        else:
            b["profit"] = None
        if b["profit"] is not None:
            pnl += b["profit"]
            staked += b["stake"]
            history.append((b["match_date"], round(pnl, 2)))
    prefill = {k: request.args.get(k, "") for k in ("league", "match_date", "home", "away", "stake", "odds", "step", "tax_pct")}
    return render_template("bets.html", rows=rows, pnl=pnl, staked=staked, history=history, prefill=prefill,
                           pending=sum(1 for b in rows if b["status"] == "pending"), leagues=LEAGUES)


@app.route("/zaklady/<int:bet_id>/status", methods=["POST"])
def bet_status(bet_id):
    status = request.form.get("status")
    if status not in ("pending", "won", "lost", "void"):
        abort(400)
    with db.session() as conn:
        conn.execute("UPDATE bets SET status=? WHERE id=?", (status, bet_id))
        # Ręczne rozliczenie nie wymaga powiadomienia push.
        conn.execute("INSERT INTO notifications_sent(key, sent_at) VALUES(?, ?) ON CONFLICT DO NOTHING",
                     (f"bet:{bet_id}:{status}", date.today().isoformat()))
    return redirect(url_for("bets"))


@app.route("/zaklady/<int:bet_id>/usun", methods=["POST"])
def bet_delete(bet_id):
    with db.session() as conn:
        conn.execute("DELETE FROM bets WHERE id=?", (bet_id,))
    flash("Usunięto zakład.", "ok")
    return redirect(url_for("bets"))


@app.route("/matematyka")
def math_page():
    text = (ROOT / "docs" / "wyjasnienie-matematyczne.md").read_text(encoding="utf-8")
    html = markdown.markdown(text, extensions=["tables", "toc", "fenced_code"])
    summaries = [s for s in analysis.all_summaries() if s["fit_tone"] == "good"]
    return render_template("math.html", content=html, indep=analysis.independence_table(),
                           indep_fit=analysis.independence_table([s["code"] for s in summaries]),
                           fit_names=", ".join(s["league"].name for s in summaries))


@app.route("/ustawienia")
def settings():
    return render_template("settings.html", backend=db.backend_name(), subs=notify.subscription_count(),
                           cron_configured=bool(CRON_TOKEN), errors=db.get_meta("refresh_errors") or "")


# ---------- odświeżanie, cron, API ----------

@app.route("/odswiez", methods=["POST"])
def refresh():
    started = services.refresh_async(full=bool(request.form.get("full")))
    flash("Rozpoczęto pobieranie danych – potrwa to od kilkudziesięciu sekund do kilku minut."
          if started else "Odświeżanie już trwa.", "ok")
    return redirect(request.form.get("back") or url_for("dashboard"))


@app.route("/api/status")
def api_status():
    return jsonify({**services.refresh_status(), "last_refresh": db.get_meta("last_refresh")})


@app.route("/api/cron", methods=["GET", "POST"])
def cron():
    token = request.args.get("token") or request.headers.get("X-Cron-Token", "")
    if not CRON_TOKEN or not hmac.compare_digest(token, CRON_TOKEN):
        return jsonify(error="Nieprawidłowy token"), 403
    started = services.refresh_async() if (services.refresh_due() or request.args.get("force")) else False
    return jsonify(ok=True, refresh_started=started, refreshing=services.refresh_running(),
                   last_refresh=db.get_meta("last_refresh")), 202 if started else 200


@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    sub = request.get_json(silent=True) or {}
    if not sub.get("endpoint"):
        return jsonify(error="Brak subskrypcji"), 400
    notify.save_subscription(sub)
    return jsonify(ok=True)


@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    sub = request.get_json(silent=True) or {}
    if sub.get("endpoint"):
        notify.delete_subscription(sub["endpoint"])
    return jsonify(ok=True)


@app.route("/api/push/test", methods=["POST"])
def push_test():
    n = notify.send_all("Unlucky Bet", "Powiadomienia działają 🎯", "/")
    return jsonify(ok=True, sent=n)


# ---------- PWA ----------

@app.route("/manifest.webmanifest")
def manifest():
    resp = send_from_directory(app.static_folder, "manifest.webmanifest")
    resp.mimetype = "application/manifest+json"
    return resp


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/offline")
def offline():
    return render_template("offline.html")


@app.route("/healthz")
def healthz():
    return "ok"


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", message="Nie znaleziono strony."), 404


def create_app():
    db.init_db()
    if os.environ.get("DISABLE_SCHEDULER") != "1":
        services.start_background_scheduler()
    return app
