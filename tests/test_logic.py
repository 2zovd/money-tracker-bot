"""Pure-logic tests (no network). Run: python -m pytest -q  or  python tests/test_logic.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import dialog, debts
from bot.categories import FALLBACK, FUEL, GROCERIES


def test_place_asked_for_groceries():
    e = dialog.normalize({"amount": 23.5, "category": GROCERIES, "place": ""})
    assert dialog.next_missing(e) == "place"


def test_no_ask_when_place_present():
    e = dialog.normalize({"amount": 23.5, "category": GROCERIES, "place": "Store A"})
    assert dialog.next_missing(e) is None


def test_fuel_asked_when_no_liters():
    e = dialog.normalize({"amount": 65, "category": FUEL})
    assert dialog.next_missing(e) == "fuel"


def test_fuel_liters_from_price():
    e = dialog.normalize({"amount": 66.0, "category": FUEL, "price_per_liter": 1.65})
    assert e["liters"] == 40.0
    assert dialog.next_missing(e) is None


def test_unknown_category_fallback():
    e = dialog.normalize({"amount": 10, "category": "nonsense"})
    assert e["category"] == FALLBACK


def test_num_and_skip():
    assert dialog._num("1,65 eur") == 1.65
    assert dialog._skip("-") is True
    assert dialog._skip("market") is False


def test_yes_no():
    assert dialog.is_yes("yes") and dialog.is_yes("ok") and dialog.is_yes("yep")
    assert dialog.is_yes("+") and dialog.is_yes("save")
    assert dialog.is_no("no") and dialog.is_no("cancel")
    assert not dialog.is_yes("maybe")


def test_skip():
    assert dialog._skip("skip") is True and dialog._skip("-") is True
    assert dialog._skip("none") is True
    assert dialog._skip("market") is False


def test_is_income():
    assert dialog.is_income("+4000 salary")
    assert dialog.is_income("salary 4000")
    assert dialog.is_income("advance 1500")
    assert dialog.is_income("refund for hotel 80")
    assert dialog.is_income("+150 freelance")
    assert not dialog.is_income("groceries store 19.21")
    assert not dialog.is_income("65 fuel")
    assert dialog.is_income("зарплата 5000 евро")
    assert dialog.is_income("+3000 аванс")
    assert dialog.is_income("кэшбэк 120")
    assert dialog.is_income("возврат за отель 80")
    assert not dialog.is_income("продукты магазин 19.21")
    assert not dialog.is_income("65 топливо")
    assert not dialog.is_income("подарок девушке 20")
    assert not dialog.is_income("в копилку на подарок 20")
    assert not dialog.is_income("gift to girlfriend")
    assert not dialog.is_income("отложено 800")
    assert not dialog.is_income("пополнение банкролла 50")


def test_format_income():
    items = [
        {"amount": 4000, "date": "2026-07-01", "source": "salary"},
        {"amount": 150.5, "date": "2026-07-02", "source": "freelance", "note": "project X"},
    ]
    out = dialog.format_income(items)
    assert "1)" in out and "2)" in out
    assert "4150.50" in out and "2 item(s)" in out


def test_week_bounds():
    from datetime import date
    # Wednesday 2026-07-01 → week starting Monday 2026-06-29
    assert dialog.week_bounds(date(2026, 7, 1)) == ("2026-06-29", "2026-07-01")
    # Monday → its own start
    assert dialog.week_bounds(date(2026, 6, 29)) == ("2026-06-29", "2026-06-29")


def test_format_batch():
    items = [
        {"amount": 12.1, "category": "Dining out", "date": "2026-07-02", "place": "Cafe"},
        {"amount": 23.49, "category": "Groceries", "date": "2026-07-02"},
    ]
    out = dialog.format_batch(items)
    assert "1)" in out and "2)" in out
    assert "35.59" in out and "2 expense(s)" in out


def test_parse_debt_command_lend():
    p = debts.parse_debt_command(["дал", "Лёша", "10", "за", "кофе"])
    assert p == {"action": "lend", "person": "Лёша", "amount": 10.0, "note": "за кофе"}


def test_parse_debt_command_borrow_no_note():
    p = debts.parse_debt_command(["занял", "X", "100"])
    assert p == {"action": "borrow", "person": "X", "amount": 100.0, "note": ""}


def test_parse_debt_command_repay():
    p = debts.parse_debt_command(["вернул", "X", "50"])
    assert p["action"] == "repay_borrowed" and p["amount"] == 50.0
    p = debts.parse_debt_command(["вернули", "Лёша", "10", "кофе"])
    assert p["action"] == "repay_lent" and p["note"] == "кофе"


def test_parse_debt_command_errors():
    import pytest
    with pytest.raises(ValueError):
        debts.parse_debt_command([])
    with pytest.raises(ValueError):
        debts.parse_debt_command(["blah", "X", "10"])
    with pytest.raises(ValueError):
        debts.parse_debt_command(["дал", "X"])  # no amount
    with pytest.raises(ValueError):
        debts.parse_debt_command(["дал", "X", "not a number"])


def test_direction_mapping():
    assert debts.direction_for_create("lend") == "lent"
    assert debts.direction_for_create("borrow") == "borrowed"
    assert debts.direction_for_repay("repay_borrowed") == "borrowed"
    assert debts.direction_for_repay("repay_lent") == "lent"


def test_format_open_list_empty():
    assert debts.format_open_list([]) == "No open debts."


def test_format_open_list_totals():
    items = [
        {"direction": "lent", "person": "Лёша", "remaining": 10.0},
        {"direction": "lent", "person": "Лёша", "remaining": 5.0},
        {"direction": "borrowed", "person": "X", "remaining": 100.0},
    ]
    out = debts.format_open_list(items)
    assert "Owed to you:" in out and "You owe:" in out
    assert "15.00" in out  # Лёша's combined remaining
    assert "Net: -85.00" in out


def test_parse_choice_number():
    assert debts.parse_choice_number("2", 3) == 1
    assert debts.parse_choice_number("0", 3) is None
    assert debts.parse_choice_number("4", 3) is None
    assert debts.parse_choice_number("abc", 3) is None


def test_format_repay_result_closes_debt():
    debt = {"remaining": 0.0}
    msg = debts.format_repay_result(debt, 10.0)
    assert "Debt closed." in msg


def test_format_repay_result_still_open():
    debt = {"remaining": 5.0}
    msg = debts.format_repay_result(debt, 5.0)
    assert "Debt closed." not in msg
    assert "5.00" in msg


def test_action_synonyms():
    assert debts.parse_debt_command(["взял", "X", "10"])["action"] == "borrow"
    assert debts.parse_debt_command(["отдал", "X", "10"])["action"] == "repay_borrowed"
    assert debts.parse_debt_command(["погасил", "X", "10"])["action"] == "repay_borrowed"
    assert debts.parse_debt_command(["одолжил", "X", "10"])["action"] == "lend"


def test_format_closed_list_empty():
    assert debts.format_closed_list([]) == "No closed debts yet."


def test_format_closed_list():
    closed = [
        {"person": "Лёша", "direction": "lent", "amount": 10.0, "note": "кофе", "date": "2026-07-01"},
        {"person": "X", "direction": "borrowed", "amount": 100.0, "note": "", "date": "2026-07-05"},
    ]
    out = debts.format_closed_list(closed)
    assert "Лёша" in out and "X" in out
    # newest first
    assert out.index("X") < out.index("Лёша")


def test_action_keyboard_has_four_actions_and_no_cancel():
    kb = debts.action_keyboard()
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert len(buttons) == 4
    assert all(b.callback_data.startswith("debt:action:") for b in buttons)


def test_person_keyboard_includes_cancel():
    kb = debts.person_keyboard(["Лёша", "X"])
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert len(buttons) == 3  # 2 persons + cancel
    assert buttons[-1].callback_data == debts.CB_CANCEL
    assert buttons[0].callback_data == debts.person_callback("Лёша")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
