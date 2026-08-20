"""Google Sheets access layer (the expenses tab and the income tab)."""
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from . import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_INCOME_HEADER = ["Date", "Amount", "Source", "Note"]
_DEBTS_HEADER = ["Date", "Person", "Direction", "Amount", "Currency", "Note"]
_REPAYMENTS_HEADER = ["Date", "DebtID", "Amount", "Note"]


_client = None


def _authorize():
    """The gspread client, authorized once and cached (one service account for all users)."""
    global _client
    if _client is None:
        creds = Credentials.from_service_account_file(config.SA_FILE, scopes=_SCOPES)
        _client = gspread.authorize(creds)
    return _client


def _sheet(sheet_id: str):
    return _authorize().open_by_key(sheet_id)


class BadTemplate(Exception):
    """The sheet opened, but it's not a copy of our template (no expenses tab)."""


def connect_and_validate(sheet_id: str) -> str:
    """Open the user's spreadsheet and confirm it looks like our template.

    Returns the spreadsheet title on success. Raises PermissionError if the service
    account can't open it (wrong id or not shared), and BadTemplate if the expenses tab
    is missing."""
    try:
        sh = _sheet(sheet_id)
    except (gspread.SpreadsheetNotFound, gspread.exceptions.APIError) as e:
        raise PermissionError(sheet_id) from e
    try:
        sh.worksheet(config.WORKSHEET)  # expenses tab must pre-exist
    except gspread.WorksheetNotFound as e:
        raise BadTemplate(sheet_id) from e
    return sh.title


def _ws(sheet_id: str):
    return _sheet(sheet_id).worksheet(config.WORKSHEET)


def _income_ws(sheet_id: str):
    """Income log sheet. Created on first use (header in row 1)."""
    sh = _sheet(sheet_id)
    try:
        return sh.worksheet(config.INCOME_WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=config.INCOME_WORKSHEET, rows=500, cols=6)
        ws.update(range_name="A1:D1", values=[_INCOME_HEADER])
        return ws


def _debts_ws(sheet_id: str):
    """Debts sheet: one row per debt (lent/borrowed). Created on first use."""
    sh = _sheet(sheet_id)
    try:
        return sh.worksheet(config.DEBTS_WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=config.DEBTS_WORKSHEET, rows=500, cols=8)
        ws.update(range_name="A1:F1", values=[_DEBTS_HEADER])
        return ws


def _repayments_ws(sheet_id: str):
    """Repayments sheet: one row per repayment, linked to a debt by row number (DebtID)."""
    sh = _sheet(sheet_id)
    try:
        return sh.worksheet(config.REPAYMENTS_WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=config.REPAYMENTS_WORKSHEET, rows=500, cols=6)
        ws.update(range_name="A1:D1", values=[_REPAYMENTS_HEADER])
        return ws


def _first_empty_row(ws):
    return len(ws.col_values(1)) + 1


def _write_row(ws, row, exp):
    """A:Date B:Category C:Amount D:Place E:Method F:Liters  H:Note.
    G(price/L) I(Month) J(Group) K(Essential) are template formulas — leave them."""
    date = exp.get("date") or datetime.now().strftime("%Y-%m-%d")
    liters = exp.get("liters")
    ws.update(range_name=f"A{row}:F{row}",
              values=[[date, exp["category"], float(exp["amount"]),
                       exp.get("place", ""), exp.get("method", ""),
                       float(liters) if liters else ""]],
              value_input_option="USER_ENTERED")
    ws.update(range_name=f"H{row}", values=[[exp.get("note", "")]],
              value_input_option="USER_ENTERED")


def append_expense(sheet_id: str, exp: dict) -> int:
    ws = _ws(sheet_id)
    row = _first_empty_row(ws)
    _write_row(ws, row, exp)
    return row


def append_many(sheet_id: str, items: list) -> int:
    ws = _ws(sheet_id)
    row = _first_empty_row(ws)
    for exp in items:
        _write_row(ws, row, exp)
        row += 1
    return len(items)


def _amount(s):
    """Parse an amount from a cell: drop the currency symbol, spaces, thousands separator."""
    s = str(s).replace(config.CURRENCY_SYMBOL, "").replace("€", "").replace("$", "")
    s = s.replace(" ", "").replace(" ", "").strip()
    return float(s.replace(",", ""))  # comma = thousands separator


