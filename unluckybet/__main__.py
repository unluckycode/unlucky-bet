"""Polecenia: python -m unluckybet [serve|refresh|notify|vapid|summary]"""

import argparse
import os


def main():
    parser = argparse.ArgumentParser(prog="python -m unluckybet")
    sub = parser.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="uruchom portal lokalnie")
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    s.add_argument("--host", default="127.0.0.1")
    r = sub.add_parser("refresh", help="odśwież wyniki (FotMob; --full także football-data)")
    r.add_argument("--full", action="store_true", help="dodatkowo pobierz historię/kursy z football-data.co.uk")
    r.add_argument("--history", action="store_true", help="tylko football-data")
    r.add_argument("--leagues", default="", help="kody lig po przecinku (domyślnie obserwowane / pasujące)")
    sub.add_parser("notify", help="sprawdź alerty i wyślij powiadomienia push")
    sub.add_parser("vapid", help="wygeneruj klucze VAPID do powiadomień push")
    sub.add_parser("summary", help="wypisz podsumowanie lig")
    args = parser.parse_args()

    if args.cmd == "refresh":
        from . import ingest, live, notify, analysis
        codes = [c.strip() for c in (args.leagues or "").split(",") if c.strip()] or None
        if args.history:
            ingest.refresh(full=args.full, leagues=codes)
        else:
            live.ensure_default_watches()
            live.refresh(codes=codes)
            if args.full:
                from .leagues import LEAGUES
                fd = codes or [lg.code for lg in LEAGUES if lg.fd_code]
                ingest.refresh(full=True, leagues=fd)
        analysis.invalidate()
        print(notify.check_and_notify())
    elif args.cmd == "notify":
        from . import db, notify
        db.init_db()
        print(notify.check_and_notify())
    elif args.cmd == "vapid":
        generate_vapid()
    elif args.cmd == "summary":
        print_summary()
    else:
        from .web import create_app
        port = getattr(args, "port", 5000)
        host = getattr(args, "host", "127.0.0.1")
        create_app().run(host=host, port=port, debug=False, threaded=True)


def generate_vapid():
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    print("Dodaj te zmienne środowiskowe (np. w Render → Environment):\n")
    print(f"VAPID_PUBLIC_KEY={b64(pub)}")
    print(f"VAPID_PRIVATE_KEY={b64(priv)}")
    print("VAPID_SUBJECT=mailto:twoj-email@example.com")


def print_summary():
    from . import analysis, db
    db.init_db()
    rows = sorted(analysis.all_summaries(), key=lambda s: s["overlap_rate"] if s["overlap_rate"] is not None else 9)
    print(f"{'Liga':38} {'nakł.':>6} {'seria':>5} {'remisy':>7} {'rekord':>6}  ostatni wynik")
    for s in rows:
        if not s.get("n"):
            continue
        name = f"{s['league'].country} – {s['league'].name}"
        ov = s["overlap_rate"] * 100 if s["overlap_rate"] is not None else -1
        print(f"{name:38} {ov:5.0f}% {s['current_streak']:5d} {s['draw_rate'] * 100:6.1f}% "
              f"{s['longest']:6d}  {s['last_date']}")


if __name__ == "__main__":
    main()
