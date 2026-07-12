"""Debt tracking: pure parsing/formatting/selection logic (no network, covered by tests).

A debt is either "lent" (I gave money, the person owes me) or "borrowed" (I took money,
I owe the person). Repayments reduce the remaining balance of one specific debt, so a
person can have several open debts at once without them mixing together."""
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import config

SYM = config.CURRENCY_SYMBOL

# /debt <action> <person> <amount> [note...] — action verbs, with common synonyms so the
# text command isn't brittle to the exact wording.
ACTIONS = {
    "дал": "lend", "одолжил": "lend", "занёс": "lend",
    "занял": "borrow", "взял": "borrow",
    "вернул": "repay_borrowed", "отдал": "repay_borrowed", "погасил": "repay_borrowed",
    "вернули": "repay_lent", "отдали": "repay_lent", "погасили": "repay_lent",
}

ACTION_PROMPTS = {
    "lend": "You lent money — who to?",
    "borrow": "You borrowed money — from who?",
    "repay_borrowed": "Repaying a debt — to who?",
    "repay_lent": "Someone repaid you — who?",
}

CANCEL_WORDS = ("cancel", "отмена", "стоп", "stop")

CB_PREFIX = "debt"
CB_CANCEL = f"{CB_PREFIX}:cancel"


def action_callback(action: str) -> str:
    return f"{CB_PREFIX}:action:{action}"


def person_callback(name: str) -> str:
    return f"{CB_PREFIX}:person:{name}"


USAGE = (
    "Usage:\n"
    "  /debt дал <name> <amount> [note] — you lent money, they owe you\n"
    "  /debt занял <name> <amount> [note] — you borrowed money, you owe them\n"
    "  /debt вернул <name> <amount> [note] — you repaid what you owed them\n"
    "  /debt вернули <name> <amount> [note] — they repaid what they owed you\n\n"
    "Or just /debt with no arguments for a guided menu."
)


def _num(text):
    m = re.search(r"[-+]?\d+[.,]?\d*", text.replace(",", "."))
    return float(m.group()) if m else None


def parse_debt_command(args: list) -> dict:
    """Parse ctx.args of `/долг <action> <person> <amount> [note...]`.
    Returns {'action', 'person', 'amount', 'note'}. Raises ValueError(message) on bad input."""
    if not args:
        raise ValueError(USAGE)
    action = ACTIONS.get(args[0].lower())
    if not action:
        raise ValueError(f"Unknown action “{args[0]}”.\n\n{USAGE}")
    if len(args) < 3:
        raise ValueError(USAGE)
    person = args[1]
    rest = args[2:]
    amount, amount_idx = None, None
    for i, tok in enumerate(rest):
        n = _num(tok)
        if n is not None:
            amount, amount_idx = n, i
            break
    if amount is None:
        raise ValueError("Couldn't read the amount.\n\n" + USAGE)
    note_tokens = rest[:amount_idx] + rest[amount_idx + 1:]
    return {"action": action, "person": person, "amount": amount,
            "note": " ".join(note_tokens).strip()}


def direction_for_create(action: str) -> str:
    """'lend' -> the new debt's direction is 'lent'; 'borrow' -> 'borrowed'."""
    return {"lend": "lent", "borrow": "borrowed"}[action]


def direction_for_repay(action: str) -> str:
    """Which existing debts a repay action targets."""
    return {"repay_borrowed": "borrowed", "repay_lent": "lent"}[action]


def _line(d) -> str:
    parts = [f"{d['remaining']:.2f} {SYM} left", f"of {d['amount']:.2f} {SYM}"]
    if d.get("note"):
        parts.append(d["note"])
    return " · ".join(parts)


def format_debt_created(direction: str, person: str, amount: float, note: str) -> str:
    verb = "owes you" if direction == "lent" else "you owe"
    tail = f" ({note})" if note else ""
    return f"Saved: {person} {verb} {amount:.2f} {SYM}{tail}"