def _expense_rows(sheet_id: str):
    """(date 'YYYY-MM-DD', category, amount) for each filled row of the journal."""
    out = []
    for r in _ws(sheet_id).get_all_values()[3:]:
        if len(r) < 3 or not r[0]:
            continue
        try:
            amt = _amount(r[2])
        except ValueError:
            continue
        out.append((str(r[0])[:10], r[1], amt))
    return out


def range_summary(sheet_id: str, start: str, end: str):
    """Total and per-category breakdown over [start, end] (inclusive 'YYYY-MM-DD')."""
    total, by_cat = 0.0, {}
    for d, cat, amt in _expense_rows(sheet_id):
        if start <= d <= end:
            total += amt
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
    return total, by_cat


def month_summary(sheet_id: str):
    ym = datetime.now().strftime("%Y-%m")
    total, by_cat = 0.0, {}
    for d, cat, amt in _expense_rows(sheet_id):
        if d[:7] == ym:
            total += amt
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
    return ym, total, by_cat


def category_history(sheet_id: str, category: str, months: int = 6):
    """[(YYYY-MM, total), ...] for one category, oldest first, last `months` months with data."""
    by_month = {}
    for d, cat, amt in _expense_rows(sheet_id):
        if cat.lower() == category.lower():
            ym = d[:7]
            by_month[ym] = by_month.get(ym, 0.0) + amt
    return sorted(by_month.items())[-months:]


def months_summary(sheet_id: str, months: int = 6):
    """[(YYYY-MM, income_total, expense_total), ...] for the last `months` months
    with any activity, oldest first."""
    by_month = {}  # ym -> [income, expense]

    for d, _cat, amt in _expense_rows(sheet_id):
        ym = d[:7]
        by_month.setdefault(ym, [0.0, 0.0])[1] += amt

    for r in _income_ws(sheet_id).get_all_values()[1:]:  # row 1 is the header
        if len(r) < 2 or not r[0]:
            continue
        try:
            amt = _amount(r[1])
        except ValueError:
            continue
        ym = str(r[0])[:7]
        by_month.setdefault(ym, [0.0, 0.0])[0] += amt

    items = sorted((ym, inc, exp) for ym, (inc, exp) in by_month.items())
    return items[-months:]


def undo_last(sheet_id: str):
    ws = _ws(sheet_id)
    row = _first_empty_row(ws) - 1
    if row <= 3:
        return None
    vals = ws.row_values(row)
    ws.batch_clear([f"A{row}:F{row}", f"H{row}"])  # keep the G,I,J,K formulas
    return vals


# ---- income (income log sheet): A:Date B:Amount C:Source D:Note ----
def _write_income(ws, row, inc):
    date = inc.get("date") or datetime.now().strftime("%Y-%m-%d")
    ws.update(range_name=f"A{row}:D{row}",
              values=[[date, float(inc["amount"]),
                       inc.get("source", ""), inc.get("note", "")]],
              value_input_option="USER_ENTERED")


def append_income_many(sheet_id: str, items: list) -> int:
    ws = _income_ws(sheet_id)
    row = _first_empty_row(ws)
    for inc in items:
        _write_income(ws, row, inc)
        row += 1
    return len(items)


def income_summary(sheet_id: str):
    ws = _income_ws(sheet_id)
    rows = ws.get_all_values()
    ym = datetime.now().strftime("%Y-%m")
    total, by_src = 0.0, {}
    for r in rows[1:]:  # row 1 is the header
        if len(r) < 2 or not r[0].startswith(ym):
            continue
        try:
            amt = _amount(r[1])
        except ValueError:
            continue
        total += amt
        src = r[2] if len(r) > 2 and r[2] else "—"
        by_src[src] = by_src.get(src, 0.0) + amt
    return ym, total, by_src


# ---- debts: A:Date B:Person C:Direction(lent/borrowed) D:Amount E:Currency F:Note ----
# A debt's ID is its row number in the Debts sheet (no separate counter needed).
def append_debt(sheet_id, date, person, direction, amount, currency, note) -> int:
    ws = _debts_ws(sheet_id)
    row = _first_empty_row(ws)
    date = date or datetime.now().strftime("%Y-%m-%d")
    ws.update(range_name=f"A{row}:F{row}",
              values=[[date, person, direction, float(amount), currency, note or ""]],
              value_input_option="USER_ENTERED")
    return row


def _debt_rows(sheet_id: str):
    """{id, date, person, direction, amount, currency, note} for each filled Debts row."""
    out = []
    for i, r in enumerate(_debts_ws(sheet_id).get_all_values()[1:], start=2):  # row 1 is the header
        if len(r) < 4 or not r[0]:
            continue
        try:
            amt = _amount(r[3])
        except ValueError:
            continue
        out.append({
            "id": i, "date": str(r[0])[:10], "person": r[1], "direction": r[2],
            "amount": amt, "currency": r[4] if len(r) > 4 else "",
            "note": r[5] if len(r) > 5 else "",
        })
    return out


