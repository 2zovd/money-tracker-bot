"""Dialog logic: parse expenses (single or batch), follow-up questions, confirm, write.

Every message shown to the user is English. Data is written to the sheet using the
category names from bot/categories.py so it stays in sync with the tracker."""
import re
import asyncio
import logging
from datetime import date, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from . import sheets, parser, config, debts
from .categories import CATEGORIES, FUEL, GROCERIES, FALLBACK

log = logging.getLogger("expense-bot")

SYM = config.CURRENCY_SYMBOL


# ---- pure helpers (covered by tests) ----
def _num(text):
    m = re.search(r"[-+]?\d+[.,]?\d*", text.replace(",", "."))
    return float(m.group()) if m else None


def _skip(text):
    return text.strip().lower() in (
        "-", "—", "skip", "none", "dunno", "don't know", "no")


def is_yes(text):
    return text.strip().lower() in (
        "yes", "y", "ok", "okay", "yep", "yeah", "sure", "+", "save", "go")


def is_no(text):
    return text.strip().lower() in (
        "no", "n", "nope", "cancel", "-")


_INCOME_KW = (
    "salary", "paycheck", "wage", "bonus", "premium", "freelance", "fee",
    "dividend", "cashback", "refund", "income", "deposit", "payout",
    "advance", "reimbursement",
    "зарплата", "аванс", "премия", "кэшбэк", "кешбэк", "возврат", "доход",
    "депозит", "выплата", "компенсация", "гонорар", "фриланс")


def is_income(text: str) -> bool:
    """Income if the text starts with "+" or the first line contains a marker word."""
    t = text.strip().lower()
    if t.startswith("+"):
        return True
    first = t.splitlines()[0] if t else ""
    return any(k in first for k in _INCOME_KW)


def _income_line(inc) -> str:
    parts = [inc.get("date", ""), f"{float(inc['amount']):.2f} {SYM}",
             inc.get("source", ""), inc.get("note", "")]
    return " · ".join(p for p in parts if p)


def format_income(items) -> str:
    lines = [f"{i}) {_income_line(e)}" for i, e in enumerate(items, 1)]
    total = sum(float(e["amount"]) for e in items)
    lines.append(f"\nTotal income: {total:.2f} {SYM} · {len(items)} item(s)")
    return "\n".join(lines)


def normalize(exp: dict) -> dict:
    exp["category"] = exp.get("category") or FALLBACK
    if exp["category"] not in CATEGORIES:
        exp["category"] = FALLBACK
    if exp["category"] == FUEL and not exp.get("liters") and exp.get("price_per_liter"):
        try:
            exp["liters"] = round(float(exp["amount"]) / float(exp["price_per_liter"]), 2)
        except (TypeError, ZeroDivisionError):
            pass
    return exp


def next_missing(exp: dict):
    """What to ask next: 'fuel' | 'place' | None."""
    if exp["category"] == FUEL and not exp.get("liters") and not exp.get("_fuel_asked"):
        return "fuel"
    if exp["category"] == GROCERIES and not exp.get("place") and not exp.get("_place_asked"):
        return "place"
    return None


def _line(exp) -> str:
    parts = [exp.get("date", ""), f"{float(exp['amount']):.2f} {SYM}", exp["category"]]
    if exp.get("place"):
        parts.append(exp["place"])
    if exp.get("liters"):
        pl = float(exp["amount"]) / float(exp["liters"])
        parts.append(f"{float(exp['liters']):.2f} L ({pl:.2f} {SYM}/L)")
    elif exp.get("method"):
        parts.append(exp["method"])
    if exp.get("note"):
        parts.append(exp["note"])
    return " · ".join(p for p in parts if p)


def format_batch(items) -> str:
    lines = [f"{i}) {_line(e)}" for i, e in enumerate(items, 1)]
    total = sum(float(e["amount"]) for e in items)
    lines.append(f"\nTotal: {total:.2f} {SYM} · {len(items)} expense(s)")
    return "\n".join(lines)


# ---- write/reply (single expense with follow-ups) ----
async def _finalize(update, ctx, exp):
    await asyncio.to_thread(sheets.append_expense, exp)
    ctx.user_data["last_write"] = {"kind": "expense"}
    await update.message.reply_text("Saved: " + _line(exp))


