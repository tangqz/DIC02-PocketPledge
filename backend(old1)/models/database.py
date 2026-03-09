# backend/models/database.py
# SQLite schema + tiny migration for Reward/Escrow MVP

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "reward.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table});")
    return any(r["name"] == col for r in cur.fetchall())


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def init_db() -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()

        # ---- users (migrate from old schema if needed) ----
        if not _table_exists(conn, "users"):
            cur.execute(
                """
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    balance_available INTEGER NOT NULL DEFAULT 0,
                    balance_locked INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        else:
            # old schema may have: (user_id, balance)
            if _has_column(conn, "users", "balance") and not _has_column(
                conn, "users", "balance_available"
            ):
                cur.execute(
                    "ALTER TABLE users ADD COLUMN balance_available INTEGER NOT NULL DEFAULT 0"
                )
                cur.execute(
                    "ALTER TABLE users ADD COLUMN balance_locked INTEGER NOT NULL DEFAULT 0"
                )
                # backfill
                cur.execute(
                    "UPDATE users SET balance_available = balance WHERE balance_available = 0"
                )
            # ensure columns exist
            if not _has_column(conn, "users", "balance_available"):
                cur.execute(
                    "ALTER TABLE users ADD COLUMN balance_available INTEGER NOT NULL DEFAULT 0"
                )
            if not _has_column(conn, "users", "balance_locked"):
                cur.execute(
                    "ALTER TABLE users ADD COLUMN balance_locked INTEGER NOT NULL DEFAULT 0"
                )

        # ---- sessions ----
        if not _table_exists(conn, "sessions"):
            cur.execute(
                """
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    duration_sec INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    deposit INTEGER NOT NULL,
                    penalty_target TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    score INTEGER,
                    refund_amount INTEGER,
                    penalty_amount INTEGER,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )

        # ---- session_events (evidence / telemetry) ----
        # 用来挂“屏幕/摄像头/语音”等到某个 session 上
        if not _table_exists(conn, "session_events"):
            cur.execute(
                """
                CREATE TABLE session_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    ts INTEGER NOT NULL,              -- unix timestamp (seconds)
                    event_type TEXT NOT NULL,         -- heartbeat/screen/webcam/audio/manual_note
                    payload_json TEXT NOT NULL,       -- JSON string
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )
            # 按 session_id 拉一段时间内的事件
            cur.execute(
                "CREATE INDEX idx_session_events_session_ts ON session_events(session_id, ts)"
            )

        # ---- ledger (if legacy exists, rename it and create new) ----
        if _table_exists(conn, "ledger"):
            # detect legacy: it had column event_type (old) and lacked kind
            legacy = _has_column(conn, "ledger", "event_type") and not _has_column(
                conn, "ledger", "kind"
            )
            if legacy:
                # keep the old data for debugging
                cur.execute("ALTER TABLE ledger RENAME TO ledger_legacy")

        if not _table_exists(conn, "ledger"):
            cur.execute(
                """
                CREATE TABLE ledger (
                    event_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    user_id INTEGER NOT NULL,
                    session_id TEXT,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    available_before INTEGER NOT NULL,
                    available_after INTEGER NOT NULL,
                    locked_before INTEGER NOT NULL,
                    locked_after INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    evidence_id TEXT,
                    counterparty_user_id INTEGER,
                    target TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
                """
            )

        conn.commit()
    finally:
        conn.close()