"""Dialog logic: parse expenses (single or batch), follow-up questions, confirm, write.

All user-facing text lives in bot/strings.py — edit that file to translate the bot.
Data is written to the sheet using the category names from bot/categories.py so it
stays in sync with the tracker."""
import re
import asyncio
import logging
from datetime import date, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from . import access, sheets, parser, config, debts, onboarding, store, strings as s
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
async def _finalize(update, ctx, sid, exp):
    await asyncio.to_thread(sheets.append_expense, sid, exp)
    ctx.user_data["last_write"] = {"kind": "expense"}
    await update.message.reply_text(s.SAVED_ONE_EXPENSE.format(line=_line(exp)))


async def _step(update, ctx, sid, exp):
    if exp.get("amount") is None:
        await update.message.reply_text(s.NO_AMOUNT)
        return
    exp = normalize(exp)
    need = next_missing(exp)
    if need == "fuel":
        exp["_fuel_asked"] = True
        ctx.user_data["pending"] = exp
        await update.message.reply_text(s.ASK_FUEL_PRICE)
        return
    if need == "place":
        exp["_place_asked"] = True
        ctx.user_data["pending"] = exp
        await update.message.reply_text(s.ASK_PLACE)
        return
    ctx.user_data.pop("pending", None)
    await _finalize(update, ctx, sid, exp)


async def _answer_pending(update, ctx, sid, text):
    exp = ctx.user_data["pending"]
    if exp.get("_fuel_asked") and not exp.get("liters"):
        if not _skip(text):
            price = _num(text)
            if not price:
                await update.message.reply_text(s.BAD_FUEL_PRICE)
                return
            exp["price_per_liter"] = price
            exp["liters"] = round(float(exp["amount"]) / price, 2)
    elif exp.get("_place_asked") and not exp.get("place"):
        if not _skip(text):
            exp["place"] = text.strip()
    await _step(update, ctx, sid, exp)


# ---- batch of expenses: confirm before writing ----
async def _route(update, ctx, sid, items):
    items = [normalize(e) for e in items if e.get("amount") is not None]
    if not items:
        await update.message.reply_text(s.NO_EXPENSE_PARSED)
        return
    if len(items) == 1:
        await _step(update, ctx, sid, items[0])
        return
    ctx.user_data["confirm"] = items
    await update.message.reply_text(format_batch(items) + "\n\n" + s.CONFIRM_SAVE_ALL)


async def _answer_confirm(update, ctx, sid, text):
    if is_yes(text):
        items = ctx.user_data.pop("confirm")
        n = await asyncio.to_thread(sheets.append_many, sid, items)
        ctx.user_data["last_write"] = {"kind": "expense"}
        await update.message.reply_text(s.SAVED_N_EXPENSES.format(n=n))
    elif is_no(text):
        ctx.user_data.pop("confirm", None)
        await update.message.reply_text(s.CANCELLED_NOTHING_SAVED)
    else:
        await update.message.reply_text(s.ASK_YES_NO)


# ---- income: confirm before writing to the income sheet ----
async def _route_income(update, ctx, items):
    items = [e for e in items if e.get("amount") is not None]
    if not items:
        await update.message.reply_text(s.NO_INCOME_PARSED)
        return
    ctx.user_data["confirm_income"] = items
    await update.message.reply_text(format_income(items) + "\n\n" + s.CONFIRM_SAVE_INCOME)


async def _answer_confirm_income(update, ctx, sid, text):
    if is_yes(text):
        items = ctx.user_data.pop("confirm_income")
        n = await asyncio.to_thread(sheets.append_income_many, sid, items)
        await update.message.reply_text(
            s.SAVED_INCOME.format(n=n, worksheet=config.INCOME_WORKSHEET))
    elif is_no(text):
        ctx.user_data.pop("confirm_income", None)
        await update.message.reply_text(s.CANCELLED_INCOME_NOT_SAVED)
    else:
        await update.message.reply_text(s.ASK_YES_NO)