async def _step(update, ctx, exp):
    if exp.get("amount") is None:
        await update.message.reply_text("Couldn't read the amount. E.g. “water 5 eur” or “65 fuel”.")
        return
    exp = normalize(exp)
    need = next_missing(exp)
    if need == "fuel":
        exp["_fuel_asked"] = True
        ctx.user_data["pending"] = exp
        await update.message.reply_text("Price per liter? (e.g. 1.65) — or “-” to skip.")
        return
    if need == "place":
        exp["_place_asked"] = True
        ctx.user_data["pending"] = exp
        await update.message.reply_text("Where? store / market / other — or “-”.")
        return
    ctx.user_data.pop("pending", None)
    await _finalize(update, ctx, exp)


async def _answer_pending(update, ctx, text):
    exp = ctx.user_data["pending"]
    if exp.get("_fuel_asked") and not exp.get("liters"):
        if not _skip(text):
            price = _num(text)
            if not price:
                await update.message.reply_text("Couldn't read the number. Price per liter, e.g. 1.65 — or “-”.")
                return
            exp["price_per_liter"] = price
            exp["liters"] = round(float(exp["amount"]) / price, 2)
    elif exp.get("_place_asked") and not exp.get("place"):
        if not _skip(text):
            exp["place"] = text.strip()
    await _step(update, ctx, exp)


# ---- batch of expenses: confirm before writing ----
async def _route(update, ctx, items):
    items = [normalize(e) for e in items if e.get("amount") is not None]
    if not items:
        await update.message.reply_text("Couldn't read any expense. Example: “water 5 eur”.")
        return
    if len(items) == 1:
        await _step(update, ctx, items[0])
        return
    ctx.user_data["confirm"] = items
    await update.message.reply_text(format_batch(items) + "\n\nSave all? yes / no")


async def _answer_confirm(update, ctx, text):
    if is_yes(text):
        items = ctx.user_data.pop("confirm")
        n = await asyncio.to_thread(sheets.append_many, items)
        ctx.user_data["last_write"] = {"kind": "expense"}
        await update.message.reply_text(f"Saved {n} expense(s).")
    elif is_no(text):
        ctx.user_data.pop("confirm", None)
        await update.message.reply_text("Cancelled, nothing saved.")
    else:
        await update.message.reply_text("Please answer “yes” or “no”.")


# ---- income: confirm before writing to the income sheet ----
async def _route_income(update, ctx, items):
    items = [e for e in items if e.get("amount") is not None]
    if not items:
        await update.message.reply_text("Couldn't read the income. Example: “+4000 salary”.")
        return
    ctx.user_data["confirm_income"] = items
    await update.message.reply_text(format_income(items) + "\n\nSave to income? yes / no")


async def _answer_confirm_income(update, ctx, text):
    if is_yes(text):
        items = ctx.user_data.pop("confirm_income")
        n = await asyncio.to_thread(sheets.append_income_many, items)
        await update.message.reply_text(f"Saved income ({n} item(s)) to “{config.INCOME_WORKSHEET}”.")
    elif is_no(text):
        ctx.user_data.pop("confirm_income", None)
        await update.message.reply_text("Cancelled, income not saved.")
    else:
        await update.message.reply_text("Please answer “yes” or “no”.")


# ---- debts: lend/borrow/repay via /debt, list/history via /debts ----
async def _apply_repayment(update, ctx, debt, amount, note):
    await asyncio.to_thread(sheets.append_repayment, None, debt["id"], amount, note)
    updated = await asyncio.to_thread(sheets.debt_by_id, debt["id"])
    ctx.user_data["last_write"] = {"kind": "repayment"}
    await update.message.reply_text(debts.format_repay_result(updated, amount))


async def _finalize_debt_action(update, ctx, action, person, amount, note):
    if action in ("lend", "borrow"):
        direction = debts.direction_for_create(action)
        await asyncio.to_thread(
            sheets.append_debt, None, person, direction, amount, config.CURRENCY_CODE, note)
        ctx.user_data["last_write"] = {"kind": "debt"}
        await update.message.reply_text(debts.format_debt_created(direction, person, amount, note))
        return

    direction = debts.direction_for_repay(action)
    matches = await asyncio.to_thread(sheets.open_debts, person, direction)
    if not matches:
        await update.message.reply_text(f"No open debt found for {person}.")
        return
    if len(matches) == 1:
        await _apply_repayment(update, ctx, matches[0], amount, note)
        return
    ctx.user_data["pending_repay"] = {
        "debts": matches, "amount": amount, "note": note, "person": person}
    await update.message.reply_text(debts.format_repay_choices(matches, person))


