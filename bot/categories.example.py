"""Single source of truth for the budget — EXAMPLE / starting template.

Copy this file to bot/categories.py and edit CATEGORY_TABLE to make the tracker your
own: it drives BOTH the bot (parsing, validation, follow-up questions) and the
generated spreadsheet (tracker/build_tracker.py). Keep the three sentinels (FUEL,
GROCERIES, FALLBACK) pointing at real category names.

bot/categories.py is gitignored on purpose — your personal categories (and anything
you'd rather not have in a public repo) live only in your local/deployed copy.

Each row: (name, group, essential, plan, currency, note)
  name      shown to the user and written to the sheet — any language you like
  group     rollup bucket for the dashboard
  essential True if it counts toward the emergency-fund target (rent, food, bills...)
  plan      monthly planned amount in `currency`
  currency  EUR / USD / GBP (converted to the base currency in the sheet)
  note      free-text hint (optional)
"""

CATEGORY_TABLE = [
    ("Rent",           "Housing",   True,  700, "EUR", ""),
    ("Utilities",      "Housing",   True,  100, "EUR", ""),
    ("Internet/Phone", "Housing",   True,   40, "EUR", ""),
    ("Groceries",      "Food",      True,  500, "EUR", "store/market — see Place"),
    ("Dining out",     "Food",      False, 150, "EUR", ""),
    ("Coffee/snacks",  "Food",      False,  60, "EUR", ""),
    ("Delivery",       "Food",      False,  60, "EUR", ""),
    ("Fuel",           "Transport", True,  130, "EUR", "liters + station in fields"),
    ("Transport",      "Transport", False,  40, "EUR", "tickets, taxi, parking"),
    ("Health/Pharmacy","Health",    True,   50, "EUR", ""),
    ("Personal care",  "Personal",  False,  40, "EUR", ""),
    ("Clothing",       "Personal",  False,  50, "EUR", ""),
    ("Subscriptions",  "Subscriptions", False, 30, "EUR", "streaming, software..."),
    ("Gifts/Family",   "Family",    False, 100, "EUR", ""),
    ("Travel",         "Travel",    False, 150, "EUR", "savings jar"),
    ("Other/unplanned","Other",     False, 100, "EUR", ""),
]

# Derived lists — do not edit; change CATEGORY_TABLE instead.
CATEGORIES = [row[0] for row in CATEGORY_TABLE]

GROUPS = []
for _row in CATEGORY_TABLE:
    if _row[1] not in GROUPS:
        GROUPS.append(_row[1])

# Sentinels used by the follow-up logic. Must match names in CATEGORY_TABLE.
FUEL = "Fuel"
GROCERIES = "Groceries"
FALLBACK = "Other/unplanned"
