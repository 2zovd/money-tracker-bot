# Money Tracker Bot — guide for Claude Code

A personal expense tracker: a Python Telegram bot accepts expenses (text / receipt photo /
voice), parses them with the Claude API, and writes structured rows into a Google Sheet.
The sheet holds a budget model (plan vs actual, emergency fund, group rollups). The project
is white-label — categories, currency and language are meant to be customized.

## Layout

```
money-tracker-bot/
├── bot/            # the Telegram bot (Python) — what runs today
│   ├── main.py         # entry point: python -m bot.main
│   ├── config.py       # environment variables (keys, currency, tab names, allowlist)
│   ├── categories.py   # SINGLE SOURCE OF TRUTH: categories, groups, plan amounts
│   ├── sheets.py       # Google Sheets layer
│   ├── parser.py       # expense/income parsing via Claude (lazy client)
│   └── dialog.py       # Telegram handlers + follow-up question logic
├── tracker/        # spreadsheet generator (openpyxl) — reads bot/categories.py
│   └── build_tracker.py
├── frontend/       # future Vue mini app (empty for now)
├── deploy/         # systemd unit for a VPS
├── docs/           # SETUP, CONFIGURATION, DATA_MODEL, ROADMAP
└── tests/          # tests for pure logic (no network)
```

## Commands

```bash
# environment
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt

# tests (no network/secrets)
./venv/bin/python -m pytest -q          # or: python tests/test_logic.py

# rebuild the tracker from bot/categories.py
./venv/bin/python tracker/build_tracker.py tracker/budget-tracker.xlsx

# run the bot (requires .env)
set -a; source .env; set +a; ./venv/bin/python -m bot.main
```

## Development rules

- Python 3.10+, keep the style simple and explicit; no unnecessary abstractions.
- Comments and strings in **simple, short English**.
- **`bot/categories.py` is the single source of truth.** The bot (parsing, validation,
  follow-ups) and the tracker generator both read `CATEGORY_TABLE` from it. Change
  categories there and rebuild the tracker — never hardcode a category elsewhere.
- Keep the `FUEL` / `GROCERIES` / `FALLBACK` sentinels pointing at real category names.
- Secrets only in `.env` and `service_account.json` — both gitignored. Never hardcode or
  log keys.
- Network calls (Claude, Sheets) are blocking; wrap them in `asyncio.to_thread` inside
  handlers so the event loop isn't blocked.
- The Anthropic client is created lazily (`parser._c()`) so tests import without a key.
- Default model is Haiku (cheap); change it via `ANTHROPIC_MODEL` in `.env`.
- Any new parsing/dialog logic gets a test in `tests/` (pure functions: `normalize`,
  `next_missing`, `_num`, `_skip`, ...).

## Data model (brief)

Separate the axes: **Category** (budget) ≠ **Place** (store/market) ≠ **attributes**
(liters, price/liter, method). Categories roll up into **Groups**. Details in
`docs/DATA_MODEL.md`; customization in `docs/CONFIGURATION.md`.

## Where it's heading

Bot + Sheets (now) → DB + API → Vue mini app. See `docs/ROADMAP.md`.

## What NOT to do

- Don't commit `.env`, `service_account.json`, `tracker/*.xlsx`, or `frontend/CLAUDE.md`.
- Don't expand categories per place/merchant — place is a separate field, not a category.
- Don't perform financial operations (transfers, payments) — the bot only records.