# ---- debts: lend/borrow/repay via /debt, list/history via /debts ----
async def _apply_repayment(update, ctx, sid, debt, amount, note):
    await asyncio.to_thread(sheets.append_repayment, sid, None, debt["id"], amount, note)
    updated = await asyncio.to_thread(sheets.debt_by_id, sid, debt["id"])
    ctx.user_data["last_write"] = {"kind": "repayment"}
    await update.message.reply_text(debts.format_repay_result(updated, amount))


async def _finalize_debt_action(update, ctx, sid, action, person, amount, note):
    if action in ("lend", "borrow"):
        direction = debts.direction_for_create(action)
        await asyncio.to_thread(
            sheets.append_debt, sid, None, person, direction, amount, config.CURRENCY_CODE, note)
        ctx.user_data["last_write"] = {"kind": "debt"}
        await update.message.reply_text(debts.format_debt_created(direction, person, amount, note))
        return

    direction = debts.direction_for_repay(action)
    matches = await asyncio.to_thread(sheets.open_debts, sid, person, direction)
    if not matches:
        await update.message.reply_text(s.NO_OPEN_DEBT_FOR.format(person=person))
        return
    if len(matches) == 1:
        await _apply_repayment(update, ctx, sid, matches[0], amount, note)
        return
    ctx.user_data["pending_repay"] = {
        "debts": matches, "amount": amount, "note": note, "person": person}
    await update.message.reply_text(debts.format_repay_choices(matches, person))


async def _answer_pending_repay(update, ctx, sid, text):
    state = ctx.user_data["pending_repay"]
    idx = debts.parse_choice_number(text, len(state["debts"]))
    if idx is None:
        await update.message.reply_text(s.ASK_DEBT_NUMBER)
        return
    ctx.user_data.pop("pending_repay")
    await _apply_repayment(update, ctx, sid, state["debts"][idx], state["amount"], state["note"])


# ---- guided /debt menu: buttons for action -> person -> typed amount -> typed note ----
async def _ask_person(reply, ctx, sid, action):
    ctx.user_data["debt_wizard"] = {"action": action, "step": "person"}
    if action in ("lend", "borrow"):
        persons = await asyncio.to_thread(sheets.recent_debt_persons, sid)
    else:
        direction = debts.direction_for_repay(action)
        persons = await asyncio.to_thread(sheets.persons_with_open_debt, sid, direction)
        if not persons:
            ctx.user_data.pop("debt_wizard", None)
            await reply(s.NO_OPEN_DEBTS_DIRECTION)
            return
    await reply(s.ACTION_PROMPTS[action], reply_markup=debts.person_keyboard(persons))


async def _start_debt_wizard(update, ctx, sid, action=None):
    async def reply(text, reply_markup=None):
        await update.message.reply_text(text, reply_markup=reply_markup)

    if action is None:
        open_all = await asyncio.to_thread(sheets.open_debts, sid)
        summary = debts.format_open_list(open_all)
        await reply(summary + "\n\nWhat do you want to do?", debts.action_keyboard())
        return
    await _ask_person(reply, ctx, sid, action)


async def on_debt_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _allowed(update, ctx):
        await query.answer()
        return
    await query.answer()

    async def reply(text, reply_markup=None):
        await query.edit_message_text(text, reply_markup=reply_markup)

    sid = store.get_sheet(update.effective_user.id)
    if sid is None:
        await reply(s.NOT_CONNECTED)
        return

    data = query.data
    if data == debts.CB_CANCEL:
        ctx.user_data.pop("debt_wizard", None)
        await reply(s.CANCELLED)
        return
    if data.startswith(f"{debts.CB_PREFIX}:action:"):
        action = data.split(":", 2)[2]
        await _ask_person(reply, ctx, sid, action)
        return
    if data.startswith(f"{debts.CB_PREFIX}:person:"):
        name = data.split(":", 2)[2]
        wiz = ctx.user_data.get("debt_wizard")
        if not wiz:
            await reply(s.SESSION_EXPIRED)
            return
        wiz["person"] = name
        wiz["step"] = "amount"
        await reply(s.ASK_AMOUNT_FOR.format(name=name))
        return


