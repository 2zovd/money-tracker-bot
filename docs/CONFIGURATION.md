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
DEBTS_WORKSHEET=Debts             # debts tab (created on first use)
REPAYMENTS_WORKSHEET=Debt repayments  # repayments tab (created on first use)
```

`WORKSHEET` must match the expenses tab in your sheet (default `Journal`). If you rename
tabs in `build_tracker.py`, keep them consistent across the formulas and `.env`. Unlike
`WORKSHEET`, the income/debts/repayments tabs are auto-created by the bot on first write if
missing, so they don't need to exist beforehand.

## Debts (`/debt`, `/debts`)

```
/debt                                 # guided menu: tap an action, then a person, type amount/note
/debt дал <name> <amount> [note]      # you lent money — they owe you (also: одолжил, занёс)
/debt занял <name> <amount> [note]    # you borrowed money — you owe them (also: взял)
/debt вернул <name> <amount> [note]   # you repaid what you owed (also: отдал, погасил)
/debt вернули <name> <amount> [note]  # they repaid what they owed you (also: отдали, погасили)
/debts [name]                         # open balances, or one person's history
/debts closed [name]                  # fully repaid debts
```

The command name is Latin (`/debt`) because Telegram only recognizes `/word` as a real
slash-command for ASCII names — the action verb after it (and its synonyms, see `ACTIONS` in
`bot/debts.py`) can be in any language.

`/debt` with no arguments (or with just an action word, e.g. `/debt занял`) starts a guided
flow: it shows an inline keyboard to pick lend/borrow/repay, then buttons for people who are
relevant to that action (recent debtors for lend/borrow, people with a matching open debt for
repay), then asks for the amount and note as plain text. You can always type a name instead of
tapping a button. The one-line command (`/debt дал Лёша 10 кофе`) still works unchanged for
quick entry. Closed (fully repaid) debts aren't deleted or moved — they stay in the `Debts`
sheet and are just filtered out of the default `/debts` view; see `/debts closed`.

See `docs/DATA_MODEL.md` for how debts and repayments are stored and linked.

## Who can use the bot (`.env`)

```
ALLOWED_USER_ID=111111111,222222222   # comma-separated Telegram IDs; empty = open to anyone
```

## Multi-user (each user their own sheet)

```
DB_FILE=data/users.db     # SQLite mapping of Telegram user -> their sheet id
TEMPLATE_SHEET_URL=...     # public template users copy during onboarding
GOOGLE_SA_EMAIL=...        # optional; otherwise read from service_account.json's client_email
```

Every user connects their own spreadsheet via the `/start` wizard (or `/connect <link>`);
the mapping is kept in `DB_FILE`. One shared `ANTHROPIC_API_KEY` and one service account
serve everyone. Leave `SHEET_ID` empty; set it only to migrate an existing single-sheet
deployment (its `ALLOWED_USER_ID` users are seeded to that sheet on first run). See
`docs/SETUP.md` → **Multi-user mode** for the full flow.

## Language

The interface is English. Claude parses whatever language you type, and it writes the
category names exactly as they appear in `CATEGORY_TABLE` — so if you name your categories
in another language, that's what lands in the sheet. To change the bot's replies, edit the
strings in `bot/strings.py` — all user-facing text lives there.

## Model

`ANTHROPIC_MODEL` (default `claude-haiku-4-5`) picks the Claude model. Haiku is cheap and
good enough for parsing; use a larger model if you want.
