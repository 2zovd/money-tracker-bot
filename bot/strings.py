"""All user-facing text in one place.

Everything the bot shows to the user lives here as a constant or a small format
function. To translate the bot, edit the values in this file — nothing else
needs to change. Keep placeholders ({name}, {amount}, ...) intact when you
translate a template.
"""

# ---- generic yes/no ----
ASK_YES_NO = "Please answer “yes” or “no”."
CANCELLED = "Cancelled."

# ---- expense flow ----
NO_AMOUNT = "Couldn't read the amount. E.g. “water 5 eur” or “65 fuel”."
ASK_FUEL_PRICE = "Price per liter? (e.g. 1.65) — or “-” to skip."
ASK_PLACE = "Where? store / market / other — or “-”."
BAD_FUEL_PRICE = "Couldn't read the number. Price per liter, e.g. 1.65 — or “-”."
NO_EXPENSE_PARSED = "Couldn't read any expense. Example: “water 5 eur”."
CONFIRM_SAVE_ALL = "Save all? yes / no"
SAVED_N_EXPENSES = "Saved {n} expense(s)."
CANCELLED_NOTHING_SAVED = "Cancelled, nothing saved."
SAVED_ONE_EXPENSE = "Saved: {line}"

# ---- income flow ----
NO_INCOME_PARSED = "Couldn't read the income. Example: “+4000 salary”."
CONFIRM_SAVE_INCOME = "Save to income? yes / no"
SAVED_INCOME = "Saved income ({n} item(s)) to “{worksheet}”."
CANCELLED_INCOME_NOT_SAVED = "Cancelled, income not saved."
NO_INCOME_THIS_MONTH = "{ym}: no income yet. Example: “+4000 salary”."

# ---- summaries ----
NO_EXPENSES_FOR = "{title}: no expenses."
NO_INCOME_OR_EXPENSES = "No income or expenses recorded yet."
UNKNOWN_CATEGORY = "Unknown category. Categories:\n{list}"
CATEGORY_USAGE = "Usage: /category <name>\n\nCategories:\n{list}"
NO_EXPENSES_FOR_CATEGORY = "{category}: no expenses yet."
BAD_DAY_ARG = "Date as YYYY-MM-DD, e.g. /day 2026-07-03"
SUMMARY_MONTH_TITLE = "Summary {ym}"
SUMMARY_DAY_TITLE = "Day {iso}"
SUMMARY_WEEK_TITLE = "Week {start} — {end}"
CATEGORY_HISTORY_HEADER = "{category} — last {n} month(s):"
MONTHS_HISTORY_HEADER = "Income vs. expenses — last {n} month(s):"
INCOME_MONTH_HEADER = "Income {ym}: {total:.2f} {sym}\n"

# ---- undo ----
NOTHING_TO_DELETE = "Nothing to delete."
DELETED = "Deleted: {summary}"

# ---- voice ----
VOICE_DISABLED = "Voice input is disabled (see README) — please type instead."

# ---- errors ----
ERROR = "Error: {error}"

# ---- debts: prompts ----
ACTION_PROMPTS = {
    "lend": "You lent money — who to?",
    "borrow": "You borrowed money — from who?",
    "repay_borrowed": "Repaying a debt — to who?",
    "repay_lent": "Someone repaid you — who?",
}
ASK_AMOUNT_FOR = "{name} — how much?"
ASK_AMOUNT = "How much?"
ASK_NOTE = "Note? (or “-” to skip)"
BAD_AMOUNT = "Couldn't read the amount, try again."
NO_OPEN_DEBT_FOR = "No open debt found for {person}."
NO_OPEN_DEBTS_DIRECTION = "No open debts in that direction."
SESSION_EXPIRED = "Session expired — start again with /debt."
ASK_DEBT_NUMBER = "Please reply with the debt number."

