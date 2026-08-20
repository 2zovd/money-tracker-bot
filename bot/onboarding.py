"""Guided setup wizard: pure step/keyboard logic (no network, covered by tests).

A new user is walked through four steps — welcome, copy the template, share it with the
service account, send the link — after which the bot validates access and connects the
sheet. State lives in ctx.user_data["onboarding"]; this module only knows the step graph,
the buttons, and how to read a sheet id out of a pasted link."""
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import config, strings as s

# Steps, in order. The wizard advances one step per user action (button or link).
STEP_WELCOME = "welcome"
STEP_COPY = "copy"
STEP_GRANT = "grant"
STEP_LINK = "link"

CB_PREFIX = "onb"
CB_START = f"{CB_PREFIX}:start"
CB_COPIED = f"{CB_PREFIX}:copied"
CB_GRANTED = f"{CB_PREFIX}:granted"
CB_CANCEL = f"{CB_PREFIX}:cancel"

# Which button click moves us from one step to the next.
_ADVANCE = {
    (STEP_WELCOME, CB_START): STEP_COPY,
    (STEP_COPY, CB_COPIED): STEP_GRANT,
    (STEP_GRANT, CB_GRANTED): STEP_LINK,
}


def next_step(step: str, callback: str):
    """The step a button click leads to, or None if the click doesn't apply to this step."""
    return _ADVANCE.get((step, callback))


def parse_sheet_id(text: str):
    """Extract a spreadsheet id from a full URL or accept a bare id; None if neither.
    Google ids are long url-safe tokens, so a bare id must be at least 20 such chars."""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", text):
        return text
    return None


# ---- keyboards ----
def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(s.BTN_ONB_START, callback_data=CB_START)],
        [InlineKeyboardButton(s.BTN_ONB_CANCEL, callback_data=CB_CANCEL)],
    ])


def copy_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if config.TEMPLATE_SHEET_URL:
        rows.append([InlineKeyboardButton(s.BTN_ONB_OPEN_TEMPLATE, url=config.TEMPLATE_SHEET_URL)])
    rows.append([InlineKeyboardButton(s.BTN_ONB_COPIED, callback_data=CB_COPIED)])
    rows.append([InlineKeyboardButton(s.BTN_ONB_CANCEL, callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(rows)


def grant_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(s.BTN_ONB_GRANTED, callback_data=CB_GRANTED)],
        [InlineKeyboardButton(s.BTN_ONB_CANCEL, callback_data=CB_CANCEL)],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(s.BTN_ONB_CANCEL, callback_data=CB_CANCEL)]])
