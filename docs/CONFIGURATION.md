# Configuration & customization

Everything personal lives in two places: `bot/categories.py` (your budget) and `.env`
(keys, currency, tab names). This is what makes the project white-label.

## Categories, groups and plan amounts

`bot/categories.py` is the single source of truth — and it's gitignored, so your personal
categories never land in the repo. First time: `cp bot/categories.example.py bot/categories.py`.
Edit `CATEGORY_TABLE`:

```python
# (name, group, essential, plan, currency, note)
CATEGORY_TABLE = [
    ("Rent",      "Housing", True,  700, "EUR", ""),
    ("Groceries", "Food",    True,  500, "EUR", "store/market — see Place"),
    ...
]
```

- **name** — shown to you and written to the sheet. Use any language you like.
- **group** — the dashboard rollup bucket. `GROUPS` is derived automatically in table order.
- **essential** — `True` counts toward the emergency-fund target (6 months of essentials).
- **plan** — monthly planned amount, in **currency**.
- **currency** — `EUR` / `USD` / `GBP` (converted in the sheet using the dashboard rates).
- **note** — an optional hint.

Keep the three sentinels pointing at real category names:

```python
FUEL = "Fuel"            # triggers the "price per liter?" follow-up
GROCERIES = "Groceries"  # triggers the "where?" follow-up
FALLBACK = "Other/unplanned"  # used when the parser is unsure
```

After editing, **rebuild the tracker** so the sheet matches:

```bash
./venv/bin/python tracker/build_tracker.py tracker/budget-tracker.xlsx
```

Re-upload it (or update the Reference/Expenses tabs by hand). The bot and the sheet read
categories from the same file, so they can't drift.

## Currency (`.env`)

```
CURRENCY_SYMBOL=€      # shown to the user and used in the sheet number formats
CURRENCY_CODE=EUR      # base currency; category rows in this currency use rate 1
USD_RATE=0.92          # 1 USD -> base
GBP_RATE=1.16          # 1 GBP -> base
```

The generated dashboard exposes the USD/GBP rates as editable cells, so you can adjust
them later without regenerating.

## Sheet tab names (`.env`)

```
WORKSHEET=Journal        # the expenses tab the bot writes to
INCOME_WORKSHEET=Income log   # the income tab (created on first use)
```

`WORKSHEET` must match the expenses tab in your sheet (default `Journal`). If you rename
tabs in `build_tracker.py`, keep them consistent across the formulas and `.env`.

## Who can use the bot (`.env`)

```
ALLOWED_USER_ID=111111111,222222222   # comma-separated Telegram IDs; empty = open to anyone
```

## Language

The interface is English. Claude parses whatever language you type, and it writes the
category names exactly as they appear in `CATEGORY_TABLE` — so if you name your categories
in another language, that's what lands in the sheet. To change the bot's replies, edit the
strings in `bot/dialog.py`.

## Model

`ANTHROPIC_MODEL` (default `claude-haiku-4-5`) picks the Claude model. Haiku is cheap and
good enough for parsing; use a larger model if you want.
