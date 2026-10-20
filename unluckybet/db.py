"""Warstwa bazy danych: SQLite lokalnie, PostgreSQL gdy ustawiono DATABASE_URL.

Zapytania w kodzie używają placeholderów `?` – dla PostgreSQL są zamieniane na `%s`.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("UNLUCKYBET_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = Path(os.environ.get("UNLUCKYBET_DB", DATA_DIR / "unluckybet.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

_ID = "BIGSERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS matches (
    id {_ID},
    league TEXT NOT NULL,
    season TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL DEFAULT '',
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    hg INTEGER, ag INTEGER,
    res TEXT NOT NULL,
    odds_d_avg REAL, odds_d_max REAL, odds_d_b365 REAL,
    kickoff_utc TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'football-data',
    UNIQUE(league, date, home, away)
);
CREATE INDEX IF NOT EXISTS ix_matches_league ON matches(league, date, time);

CREATE TABLE IF NOT EXISTS fixtures (
    id {_ID},
    league TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL DEFAULT '',
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    odds_d_avg REAL, odds_d_max REAL, odds_d_b365 REAL,
    kickoff_utc TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'upcoming',
    UNIQUE(league, date, home, away)
);

CREATE TABLE IF NOT EXISTS strategies (
    league TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'draw',
    side TEXT NOT NULL DEFAULT '',
    watched INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 0,
    threshold INTEGER NOT NULL DEFAULT 5,
    base_stake REAL NOT NULL DEFAULT 10,
    multiplier REAL NOT NULL DEFAULT 2,
    max_steps INTEGER NOT NULL DEFAULT 8,
    bankroll REAL NOT NULL DEFAULT 0,
    odds_mode TEXT NOT NULL DEFAULT 'avg',
    fixed_odds REAL NOT NULL DEFAULT 3.2,
    tax REAL NOT NULL DEFAULT 0.12,
    start_date TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (league, market)
);

CREATE TABLE IF NOT EXISTS bets (
    id {_ID},
    league TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'draw',
    match_date TEXT NOT NULL,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    stake REAL NOT NULL,
    odds REAL NOT NULL,
    tax REAL NOT NULL DEFAULT 0.12,
    step INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS notifications_sent (
    key TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Conn:
    """Cienka nakładka ujednolicająca sqlite3 i psycopg."""

    def __init__(self):
        if IS_PG:
            import psycopg
            from psycopg.rows import dict_row

            self.raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=20)
        else:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.raw = sqlite3.connect(DB_PATH, timeout=30)
            self.raw.row_factory = sqlite3.Row
            self.raw.execute("PRAGMA journal_mode=WAL")

    @staticmethod
    def _sql(sql):
        return sql.replace("?", "%s") if IS_PG else sql

    def execute(self, sql, params=()):
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(self._sql(sql), params)
            return cur
        return self.raw.execute(sql, params)

    def executemany(self, sql, rows):
        rows = list(rows)
        if not rows:
            return
        if IS_PG:
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), rows)
        else:
            self.raw.executemany(sql, rows)

    def executescript(self, script):
        if IS_PG:
            with self.raw.cursor() as cur:
                for stmt in script.split(";"):
                    if stmt.strip():
                        cur.execute(stmt)
        else:
            self.raw.executescript(script)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def connect():
    return Conn()


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


MIGRATIONS = [
    ("strategies", "tax", "REAL NOT NULL DEFAULT 0.12"),
    ("bets", "tax", "REAL NOT NULL DEFAULT 0.12"),
    ("matches", "kickoff_utc", "TEXT NOT NULL DEFAULT ''"),
    ("matches", "event_id", "TEXT NOT NULL DEFAULT ''"),
    ("matches", "source", "TEXT NOT NULL DEFAULT 'football-data'"),
    ("fixtures", "kickoff_utc", "TEXT NOT NULL DEFAULT ''"),
    ("fixtures", "event_id", "TEXT NOT NULL DEFAULT ''"),
    ("fixtures", "status", "TEXT NOT NULL DEFAULT 'upcoming'"),
    ("strategies", "market", "TEXT NOT NULL DEFAULT 'draw'"),
    ("strategies", "side", "TEXT NOT NULL DEFAULT ''"),
    ("bets", "market", "TEXT NOT NULL DEFAULT 'draw'"),
]


def init_db():
    with session() as conn:
        conn.executescript(SCHEMA)
    for table, column, ddl in MIGRATIONS:
        conn = connect()
        try:
            conn.execute(f"SELECT {column} FROM {table} LIMIT 1").fetchall()
        except Exception:  # noqa: BLE001 - brak kolumny w starszej bazie
            conn.raw.rollback()
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()
        finally:
            conn.close()
    # Indeks po migracji kolumn (CREATE TABLE IF NOT EXISTS nie dodaje ich do starej tabeli).
    with session() as conn:
        conn.execute("CREATE INDEX IF NOT EXISTS ix_matches_kickoff ON matches(league, kickoff_utc)")
    _migrate_strategies_pk()


def _migrate_strategies_pk():
    """Stare bazy miały PRIMARY KEY(league) – przebuduj na (league, market)."""
    conn = connect()
    try:
        if IS_PG:
            row = conn.execute(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_name='strategies' AND constraint_type='PRIMARY KEY'"
            ).fetchone()
            # Jeśli PK to tylko league – przebuduj
            cols = conn.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) "
                "WHERE i.indrelid='strategies'::regclass AND i.indisprimary"
            ).fetchall()
            names = [c["attname"] for c in cols] if cols else []
            if names == ["league"]:
                conn.execute("ALTER TABLE strategies DROP CONSTRAINT strategies_pkey")
                conn.execute("ALTER TABLE strategies ADD PRIMARY KEY (league, market)")
                conn.commit()
        else:
            # SQLite: sprawdź sql tabeli
            row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='strategies'").fetchone()
            sql = (row["sql"] or "") if row else ""
            if sql and "PRIMARY KEY (league, market)" not in sql and "PRIMARY KEY(league, market)" not in sql:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS strategies_new (
                    league TEXT NOT NULL,
                    market TEXT NOT NULL DEFAULT 'draw',
                    side TEXT NOT NULL DEFAULT '',
                    watched INTEGER NOT NULL DEFAULT 1,
                    active INTEGER NOT NULL DEFAULT 0,
                    threshold INTEGER NOT NULL DEFAULT 5,
                    base_stake REAL NOT NULL DEFAULT 10,
                    multiplier REAL NOT NULL DEFAULT 2,
                    max_steps INTEGER NOT NULL DEFAULT 8,
                    bankroll REAL NOT NULL DEFAULT 0,
                    odds_mode TEXT NOT NULL DEFAULT 'avg',
                    fixed_odds REAL NOT NULL DEFAULT 3.2,
                    tax REAL NOT NULL DEFAULT 0.12,
                    start_date TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (league, market)
                );
                INSERT OR IGNORE INTO strategies_new
                    (league, market, side, watched, active, threshold, base_stake, multiplier,
                     max_steps, bankroll, odds_mode, fixed_odds, tax, start_date)
                SELECT league, COALESCE(market,'draw'), COALESCE(side,''), watched, active, threshold,
                       base_stake, multiplier, max_steps, bankroll, odds_mode, fixed_odds, tax, start_date
                FROM strategies;
                DROP TABLE strategies;
                ALTER TABLE strategies_new RENAME TO strategies;
                """)
                conn.commit()
    except Exception:  # noqa: BLE001
        try:
            conn.raw.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def get_meta(key, default=None):
    with session() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_meta(key, value):
    with session() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def backend_name():
    return "PostgreSQL" if IS_PG else f"SQLite ({DB_PATH})"
