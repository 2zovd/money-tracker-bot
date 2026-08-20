"""Per-user store (SQLite).

Two tables, deliberately separate: `users` maps a Telegram user to their own Google
Sheet, `access` records whether that user is allowed to use the bot at all. Blocking
someone must not lose their sheet mapping, and a pending user has no sheet yet.
A fresh sqlite3 connection is opened per call — the queries are tiny and this keeps
things safe across the bot's worker threads without a pool.
"""
import os
import sqlite3
from datetime import datetime

from . import access, config

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


_ACCESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS access (
    user_id      INTEGER PRIMARY KEY,
    status       TEXT NOT NULL,
    username     TEXT,
    requested_at TEXT,
    decided_at   TEXT
)
"""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def init():
    with _conn() as conn:
        conn.execute(_SCHEMA)
        conn.execute(_ACCESS_SCHEMA)


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
            (user_id, sheet_id, _now()),
        )


def seed(user_id: int, sheet_id: str):
    """Insert a mapping only if the user has none yet (idempotent migration helper)."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, sheet_id, created_at) VALUES (?, ?, ?)",
            (user_id, sheet_id, _now()),
        )


def disconnect(user_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))


# ---- access control ----
def access_status(user_id: int):
    """'pending' | 'approved' | 'blocked', or None if the user is unknown."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT status FROM access WHERE user_id = ?", (user_id,)).fetchone()
    return row["status"] if row else None


def request_access(user_id: int, username: str = "") -> str:
    """File a request for an unknown user. Never downgrades an existing decision —
    returns the status that is in force afterwards."""
    current = access_status(user_id)
    if current:
        return current
    with _conn() as conn:
        conn.execute(
            "INSERT INTO access (user_id, status, username, requested_at) VALUES (?, ?, ?, ?)",
            (user_id, access.PENDING, username, _now()))
    return access.PENDING


def set_access(user_id: int, status: str, username: str = ""):
    """Approve or block a user (also works for someone who never asked)."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO access (user_id, status, username, requested_at, decided_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET status = excluded.status, "
            "decided_at = excluded.decided_at",
            (user_id, status, username, _now(), _now()))


def approve_seed(user_id: int, username: str = ""):
    """Mark a user approved only if they have no record yet (for ALLOWED_USER_ID)."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO access (user_id, status, username, requested_at, decided_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, access.APPROVED, username, _now(), _now()))


def list_access(status: str = None) -> list:
    """All access rows, pending first so the admin sees what needs a decision."""
    sql = "SELECT * FROM access"
    params = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY status = 'pending' DESC, requested_at"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
