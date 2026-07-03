# Money Tracker Bot

A personal expense tracker you can make your own. Message a Telegram bot — "23 groceries
store", a receipt photo, or a voice note — and Claude parses the amount, category and
place and appends a row to a Google Sheet that holds your budget model (plan vs actual,
emergency-fund progress, group rollups).

White-label by design: change your categories, currency and language in one place and it's
your tracker.

## Features

- Free-form text, receipt photos (vision), and optional voice (Whisper).
- Smart follow-ups: fuel → asks price per liter (computes liters); groceries → asks where.
- Separate axes — category / place / attributes — so analytics stay clean.
- Commands: `/day` `/week` `/month` (expense summaries), `/income`, `/undo`.
- One source of truth for categories, shared by the bot and the spreadsheet generator.

## Quick start

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env       # fill in your keys
./venv/bin/python -m pytest -q
./venv/bin/python tracker/build_tracker.py tracker/budget-tracker.xlsx   # build the sheet
set -a; source .env; set +a; ./venv/bin/python -m bot.main
```

Getting the keys, the Google service account, and VPS deploy — see [docs/SETUP.md](docs/SETUP.md).

## Make it yours

Edit `bot/categories.py` (categories, groups, plan amounts) and rebuild the tracker — the
bot and spreadsheet update together. Currency, tab names and the user allowlist are set in
`.env`. Full guide: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Stack

- **Now:** Python (python-telegram-bot), Anthropic Claude API, Google Sheets.
- **Planned:** a database (Supabase/Postgres) + FastAPI + a Vue 3 mini app. See
  [docs/ROADMAP.md](docs/ROADMAP.md).

## Project map

See [CLAUDE.md](CLAUDE.md) for the layout and development rules (handy if you pair with an
AI assistant).

## Secrets

`.env` and `service_account.json` are gitignored — never commit them. Set `ALLOWED_USER_ID`
to restrict the bot to yourself (or a comma-separated list for a household).

## License

MIT — see [LICENSE](LICENSE).