def format_open_list(debts: list) -> str:
    """/долги with no argument: everyone's open balances."""
    if not debts:
        return "No open debts."
    lent = [d for d in debts if d["direction"] == "lent"]
    borrowed = [d for d in debts if d["direction"] == "borrowed"]

    def by_person(items):
        totals = {}
        for d in items:
            totals[d["person"]] = totals.get(d["person"], 0.0) + d["remaining"]
        return sorted(totals.items(), key=lambda x: -x[1])

    lines = []
    if lent:
        lines.append("Owed to you:")
        lines += [f"  {amt:8.2f} {SYM}  {p}" for p, amt in by_person(lent)]
    if borrowed:
        lines.append("You owe:")
        lines += [f"  {amt:8.2f} {SYM}  {p}" for p, amt in by_person(borrowed)]
    net = sum(d["remaining"] for d in lent) - sum(d["remaining"] for d in borrowed)
    sign = "+" if net >= 0 else "-"
    lines.append(f"\nNet: {sign}{abs(net):.2f} {SYM}")
    return "\n".join(lines)


def format_person_history(person: str, debts: list) -> str:
    """/долги <name>: this person's debts, open and closed, newest first."""
    if not debts:
        return f"{person}: no debts recorded."
    lines = [f"{person}:"]
    for d in debts:
        tag = "open" if d["status"] == "open" else "closed"
        verb = "owes you" if d["direction"] == "lent" else "you owe"
        lines.append(f"  [{tag}] {verb} — {_line(d)} · {d['date']}")
    return "\n".join(lines)


def format_repay_choices(debts: list, person: str) -> str:
    lines = [f"{person} has {len(debts)} open debts — which one?"]
    lines += [f"  {i}) {_line(d)}" for i, d in enumerate(debts, 1)]
    return "\n".join(lines)


def parse_choice_number(text: str, n: int):
    """Parse a 1-based choice out of `n` options, or None if invalid."""
    m = re.match(r"\s*(\d+)\s*$", text)
    if not m:
        return None
    i = int(m.group(1))
    return i - 1 if 1 <= i <= n else None


def format_repay_result(debt: dict, paid: float) -> str:
    msg = f"Recorded {paid:.2f} {SYM} repayment. Remaining: {max(debt['remaining'], 0):.2f} {SYM}."
    if debt["remaining"] <= 0:
        msg += " Debt closed."
        if debt["remaining"] < 0:
            msg += f" (overpaid by {-debt['remaining']:.2f} {SYM})"
    return msg


def format_closed_list(closed: list) -> str:
    """/debts closed: fully repaid debts, newest first."""
    if not closed:
        return "No closed debts yet."
    lines = ["Closed debts:"]
    for d in sorted(closed, key=lambda x: x["date"], reverse=True):
        verb = "owed you" if d["direction"] == "lent" else "you owed"
        tail = f" ({d['note']})" if d.get("note") else ""
        lines.append(f"  {d['person']} {verb} {d['amount']:.2f} {SYM}{tail} · {d['date']}")
    return "\n".join(lines)


# ---- guided /debt menu: action buttons -> person buttons (or free text) -> amount -> note ----
def action_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("➕ Я дал в долг", callback_data=action_callback("lend")),
         InlineKeyboardButton("➕ Я занял", callback_data=action_callback("borrow"))],
        [InlineKeyboardButton("↩️ Я вернул", callback_data=action_callback("repay_borrowed")),
         InlineKeyboardButton("↩️ Мне вернули", callback_data=action_callback("repay_lent"))],
    ]
    return InlineKeyboardMarkup(rows)


def person_keyboard(persons: list) -> InlineKeyboardMarkup:
    """One button per known person (tap to pick), plus Cancel. Typing a name always works too."""
    rows = [[InlineKeyboardButton(p, callback_data=person_callback(p))] for p in persons]
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(rows)
