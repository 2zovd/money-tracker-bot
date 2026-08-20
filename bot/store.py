"""Per-user settings store (SQLite).

Maps a Telegram user id to their own Google Sheet (and, later, per-user currency).
One row per user. A fresh sqlite3 connection is opened per call — the queries are
tiny and this keeps things safe across the bot's worker threads without a pool.
"""
import os
import sqlite3
from datetime import datetime

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    sheet_id        TEXT NOT NULL,
    currency_symbol TEXT,
    currency_code   TEXT,
    created_at      TEXT
)
"""


def _conn():
    path = config.DB_FILE
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _conn() as conn:
        conn.execute(_SCHEMA)


def get(user_id: int):
    """The user's row as a dict, or None if not connected."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_sheet(user_id: int):
    row = get(user_id)
    return row["sheet_id"] if row else None


def is_connected(user_id: int) -> bool:
    return get_sheet(user_id) is not None


def set_sheet(user_id: int, sheet_id: str):
    """Connect (or re-point) a user to a spreadsheet. Keeps created_at on updates."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, sheet_id, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET sheet_id = excluded.sheet_id",
            (user_id, sheet_id, datetime.now().isoformat(timespec="seconds")),
        )


def seed(user_id: int, sheet_id: str):
    """Insert a mapping only if the user has none yet (idempotent migration helper)."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, sheet_id, created_at) VALUES (?, ?, ?)",
            (user_id, sheet_id, datetime.now().isoformat(timespec="seconds")),
        )


def disconnect(user_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