# ---- repayments: A:Date B:DebtID C:Amount D:Note ----
def append_repayment(sheet_id, date, debt_id, amount, note) -> int:
    ws = _repayments_ws(sheet_id)
    row = _first_empty_row(ws)
    date = date or datetime.now().strftime("%Y-%m-%d")
    ws.update(range_name=f"A{row}:D{row}",
              values=[[date, int(debt_id), float(amount), note or ""]],
              value_input_option="USER_ENTERED")
    return row


def _repayment_rows(sheet_id: str):
    """{row, date, debt_id, amount, note} for each filled Repayments row."""
    out = []
    for i, r in enumerate(_repayments_ws(sheet_id).get_all_values()[1:], start=2):
        if len(r) < 3 or not r[0]:
            continue
        try:
            debt_id = int(float(r[1]))
            amt = _amount(r[2])
        except ValueError:
            continue
        out.append({"row": i, "date": str(r[0])[:10], "debt_id": debt_id,
                     "amount": amt, "note": r[3] if len(r) > 3 else ""})
    return out


def _repaid_amount(debt_id: int, repayments) -> float:
    return sum(r["amount"] for r in repayments if r["debt_id"] == debt_id)


def _with_balance(debt, repayments):
    repaid = _repaid_amount(debt["id"], repayments)
    remaining = debt["amount"] - repaid
    return {**debt, "repaid": repaid, "remaining": remaining,
            "status": "closed" if remaining <= 0 else "open"}


def _filtered_debts(sheet_id, person: str = None, direction: str = None, open_only: bool = True):
    repayments = _repayment_rows(sheet_id)
    out = []
    for d in _debt_rows(sheet_id):
        if person and d["person"].lower() != person.lower():
            continue
        if direction and d["direction"] != direction:
            continue
        d = _with_balance(d, repayments)
        if (d["remaining"] > 0) == open_only:
            out.append(d)
    return out


def open_debts(sheet_id, person: str = None, direction: str = None):
    """Debts with remaining > 0, balance computed, optionally filtered by person/direction."""
    return _filtered_debts(sheet_id, person, direction, open_only=True)


def closed_debts(sheet_id, person: str = None, direction: str = None):
    """Fully repaid debts (remaining <= 0), optionally filtered by person/direction."""
    return _filtered_debts(sheet_id, person, direction, open_only=False)


def recent_debt_persons(sheet_id, limit: int = 6):
    """Distinct debt person names, most-recently-added first (for quick-pick buttons)."""
    seen = []
    for d in reversed(_debt_rows(sheet_id)):
        if d["person"] not in seen:
            seen.append(d["person"])
        if len(seen) >= limit:
            break
    return seen


def persons_with_open_debt(sheet_id, direction: str, limit: int = 8):
    """Distinct person names with an open debt in the given direction, most recent first."""
    seen = []
    for d in reversed(open_debts(sheet_id, direction=direction)):
        if d["person"] not in seen:
            seen.append(d["person"])
        if len(seen) >= limit:
            break
    return seen


def debt_by_id(sheet_id, debt_id: int):
    repayments = _repayment_rows(sheet_id)
    for d in _debt_rows(sheet_id):
        if d["id"] == debt_id:
            return _with_balance(d, repayments)
    return None


def debt_history(sheet_id, person: str):
    """All debts (open and closed) for a person, each with its repayments, newest first."""
    repayments = _repayment_rows(sheet_id)
    debts = [_with_balance(d, repayments) for d in _debt_rows(sheet_id)
             if d["person"].lower() == person.lower()]
    for d in debts:
        d["repayments"] = [r for r in repayments if r["debt_id"] == d["id"]]
    return list(reversed(debts))


def undo_last_debt(sheet_id):
    ws = _debts_ws(sheet_id)
    row = _first_empty_row(ws) - 1
    if row <= 1:
        return None
    vals = ws.row_values(row)
    ws.batch_clear([f"A{row}:F{row}"])
    return vals


def undo_last_repayment(sheet_id):
    ws = _repayments_ws(sheet_id)
    row = _first_empty_row(ws) - 1
    if row <= 1:
        return None
    vals = ws.row_values(row)
    ws.batch_clear([f"A{row}:D{row}"])
    return vals
