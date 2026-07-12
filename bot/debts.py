"""Debt tracking: pure parsing/formatting/selection logic (no network, covered by tests).

A debt is either "lent" (I gave money, the person owes me) or "borrowed" (I took money,
I owe the person). Repayments reduce the remaining balance of one specific debt, so a
person can have several open debts at once without them mixing together."""
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import config, strings as s

SYM = config.CURRENCY_SYMBOL

# /debt <action> <person> <amount> [note...] — action verbs, with common synonyms so the
# text command isn't brittle to the exact wording.
ACTIONS = {
    "дал": "lend", "одолжил": "lend", "занёс": "lend",
    "занял": "borrow", "взял": "borrow",
    "вернул": "repay_borrowed", "отдал": "repay_borrowed", "погасил": "repay_borrowed",
    "вернули": "repay_lent", "отдали": "repay_lent", "погасили": "repay_lent",
}

CANCEL_WORDS = ("cancel", "отмена", "стоп", "stop")

CB_PREFIX = "debt"
CB_CANCEL = f"{CB_PREFIX}:cancel"


def action_callback(action: str) -> str:
    return f"{CB_PREFIX}:action:{action}"


def person_callback(name: str) -> str:
    return f"{CB_PREFIX}:person:{name}"


USAGE = s.DEBT_USAGE


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
        raise ValueError(s.UNKNOWN_ACTION.format(action=args[0], usage=USAGE))
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
        raise ValueError(s.NO_AMOUNT_DEBT.format(usage=USAGE))
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
    verb = s.VERB_OWES_YOU if direction == "lent" else s.VERB_YOU_OWE
    tail = f" ({note})" if note else ""
    return s.DEBT_CREATED.format(person=person, verb=verb, amount=amount, sym=SYM, tail=tail)


def format_open_list(debts: list) -> str:
    """/долги with no argument: everyone's open balances."""
    if not debts:
        return s.NO_OPEN_DEBTS
    lent = [d for d in debts if d["direction"] == "lent"]
    borrowed = [d for d in debts if d["direction"] == "borrowed"]

    def by_person(items):
        totals = {}
        for d in items:
            totals[d["person"]] = totals.get(d["person"], 0.0) + d["remaining"]
        return sorted(totals.items(), key=lambda x: -x[1])

    lines = []
    if lent:
        lines.append(s.OWED_TO_YOU)
        lines += [f"  {amt:8.2f} {SYM}  {p}" for p, amt in by_person(lent)]
    if borrowed:
        lines.append(s.YOU_OWE)
        lines += [f"  {amt:8.2f} {SYM}  {p}" for p, amt in by_person(borrowed)]
    net = sum(d["remaining"] for d in lent) - sum(d["remaining"] for d in borrowed)
    sign = "+" if net >= 0 else "-"
    lines.append(s.NET_LINE.format(sign=sign, amount=abs(net), sym=SYM))
    return "\n".join(lines)


def format_person_history(person: str, debts: list) -> str:
    """/долги <name>: this person's debts, open and closed, newest first."""
    if not debts:
        return s.NO_DEBTS_FOR_PERSON.format(person=person)
    lines = [f"{person}:"]
    for d in debts:
        tag = "open" if d["status"] == "open" else "closed"
        verb = s.VERB_OWES_YOU if d["direction"] == "lent" else s.VERB_YOU_OWE
        lines.append(f"  [{tag}] {verb} — {_line(d)} · {d['date']}")
    return "\n".join(lines)


def format_repay_choices(debts: list, person: str) -> str:
    lines = [s.REPAY_CHOICES_HEADER.format(person=person, n=len(debts))]
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
    msg = s.REPAY_RESULT.format(paid=paid, remaining=max(debt["remaining"], 0), sym=SYM)
    if debt["remaining"] <= 0:
        msg += s.DEBT_CLOSED
        if debt["remaining"] < 0:
            msg += s.OVERPAID.format(amount=-debt["remaining"], sym=SYM)
    return msg


def format_closed_list(closed: list) -> str:
    """/debts closed: fully repaid debts, newest first."""
    if not closed:
        return s.NO_CLOSED_DEBTS
    lines = [s.CLOSED_DEBTS_HEADER]
    for d in sorted(closed, key=lambda x: x["date"], reverse=True):
        verb = s.VERB_OWED_YOU if d["direction"] == "lent" else s.VERB_YOU_OWED
        tail = f" ({d['note']})" if d.get("note") else ""
        lines.append(f"  {d['person']} {verb} {d['amount']:.2f} {SYM}{tail} · {d['date']}")
    return "\n".join(lines)


# ---- guided /debt menu: action buttons -> person buttons (or free text) -> amount -> note ----
def action_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(s.BTN_LEND, callback_data=action_callback("lend")),
         InlineKeyboardButton(s.BTN_BORROW, callback_data=action_callback("borrow"))],
        [InlineKeyboardButton(s.BTN_REPAY_BORROWED, callback_data=action_callback("repay_borrowed")),
         InlineKeyboardButton(s.BTN_REPAY_LENT, callback_data=action_callback("repay_lent"))],
    ]
    return InlineKeyboardMarkup(rows)


def person_keyboard(persons: list) -> InlineKeyboardMarkup:
    """One button per known person (tap to pick), plus Cancel. Typing a name always works too."""
    rows = [[InlineKeyboardButton(p, callback_data=person_callback(p))] for p in persons]
    rows.append([InlineKeyboardButton(s.BTN_CANCEL, callback_data=CB_CANCEL)])
    return InlineKeyboardMarkup(rows)