async def _answer_debt_wizard(update, ctx, sid, text):
    wiz = ctx.user_data["debt_wizard"]
    if text.strip().lower() in debts.CANCEL_WORDS:
        ctx.user_data.pop("debt_wizard")
        await update.message.reply_text(s.CANCELLED)
        return
    if wiz["step"] == "person":
        wiz["person"] = text.strip()
        wiz["step"] = "amount"
        await update.message.reply_text(s.ASK_AMOUNT)
        return
    if wiz["step"] == "amount":
        amount = debts._num(text)
        if amount is None:
            await update.message.reply_text(s.BAD_AMOUNT)
            return
        wiz["amount"] = amount
        wiz["step"] = "note"
        await update.message.reply_text(s.ASK_NOTE)
        return
    note = "" if _skip(text) else text.strip()
    ctx.user_data.pop("debt_wizard")
    await _finalize_debt_action(update, ctx, sid, wiz["action"], wiz["person"], wiz["amount"], note)


async def cmd_debt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    if not ctx.args:
        await _start_debt_wizard(update, ctx, sid)
        return
    if len(ctx.args) == 1 and ctx.args[0].lower() in debts.ACTIONS:
        await _start_debt_wizard(update, ctx, sid, action=debts.ACTIONS[ctx.args[0].lower()])
        return
    try:
        parsed = debts.parse_debt_command(ctx.args)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    await _finalize_debt_action(
        update, ctx, sid, parsed["action"], parsed["person"], parsed["amount"], parsed["note"])


async def cmd_debts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    if ctx.args and ctx.args[0].lower() == "closed":
        person = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
        closed = await asyncio.to_thread(sheets.closed_debts, sid, person)
        await update.message.reply_text(debts.format_closed_list(closed))
        return
    if ctx.args:
        person = " ".join(ctx.args)
        history = await asyncio.to_thread(sheets.debt_history, sid, person)
        await update.message.reply_text(debts.format_person_history(person, history))
        return
    open_all = await asyncio.to_thread(sheets.open_debts, sid)
    await update.message.reply_text(debts.format_open_list(open_all))


# ---- handlers ----
def _is_admin(user_id) -> bool:
    return str(user_id) in config.ADMIN_USER_IDS


async def _say(update, ctx, text):
    """Reply in the current chat whether we got here from a message or a button."""
    await ctx.bot.send_message(chat_id=update.effective_chat.id, text=text)


def _who(user) -> str:
    """How an admin sees a requester: display name plus @username when there is one."""
    name = user.full_name or str(user.id)
    return f"{name} (@{user.username})" if user.username else name


async def _notify_admins(ctx, user):
    text = s.ACCESS_REQUEST_ADMIN.format(
        name=user.full_name or "",
        username=f" (@{user.username})" if user.username else "",
        user_id=user.id)
    kb = access.decision_keyboard(user.id)
    for admin_id in config.ADMIN_USER_IDS:
        try:
            await ctx.bot.send_message(chat_id=int(admin_id), text=text, reply_markup=kb)
        except Exception:  # a wrong id or a blocked bot must not break the request
            log.warning("could not notify admin %s", admin_id)


async def _allowed(update, ctx) -> bool:
    """Access gate. The bot is closed by default: admins and approved users pass,
    an unknown user's first message files a request and pings the admins."""
    user = update.effective_user
    if _is_admin(user.id):
        return True
    status = store.access_status(user.id)
    if status == access.APPROVED:
        return True
    if status == access.BLOCKED:
        return False  # stay silent, don't tell a blocked user anything
    if status == access.PENDING:
        await _say(update, ctx, s.ACCESS_PENDING)
        return False
    if not config.ADMIN_USER_IDS:
        log.warning("access request from %s but ADMIN_USER_ID is not set", user.id)
        await _say(update, ctx, s.ACCESS_CLOSED)
        return False
    store.request_access(user.id, _who(user))
    await _notify_admins(ctx, user)
    await _say(update, ctx, s.ACCESS_REQUESTED)
    return False


async def _apply_decision(ctx, status, user_id, username=""):
    """Record an admin's decision and let an approved user know they can start."""
    store.set_access(user_id, status, username)
    if status == access.APPROVED:
        try:
            await ctx.bot.send_message(chat_id=user_id, text=s.ACCESS_GRANTED)
        except Exception:  # the user may not have started a chat with us yet
            log.warning("could not notify approved user %s", user_id)


