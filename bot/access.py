"""Access control: pure status/keyboard/format logic (no network, covered by tests).

The bot spends the owner's Anthropic key, so access is closed by default: an unknown
user's first message files a request, and an admin approves or blocks it from Telegram.
This module knows the statuses, the callback wire format and how to render a user list;
the rows themselves live in bot/store.py."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import strings as s

PENDING = "pending"
APPROVED = "approved"
BLOCKED = "blocked"

CB_PREFIX = "acc"
_ACTIONS = {"approve": APPROVED, "block": BLOCKED}


def callback_data(action: str, user_id: int) -> str:
    return f"{CB_PREFIX}:{action}:{user_id}"


def parse_callback(data: str):
    """('approved'|'blocked', user_id) for a well-formed button, else None."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != CB_PREFIX or parts[1] not in _ACTIONS:
        return None
    try:
        return _ACTIONS[parts[1]], int(parts[2])
    except ValueError:
        return None


def parse_users_args(args):
    """('approved'|'blocked', user_id) for "/users approve 123", else None."""
    if len(args) != 2 or args[0].lower() not in _ACTIONS:
        return None
    try:
        return _ACTIONS[args[0].lower()], int(args[1])
    except ValueError:
        return None


def decision_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(s.BTN_ACCESS_APPROVE, callback_data=callback_data("approve", user_id)),
        InlineKeyboardButton(s.BTN_ACCESS_BLOCK, callback_data=callback_data("block", user_id)),
    ]])


def describe(row: dict) -> str:
    """One line for the admin's user list."""
    who = row.get("username") or str(row["user_id"])
    return f"{row['status']:<8} {who} · {row['user_id']}"


def format_user_list(rows) -> str:
    if not rows:
        return s.ACCESS_NO_USERS
    return s.ACCESS_LIST_HEADER + "\n" + "\n".join(describe(r) for r in rows)
