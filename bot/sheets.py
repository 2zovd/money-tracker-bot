"""Google Sheets access layer (the expenses tab and the income tab)."""
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from . import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_INCOME_HEADER = ["Date", "Amount", "Source", "Note"]


def _sheet():
    creds = Credentials.from_service_account_file(config.SA_FILE, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(config.SHEET_ID)


def _ws():
    return _sheet().worksheet(config.WORKSHEET)


def _income_ws():
    """Income log sheet. Created on first use (header in row 1)."""
    sh = _sheet()
    try:
        return sh.worksheet(config.INCOME_WORKSHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=config.INCOME_WORKSHEET, rows=500, cols=6)
        ws.update(range_name="A1:D1", values=[_INCOME_HEADER])
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


def append_expense(exp: dict) -> int:
    ws = _ws()
    row = _first_empty_row(ws)
    _write_row(ws, row, exp)
    return row


def append_many(items: list) -> int:
    ws = _ws()
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


def _expense_rows():
    """(date 'YYYY-MM-DD', category, amount) for each filled row of the journal."""
    out = []
    for r in _ws().get_all_values()[3:]:
        if len(r) < 3 or not r[0]:
            continue
        try:
            amt = _amount(r[2])
        except ValueError:
            continue
        out.append((str(r[0])[:10], r[1], amt))
    return out


def range_summary(start: str, end: str):
    """Total and per-category breakdown over [start, end] (inclusive 'YYYY-MM-DD')."""
    total, by_cat = 0.0, {}
    for d, cat, amt in _expense_rows():
        if start <= d <= end:
            total += amt
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
    return total, by_cat


def month_summary():
    ym = datetime.now().strftime("%Y-%m")
    total, by_cat = 0.0, {}
    for d, cat, amt in _expense_rows():
        if d[:7] == ym:
            total += amt
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
    return ym, total, by_cat


def undo_last():
    ws = _ws()
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


def append_income_many(items: list) -> int:
    ws = _income_ws()
    row = _first_empty_row(ws)
    for inc in items:
        _write_income(ws, row, inc)
        row += 1
    return len(items)


def income_summary():
    ws = _income_ws()
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
