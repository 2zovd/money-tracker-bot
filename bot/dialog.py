"""Dialog logic: parse expenses (single or batch), follow-up questions, confirm, write.

Every message shown to the user is English. Data is written to the sheet using the
category names from bot/categories.py so it stays in sync with the tracker."""
import re
import asyncio
import logging
from datetime import date, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from . import sheets, parser, config
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
    "advance", "gift", "reimbursement")


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
async def _finalize(update, exp):
    await asyncio.to_thread(sheets.append_expense, exp)
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
    await _finalize(update, exp)


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
        "/day /week /month — expense summaries   /income — income this month   /undo — delete the last expense")


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


async def cmd_undo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _authorized(update):
        return
    ctx.user_data.pop("pending", None)
    ctx.user_data.pop("confirm", None)
    ctx.user_data.pop("confirm_income", None)
    vals = await asyncio.to_thread(sheets.undo_last)
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