async def on_access_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update.effective_user.id):
        return
    parsed = access.parse_callback(query.data)
    if parsed is None:
        return
    status, user_id = parsed
    await _apply_decision(ctx, status, user_id)
    await query.edit_message_text(
        query.message.text + "\n\n" + s.ACCESS_DECIDED_ADMIN.format(who=user_id, status=status))


async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin-only: list users, or approve/block one by id."""
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text(s.ACCESS_ADMIN_ONLY)
        return
    if not ctx.args:
        rows = store.list_access()
        await update.message.reply_text(access.format_user_list(rows))
        return
    parsed = access.parse_users_args(ctx.args)
    if parsed is None:
        await update.message.reply_text(s.ACCESS_USERS_USAGE)
        return
    status, user_id = parsed
    await _apply_decision(ctx, status, user_id)
    await update.message.reply_text(
        s.ACCESS_DECIDED_ADMIN.format(who=user_id, status=status))


async def _require_sheet(update):
    """The user's connected sheet id, or None (after nudging them to /start) if not set."""
    sid = store.get_sheet(update.effective_user.id)
    if sid is None:
        await update.message.reply_text(s.NOT_CONNECTED)
    return sid


# ---- onboarding wizard ----
def _onb_view(step):
    """(text, keyboard) to show for a wizard step."""
    if step == onboarding.STEP_COPY:
        text = s.ONB_COPY_TEMPLATE if config.TEMPLATE_SHEET_URL else s.ONB_COPY_NO_TEMPLATE
        return text, onboarding.copy_keyboard()
    if step == onboarding.STEP_GRANT:
        return s.ONB_GRANT_ACCESS.format(email=config.SA_EMAIL), onboarding.grant_keyboard()
    if step == onboarding.STEP_LINK:
        return s.ONB_SEND_LINK, onboarding.cancel_keyboard()
    return s.ONB_WELCOME, onboarding.welcome_keyboard()


async def _start_onboarding(update, ctx):
    ctx.user_data.clear()  # drop any stale pending/confirm state before setup
    ctx.user_data["onboarding"] = {"step": onboarding.STEP_WELCOME}
    text, kb = _onb_view(onboarding.STEP_WELCOME)
    await update.message.reply_text(text, reply_markup=kb)


async def on_onboarding_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _allowed(update, ctx):
        await query.answer()
        return
    await query.answer()
    data = query.data
    if data == onboarding.CB_CANCEL:
        ctx.user_data.pop("onboarding", None)
        await query.edit_message_text(s.CANCELLED)
        return
    state = ctx.user_data.get("onboarding")
    if not state:
        await query.edit_message_text(s.ONB_SESSION_EXPIRED)
        return
    nxt = onboarding.next_step(state["step"], data)
    if nxt is None:
        return  # stale button that doesn't apply to the current step
    state["step"] = nxt
    text, kb = _onb_view(nxt)
    await query.edit_message_text(text, reply_markup=kb)


async def _answer_onboarding(update, ctx, text):
    state = ctx.user_data["onboarding"]
    if text.strip().lower() in debts.CANCEL_WORDS:
        ctx.user_data.pop("onboarding", None)
        await update.message.reply_text(s.CANCELLED)
        return
    if state["step"] != onboarding.STEP_LINK:
        # Typed before reaching the link step — re-show the current step.
        cur_text, kb = _onb_view(state["step"])
        await update.message.reply_text(cur_text, reply_markup=kb)
        return
    sid = onboarding.parse_sheet_id(text)
    if sid is None:
        await update.message.reply_text(s.ONB_BAD_LINK)
        return
    await update.message.reply_text(s.ONB_CHECKING)
    await _finish_connect(update, ctx, sid)


