"""SQLite storage shared by the watcher daemon and the MCP server.

The watcher writes (alerts, heartbeat); the MCP server mostly reads and
manages rules. WAL mode lets both hold the file open at once.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL UNIQUE,
    pattern          TEXT    NOT NULL,
    match_type       TEXT    NOT NULL DEFAULT 'substring',
    case_sensitive   INTEGER NOT NULL DEFAULT 0,
    chat_ids         TEXT,
    exclude_chat_ids TEXT,
    include_outgoing INTEGER NOT NULL DEFAULT 0,
    notify           INTEGER NOT NULL DEFAULT 1,
    enabled          INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL,
    hit_count        INTEGER NOT NULL DEFAULT 0,
    last_hit_at      TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         INTEGER NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    chat_id         INTEGER NOT NULL,
    chat_name       TEXT,
    message_id      INTEGER NOT NULL,
    sender_id       INTEGER,
    sender_name     TEXT,
    text            TEXT,
    matched_excerpt TEXT,
    message_date    TEXT,
    matched_at      TEXT    NOT NULL,
    acked           INTEGER NOT NULL DEFAULT 0,
    verdict         TEXT    NOT NULL DEFAULT 'pending',
    verdict_summary TEXT,
    verdict_reason  TEXT,
    verdict_criteria TEXT,
    severity        TEXT,
    judged_at       TEXT,
    judge_model     TEXT,
    UNIQUE(rule_id, chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_unacked ON alerts(acked, id DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_rule    ON alerts(rule_id, id DESC);

CREATE TABLE IF NOT EXISTS criteria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT    NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL,
    hit_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path(), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added after the first release. Existing DBs get them via migrate();
# fresh ones already have them from SCHEMA, and ADD COLUMN is skipped.
_ADDED_ALERT_COLUMNS = {
    "verdict": "TEXT NOT NULL DEFAULT 'pending'",
    "verdict_summary": "TEXT",
    "verdict_reason": "TEXT",
    "verdict_criteria": "TEXT",
    "severity": "TEXT",
    "judged_at": "TEXT",
    "judge_model": "TEXT",
}


def migrate(conn) -> list[str]:
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(alerts)").fetchall()
    }
    added = []
    for column, decl in _ADDED_ALERT_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE alerts ADD COLUMN {column} {decl}")
            added.append(column)
    # Created after the columns exist, not in SCHEMA, for the reason above.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_alerts_verdict ON alerts(verdict, id DESC)"
    )
    return added


def init() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)
        migrate(conn)


def set_state(conn, key: str, value) -> None:
    conn.execute(
        "INSERT INTO state(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
        "updated_at=excluded.updated_at",
        (key, json.dumps(value), now()),
    )


def get_state(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def state_updated_at(conn, key: str):
    row = conn.execute("SELECT updated_at FROM state WHERE key=?", (key,)).fetchone()
    return row["updated_at"] if row else None


def criterion_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["enabled"] = bool(d["enabled"])
    return d


def alert_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["acked"] = bool(d["acked"])
    if d.get("verdict_criteria"):
        d["verdict_criteria"] = json.loads(d["verdict_criteria"])
    return d


def rule_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("chat_ids", "exclude_chat_ids"):
        d[field] = json.loads(d[field]) if d[field] else None
    for field in ("case_sensitive", "include_outgoing", "notify", "enabled"):
        d[field] = bool(d[field])
    return d
