"""Pure-logic tests (no network). Run: python -m pytest -q  or  python tests/test_logic.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import dialog
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