async def _finish_connect(update, ctx, sid):
    """Validate access and connect, or bounce back to the step that needs fixing."""
    try:
        title = await asyncio.to_thread(sheets.connect_and_validate, sid)
    except PermissionError:
        if "onboarding" in ctx.user_data:
            ctx.user_data["onboarding"]["step"] = onboarding.STEP_GRANT
        await update.message.reply_text(
            s.CONNECT_NO_ACCESS.format(email=config.SA_EMAIL),
            reply_markup=onboarding.grant_keyboard() if "onboarding" in ctx.user_data else None)
        return
    except sheets.BadTemplate:
        if "onboarding" in ctx.user_data:
            ctx.user_data["onboarding"]["step"] = onboarding.STEP_COPY
            cur_text, kb = _onb_view(onboarding.STEP_COPY)
            await update.message.reply_text(s.CONNECT_BAD_TEMPLATE)
            await update.message.reply_text(cur_text, reply_markup=kb)
        else:
            await update.message.reply_text(s.CONNECT_BAD_TEMPLATE)
        return
    store.set_sheet(update.effective_user.id, sid)
    ctx.user_data.pop("onboarding", None)
    await update.message.reply_text(s.CONNECTED_OK.format(title=title))


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    if store.is_connected(update.effective_user.id):
        await update.message.reply_text(s.HELP_TEXT)
        return
    await _start_onboarding(update, ctx)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    await update.message.reply_text(s.HELP_TEXT)