async def _answer_pending_repay(update, ctx, text):
    state = ctx.user_data["pending_repay"]
    idx = debts.parse_choice_number(text, len(state["debts"]))
    if idx is None:
        await update.message.reply_text("Please reply with the debt number.")
        return
    ctx.user_data.pop("pending_repay")
    await _apply_repayment(update, ctx, state["debts"][idx], state["amount"], state["note"])


# ---- guided /debt menu: buttons for action -> person -> typed amount -> typed note ----
async def _ask_person(reply, ctx, action):
    ctx.user_data["debt_wizard"] = {"action": action, "step": "person"}
    if action in ("lend", "borrow"):
        persons = await asyncio.to_thread(sheets.recent_debt_persons)
    else:
        direction = debts.direction_for_repay(action)
        persons = await asyncio.to_thread(sheets.persons_with_open_debt, direction)
        if not persons:
            ctx.user_data.pop("debt_wizard", None)
            await reply("No open debts in that direction.")
            return
    await reply(debts.ACTION_PROMPTS[action], reply_markup=debts.person_keyboard(persons))


async def _start_debt_wizard(update, ctx, action=None):
    async def reply(text, reply_markup=None):
        await update.message.reply_text(text, reply_markup=reply_markup)

    if action is None:
        open_all = await asyncio.to_thread(sheets.open_debts)
        summary = debts.format_open_list(open_all)
        await reply(summary + "\n\nWhat do you want to do?", debts.action_keyboard())
        return
    await _ask_person(reply, ctx, action)


async def on_debt_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _authorized(update):
        await query.answer()
        return
    await query.answer()

    async def reply(text, reply_markup=None):
        await query.edit_message_text(text, reply_markup=reply_markup)

    data = query.data
    if data == debts.CB_CANCEL:
        ctx.user_data.pop("debt_wizard", None)
        await reply("Cancelled.")
        return
    if data.startswith(f"{debts.CB_PREFIX}:action:"):
        action = data.split(":", 2)[2]
        await _ask_person(reply, ctx, action)
        return
    if data.startswith(f"{debts.CB_PREFIX}:person:"):
        name = data.split(":", 2)[2]
        wiz = ctx.user_data.get("debt_wizard")
        if not wiz:
            await reply("Session expired — start again with /debt.")
            return
        wiz["person"] = name
        wiz["step"] = "amount"
        await reply(f"{name} — how much?")
        return


async def _answer_debt_wizard(update, ctx, text):
    wiz = ctx.user_data["debt_wizard"]
    if text.strip().lower() in debts.CANCEL_WORDS:
        ctx.user_data.pop("debt_wizard")
        await update.message.reply_text("Cancelled.")
        return
    if wiz["step"] == "person":
        wiz["person"] = text.strip()
        wiz["step"] = "amount"
        await update.message.reply_text("How much?")
        return
    if wiz["step"] == "amount":
        amount = debts._num(text)
        if amount is None:
            await update.message.reply_text("Couldn't read the amount, try again.")
            return
        wiz["amount"] = amount
        wiz["step"] = "note"
        await update.message.reply_text("Note? (or “-” to skip)")
        return
    note = "" if _skip(text) else text.strip()
    ctx.user_data.pop("debt_wizard")
    await _finalize_debt_action(update, ctx, wiz["action"], wiz["person"], wiz["amount"], note)


async def cmd_debt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    if not ctx.args:
        await _start_debt_wizard(update, ctx)
        return
    if len(ctx.args) == 1 and ctx.args[0].lower() in debts.ACTIONS:
        await _start_debt_wizard(update, ctx, action=debts.ACTIONS[ctx.args[0].lower()])
        return
    try:
        parsed = debts.parse_debt_command(ctx.args)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    await _finalize_debt_action(
        update, ctx, parsed["action"], parsed["person"], parsed["amount"], parsed["note"])


