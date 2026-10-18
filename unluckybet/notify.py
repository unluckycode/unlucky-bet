"""Powiadomienia Web Push (opcjonalne – wymagają kluczy VAPID w zmiennych środowiskowych)."""

import json
import logging
import os
from datetime import datetime

from . import analysis, db, strategy
from .leagues import BY_CODE

log = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com").strip()


def enabled():
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def save_subscription(sub):
    with db.session() as conn:
        conn.execute(
            "INSERT INTO push_subscriptions(endpoint, data, created_at) VALUES(?,?,?) "
            "ON CONFLICT(endpoint) DO UPDATE SET data=excluded.data",
            (sub["endpoint"], json.dumps(sub), datetime.now().isoformat(timespec="seconds")),
        )


def delete_subscription(endpoint):
    with db.session() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))


def subscription_count():
    with db.session() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM push_subscriptions").fetchone()["n"]


def send_all(title, body, url="/"):
    if not enabled():
        return 0
    from pywebpush import WebPushException, webpush

    with db.session() as conn:
        subs = [r["data"] for r in conn.execute("SELECT data FROM push_subscriptions").fetchall()]
    sent = 0
    payload = json.dumps({"title": title, "body": body, "url": url})
    for raw in subs:
        sub = json.loads(raw)
        try:
            webpush(sub, payload, vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": VAPID_SUBJECT}, ttl=6 * 3600)
            sent += 1
        except WebPushException as err:
            status = getattr(err.response, "status_code", None)
            if status in (404, 410):
                delete_subscription(sub["endpoint"])
            else:
                log.warning("Web Push nieudany: %s", err)
    return sent


def _once(conn, key):
    """True, jeśli powiadomienie o danym kluczu nie było jeszcze wysłane (i oznacza je jako wysłane)."""
    if conn.execute("SELECT 1 FROM notifications_sent WHERE key=?", (key,)).fetchone():
        return False
    conn.execute("INSERT INTO notifications_sent(key, sent_at) VALUES(?,?)",
                 (key, datetime.now().isoformat(timespec="seconds")))
    return True


def collect_alerts():
    """Zbiera nowe zdarzenia: seria osiągnęła X, wynik meczu obstawionego (ręcznie lub w symulacji)."""
    from .services import live_state

    alerts = []
    with db.session() as conn:
        strategies = [dict(r) for r in conn.execute("SELECT * FROM strategies WHERE watched=1").fetchall()]
        for st in strategies:
            code = st["league"]
            s = analysis.summary(code)
            if not s or not s.get("n"):
                continue
            name = f"{BY_CODE[code].country} – {BY_CODE[code].name}"
            p = strategy.Params.from_row(st)
            if s["current_streak"] >= p.threshold:
                last_draw = s["last_draw"]["date"] if s["last_draw"] else "brak"
                if _once(conn, f"streak:{code}:{last_draw}"):
                    nx = s["next"][0] if s["next"] else None
                    nxt = f" Następny mecz: {nx['home']} – {nx['away']} ({nx['date']} {nx['time']})." if nx else ""
                    alerts.append((f"{name}: {s['current_streak']} meczów bez remisu",
                                   f"Seria osiągnęła próg X={p.threshold}. Stawka startowa {p.stake(1):.2f} zł.{nxt}",
                                   f"/liga/{code}"))
            if st["active"]:
                live = live_state(st)
                for b in live["result"].bets[-3:]:
                    if _once(conn, f"paper:{code}:{b['date']}:{b['home']}"):
                        verdict = f"REMIS – wygrana {b['profit']:+.2f} zł" if b["won"] else f"brak remisu – strata {b['stake']:.2f} zł"
                        nxt = live["action"]
                        tail = f" Następna stawka: {nxt['stake']:.2f} zł." if nxt.get("bet") else ""
                        alerts.append((f"{name}: {b['home']} {b['score']} {b['away']}",
                                       f"Krok {b['step']}: {verdict}.{tail}", f"/liga/{code}"))
        for bet in conn.execute("SELECT * FROM bets WHERE status IN ('won','lost')").fetchall():
            if _once(conn, f"bet:{bet['id']}:{bet['status']}"):
                verdict = (f"wygrana {bet['stake'] * (1 - bet['tax']) * bet['odds'] - bet['stake']:+.2f} zł" if bet["status"] == "won"
                           else f"przegrana −{bet['stake']:.2f} zł")
                alerts.append((f"Rozliczono zakład: {bet['home']} – {bet['away']}", verdict.capitalize(), "/zaklady"))
    return alerts


def check_and_notify(send=True):
    alerts = collect_alerts()
    sent = 0
    if send:
        for title, body, url in alerts:
            sent += send_all(title, body, url)
    return {"alerts": len(alerts), "pushes": sent, "details": [a[0] for a in alerts]}