DEBT_USAGE = (
    "Usage:\n"
    "  /debt дал <name> <amount> [note] — you lent money, they owe you\n"
    "  /debt занял <name> <amount> [note] — you borrowed money, you owe them\n"
    "  /debt вернул <name> <amount> [note] — you repaid what you owed them\n"
    "  /debt вернули <name> <amount> [note] — they repaid what they owed you\n\n"
    "Or just /debt with no arguments for a guided menu."
)
UNKNOWN_ACTION = "Unknown action “{action}”.\n\n{usage}"
NO_AMOUNT_DEBT = "Couldn't read the amount.\n\n{usage}"

# ---- debts: results / listings ----
DEBT_CREATED = "Saved: {person} {verb} {amount:.2f} {sym}{tail}"
VERB_OWES_YOU = "owes you"
VERB_YOU_OWE = "you owe"
NO_OPEN_DEBTS = "No open debts."
OWED_TO_YOU = "Owed to you:"
YOU_OWE = "You owe:"
NET_LINE = "\nNet: {sign}{amount:.2f} {sym}"
NO_DEBTS_FOR_PERSON = "{person}: no debts recorded."
REPAY_CHOICES_HEADER = "{person} has {n} open debts — which one?"
REPAY_RESULT = "Recorded {paid:.2f} {sym} repayment. Remaining: {remaining:.2f} {sym}."
DEBT_CLOSED = " Debt closed."
OVERPAID = " (overpaid by {amount:.2f} {sym})"
NO_CLOSED_DEBTS = "No closed debts yet."
CLOSED_DEBTS_HEADER = "Closed debts:"
VERB_OWED_YOU = "owed you"
VERB_YOU_OWED = "you owed"

# ---- debts: guided-menu buttons ----
BTN_LEND = "➕ I lent"
BTN_BORROW = "➕ I borrowed"
BTN_REPAY_BORROWED = "↩️ I repaid"
BTN_REPAY_LENT = "↩️ They repaid me"
BTN_CANCEL = "✖ Cancel"

# ---- /start /help ----
HELP_TEXT = (
    "I log your expenses into a budget tracker sheet.\n\n"
    "One line: “water 5 eur”, “65 fuel”, “groceries store 19.21”.\n"
    "A batch — several expenses, one per line, optionally with a date:\n"
    "  yesterday\n  1) lunch cafe 12.1\n  2) groceries 23.49\n"
    "I understand “yesterday / day before yesterday / today / DD.MM”. "
    "You can also send a receipt photo or a voice message.\n\n"
    "Income — prefix with “+”: “+4000 salary”, “+150 freelance refund”. "
    "Goes to a separate sheet.\n\n"
    "Debts:\n"
    "  /debt — guided menu (buttons): pick lend/borrow/repay, then who, amount, note\n"
    "  /debt дал <name> <amount> [note] — you lent money (also: одолжил)\n"
    "  /debt занял <name> <amount> [note] — you borrowed money (also: взял)\n"
    "  /debt вернул <name> <amount> [note] — you repaid what you owed "
    "(also: отдал, погасил)\n"
    "  /debt вернули <name> <amount> [note] — they repaid what they owed you\n"
    "  /debts [name] — open balances, or one person's history\n"
    "  /debts closed [name] — fully repaid debts\n\n"
    "/day /week /month — expense summaries   /category <name> — monthly trend for one category\n"
    "/months — income vs. expenses per month\n"
    "/income — income this month   /undo — delete the last entry"
)

# ---- bot command menu (shown in Telegram's "/" command list) ----
# Kept short on purpose: the command itself already says what it does,
# this is just the one-line hint next to it.
COMMAND_DESCRIPTIONS = [
    ("day", "Expenses for a day"),
    ("week", "Expenses this week"),
    ("month", "Expenses this month"),
    ("category", "Trend for one category"),
    ("months", "Income vs. expenses"),
    ("income", "Income this month"),
    ("debt", "Lend / borrow / repay"),
    ("debts", "Debt balances"),
    ("undo", "Delete last entry"),
    ("help", "How to use the bot"),
]