async def cmd_debts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    if ctx.args and ctx.args[0].lower() == "closed":
        person = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
        closed = await asyncio.to_thread(sheets.closed_debts, person)
        await update.message.reply_text(debts.format_closed_list(closed))
        return
    if ctx.args:
        person = " ".join(ctx.args)
        history = await asyncio.to_thread(sheets.debt_history, person)
        await update.message.reply_text(debts.format_person_history(person, history))
        return
    open_all = await asyncio.to_thread(sheets.open_debts)
    await update.message.reply_text(debts.format_open_list(open_all))


# ---- handlers ----
def _authorized(update):
    return not config.ALLOWED_USER_IDS or str(update.effective_user.id) in config.ALLOWED_USER_IDS


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    await update.message.reply_text(
        "I log your expenses into a budget tracker sheet.\n\n"
        "One line: “water 5 eur”, “65 fuel”, “groceries store 19.21”.\n"
        "A batch — several expenses, one per line, optionally with a date:\n"
        "  yesterday\n  1) lunch cafe 12.1\n  2) groceries 23.49\n"
        "I understand “yesterday / day before yesterday / today / DD.MM”. "
        "You can also send a receipt photo or a voice message.\n\n"
        "Income — prefix with “+”: “+4000 salary”, “+150 freelance refund”. Goes to a separate sheet.\n\n"
        "Debts:\n"
        "  /debt — guided menu (buttons): pick lend/borrow/repay, then who, amount, note\n"
        "  /debt дал <name> <amount> [note] — you lent money (also: одолжил)\n"
        "  /debt занял <name> <amount> [note] — you borrowed money (also: взял)\n"
        "  /debt вернул <name> <amount> [note] — you repaid what you owed (also: отдал, погасил)\n"
        "  /debt вернули <name> <amount> [note] — they repaid what they owed you\n"
        "  /debts [name] — open balances, or one person's history\n"
        "  /debts closed [name] — fully repaid debts\n\n"
        "/day /week /month — expense summaries   /category <name> — monthly trend for one category\n"
        "/months — income vs. expenses per month\n"
        "/income — income this month   /undo — delete the last entry")


def week_bounds(today: date):
    """(Monday, today) as YYYY-MM-DD strings."""
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat(), today.isoformat()


async def _send_summary(update, title, total, by_cat):
    if total == 0:
        await update.message.reply_text(f"{title}: no expenses.")
        return
    lines = [f"{title}: {total:.2f} {SYM}\n"]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"  {amt:8.2f} {SYM}  {cat}")
    await update.message.reply_text("\n".join(lines))


async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    ym, total, by_cat = await asyncio.to_thread(sheets.month_summary)
    await _send_summary(update, f"Summary {ym}", total, by_cat)


async def cmd_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    if ctx.args:
        try:
            d = date.fromisoformat(ctx.args[0])
        except ValueError:
            await update.message.reply_text("Date as YYYY-MM-DD, e.g. /day 2026-07-03")
            return
    else:
        d = date.today()
    iso = d.isoformat()
    total, by_cat = await asyncio.to_thread(sheets.range_summary, iso, iso)
    await _send_summary(update, f"Day {iso}", total, by_cat)


async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    start, end = week_bounds(date.today())
    total, by_cat = await asyncio.to_thread(sheets.range_summary, start, end)
    await _send_summary(update, f"Week {start} — {end}", total, by_cat)


async def cmd_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    if not ctx.args:
        await update.message.reply_text(
            "Usage: /category <name>\n\nCategories:\n" + "\n".join(f"  {c}" for c in CATEGORIES))
        return
    query = " ".join(ctx.args).lower()
    match = next((c for c in CATEGORIES if c.lower() == query), None) \
        or next((c for c in CATEGORIES if query in c.lower()), None)
    if not match:
        await update.message.reply_text(
            "Unknown category. Categories:\n" + "\n".join(f"  {c}" for c in CATEGORIES))
        return
    history = await asyncio.to_thread(sheets.category_history, match)
    if not history:
        await update.message.reply_text(f"{match}: no expenses yet.")
        return
    lines = [f"{match} — last {len(history)} month(s):"]
    for ym, amt in history:
        lines.append(f"  {ym}  {amt:8.2f} {SYM}")
    await update.message.reply_text("\n".join(lines))