async def cmd_connect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fast path for experienced users: /connect <link>. Onboarding via /start is the norm."""
    if not await _allowed(update, ctx):
        return
    if not ctx.args:
        await update.message.reply_text(s.CONNECT_USAGE)
        return
    sid = onboarding.parse_sheet_id(" ".join(ctx.args))
    if sid is None:
        await update.message.reply_text(s.CONNECT_USAGE)
        return
    await update.message.reply_text(s.ONB_CHECKING)
    await _finish_connect(update, ctx, sid)


async def cmd_disconnect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    store.disconnect(update.effective_user.id)
    await update.message.reply_text(s.DISCONNECTED)


def week_bounds(today: date):
    """(Monday, today) as YYYY-MM-DD strings."""
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat(), today.isoformat()


async def _send_summary(update, title, total, by_cat):
    if total == 0:
        await update.message.reply_text(s.NO_EXPENSES_FOR.format(title=title))
        return
    lines = [f"{title}: {total:.2f} {SYM}\n"]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"  {amt:8.2f} {SYM}  {cat}")
    await update.message.reply_text("\n".join(lines))


async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    ym, total, by_cat = await asyncio.to_thread(sheets.month_summary, sid)
    await _send_summary(update, s.SUMMARY_MONTH_TITLE.format(ym=ym), total, by_cat)


async def cmd_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    if ctx.args:
        try:
            d = date.fromisoformat(ctx.args[0])
        except ValueError:
            await update.message.reply_text(s.BAD_DAY_ARG)
            return
    else:
        d = date.today()
    iso = d.isoformat()
    total, by_cat = await asyncio.to_thread(sheets.range_summary, sid, iso, iso)
    await _send_summary(update, s.SUMMARY_DAY_TITLE.format(iso=iso), total, by_cat)


async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    start, end = week_bounds(date.today())
    total, by_cat = await asyncio.to_thread(sheets.range_summary, sid, start, end)
    await _send_summary(update, s.SUMMARY_WEEK_TITLE.format(start=start, end=end), total, by_cat)


async def cmd_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    cat_list = "\n".join(f"  {c}" for c in CATEGORIES)
    if not ctx.args:
        await update.message.reply_text(s.CATEGORY_USAGE.format(list=cat_list))
        return
    query = " ".join(ctx.args).lower()
    match = next((c for c in CATEGORIES if c.lower() == query), None) \
        or next((c for c in CATEGORIES if query in c.lower()), None)
    if not match:
        await update.message.reply_text(s.UNKNOWN_CATEGORY.format(list=cat_list))
        return
    history = await asyncio.to_thread(sheets.category_history, sid, match)
    if not history:
        await update.message.reply_text(s.NO_EXPENSES_FOR_CATEGORY.format(category=match))
        return
    lines = [s.CATEGORY_HISTORY_HEADER.format(category=match, n=len(history))]
    for ym, amt in history:
        lines.append(f"  {ym}  {amt:8.2f} {SYM}")
    await update.message.reply_text("\n".join(lines))


async def cmd_months(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    history = await asyncio.to_thread(sheets.months_summary, sid)
    if not history:
        await update.message.reply_text(s.NO_INCOME_OR_EXPENSES)
        return
    lines = [s.MONTHS_HISTORY_HEADER.format(n=len(history))]
    for ym, inc, exp in history:
        surplus = inc - exp
        sign = "+" if surplus >= 0 else "-"
        lines.append(
            f"  {ym}   in {inc:8.2f} {SYM}   out {exp:8.2f} {SYM}   "
            f"{sign}{abs(surplus):.2f} {SYM}")
    await update.message.reply_text("\n".join(lines))


async def cmd_income(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    ym, total, by_src = await asyncio.to_thread(sheets.income_summary, sid)
    if total == 0:
        await update.message.reply_text(s.NO_INCOME_THIS_MONTH.format(ym=ym))
        return
    lines = [s.INCOME_MONTH_HEADER.format(ym=ym, total=total, sym=SYM)]
    for src, amt in sorted(by_src.items(), key=lambda x: -x[1]):
        lines.append(f"  {amt:8.2f} {SYM}  {src}")
    await update.message.reply_text("\n".join(lines))


_UNDO_FUNCS = {
    "expense": sheets.undo_last,
    "debt": sheets.undo_last_debt,
    "repayment": sheets.undo_last_repayment,
}


async def cmd_undo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    sid = await _require_sheet(update)
    if sid is None:
        return
    ctx.user_data.pop("pending", None)
    ctx.user_data.pop("confirm", None)
    ctx.user_data.pop("confirm_income", None)
    ctx.user_data.pop("pending_repay", None)
    ctx.user_data.pop("debt_wizard", None)
    kind = ctx.user_data.pop("last_write", {}).get("kind", "expense")
    vals = await asyncio.to_thread(_UNDO_FUNCS[kind], sid)
    if not vals:
        await update.message.reply_text(s.NOTHING_TO_DELETE)
        return
    await update.message.reply_text(s.DELETED.format(summary=" · ".join(v for v in vals[:6] if v)))


async def _handle_input(update, ctx, sid, text):
    """Route a text/voice message through the active conversation state to the sheet."""
    if "confirm" in ctx.user_data:
        await _answer_confirm(update, ctx, sid, text)
        return
    if "confirm_income" in ctx.user_data:
        await _answer_confirm_income(update, ctx, sid, text)
        return
    if "pending" in ctx.user_data:
        await _answer_pending(update, ctx, sid, text)
        return
    if "pending_repay" in ctx.user_data:
        await _answer_pending_repay(update, ctx, sid, text)
        return
    if "debt_wizard" in ctx.user_data:
        await _answer_debt_wizard(update, ctx, sid, text)
        return
    if is_income(text):
        items = await asyncio.to_thread(parser.parse_income, text)
        await _route_income(update, ctx, items)
        return
    items = await asyncio.to_thread(parser.parse_text, text)
    await _route(update, ctx, sid, items)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    try:
        if "onboarding" in ctx.user_data:
            await _answer_onboarding(update, ctx, update.message.text)
            return
        sid = store.get_sheet(update.effective_user.id)
        if sid is None:
            await _start_onboarding(update, ctx)  # walk a new user through setup
            return
        await _handle_input(update, ctx, sid, update.message.text)
    except Exception as e:
        log.exception("text"); await update.message.reply_text(s.ERROR.format(error=e))


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    try:
        sid = await _require_sheet(update)
        if sid is None:
            return
        f = await ctx.bot.get_file(update.message.photo[-1].file_id)
        img = bytes(await f.download_as_bytearray())
        items = await asyncio.to_thread(parser.parse_image, img, update.message.caption or "")
        await _route(update, ctx, sid, items)
    except Exception as e:
        log.exception("photo"); await update.message.reply_text(s.ERROR.format(error=e))


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _allowed(update, ctx):
        return
    try:
        sid = await _require_sheet(update)
        if sid is None:
            return
        f = await ctx.bot.get_file(update.message.voice.file_id)
        ogg = bytes(await f.download_as_bytearray())
        text = await asyncio.to_thread(parser.transcribe_voice, ogg)
        await _handle_input(update, ctx, sid, text)
    except ImportError:
        await update.message.reply_text(s.VOICE_DISABLED)
    except Exception as e:
        log.exception("voice"); await update.message.reply_text(s.ERROR.format(error=e))