async def cmd_months(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    history = await asyncio.to_thread(sheets.months_summary)
    if not history:
        await update.message.reply_text("No income or expenses recorded yet.")
        return
    lines = [f"Income vs. expenses — last {len(history)} month(s):"]
    for ym, inc, exp in history:
        surplus = inc - exp
        sign = "+" if surplus >= 0 else "-"
        lines.append(
            f"  {ym}   in {inc:8.2f} {SYM}   out {exp:8.2f} {SYM}   "
            f"{sign}{abs(surplus):.2f} {SYM}")
    await update.message.reply_text("\n".join(lines))


async def cmd_income(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    ym, total, by_src = await asyncio.to_thread(sheets.income_summary)
    if total == 0:
        await update.message.reply_text(f"{ym}: no income yet. Example: “+4000 salary”.")
        return
    lines = [f"Income {ym}: {total:.2f} {SYM}\n"]
    for src, amt in sorted(by_src.items(), key=lambda x: -x[1]):
        lines.append(f"  {amt:8.2f} {SYM}  {src}")
    await update.message.reply_text("\n".join(lines))


_UNDO_FUNCS = {
    "expense": sheets.undo_last,
    "debt": sheets.undo_last_debt,
    "repayment": sheets.undo_last_repayment,
}


async def cmd_undo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    ctx.user_data.pop("pending", None)
    ctx.user_data.pop("confirm", None)
    ctx.user_data.pop("confirm_income", None)
    ctx.user_data.pop("pending_repay", None)
    ctx.user_data.pop("debt_wizard", None)
    kind = ctx.user_data.pop("last_write", {}).get("kind", "expense")
    vals = await asyncio.to_thread(_UNDO_FUNCS[kind])
    if not vals:
        await update.message.reply_text("Nothing to delete.")
        return
    await update.message.reply_text("Deleted: " + " · ".join(v for v in vals[:6] if v))


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    try:
        if "confirm" in ctx.user_data:
            await _answer_confirm(update, ctx, update.message.text)
            return
        if "confirm_income" in ctx.user_data:
            await _answer_confirm_income(update, ctx, update.message.text)
            return
        if "pending" in ctx.user_data:
            await _answer_pending(update, ctx, update.message.text)
            return
        if "pending_repay" in ctx.user_data:
            await _answer_pending_repay(update, ctx, update.message.text)
            return
        if "debt_wizard" in ctx.user_data:
            await _answer_debt_wizard(update, ctx, update.message.text)
            return
        if is_income(update.message.text):
            items = await asyncio.to_thread(parser.parse_income, update.message.text)
            await _route_income(update, ctx, items)
            return
        items = await asyncio.to_thread(parser.parse_text, update.message.text)
        await _route(update, ctx, items)
    except Exception as e:
        log.exception("text"); await update.message.reply_text(f"Error: {e}")


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    try:
        f = await ctx.bot.get_file(update.message.photo[-1].file_id)
        img = bytes(await f.download_as_bytearray())
        items = await asyncio.to_thread(parser.parse_image, img, update.message.caption or "")
        await _route(update, ctx, items)
    except Exception as e:
        log.exception("photo"); await update.message.reply_text(f"Error: {e}")


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    try:
        f = await ctx.bot.get_file(update.message.voice.file_id)
        ogg = bytes(await f.download_as_bytearray())
        text = await asyncio.to_thread(parser.transcribe_voice, ogg)
        if "confirm" in ctx.user_data:
            await _answer_confirm(update, ctx, text)
            return
        if "confirm_income" in ctx.user_data:
            await _answer_confirm_income(update, ctx, text)
            return
        if "pending" in ctx.user_data:
            await _answer_pending(update, ctx, text)
            return
        if "pending_repay" in ctx.user_data:
            await _answer_pending_repay(update, ctx, text)
            return
        if "debt_wizard" in ctx.user_data:
            await _answer_debt_wizard(update, ctx, text)
            return
        if is_income(text):
            items = await asyncio.to_thread(parser.parse_income, text)
            await _route_income(update, ctx, items)
            return
        items = await asyncio.to_thread(parser.parse_text, text)
        await _route(update, ctx, items)
    except ImportError:
        await update.message.reply_text("Voice input is disabled (see README) — please type instead.")
    except Exception as e:
        log.exception("voice"); await update.message.reply_text(f"Error: {e}")
