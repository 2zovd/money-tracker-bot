# Setup & deploy

Requires Python 3.10+.

## Things you need

1. **TELEGRAM_TOKEN** — @BotFather → `/newbot`.
2. **ALLOWED_USER_ID** — @userinfobot. Comma-separated allowlist; empty = anyone may
   connect their own sheet.
3. **ANTHROPIC_API_KEY** — console.anthropic.com → API Keys (add a few $ of credit). One
   shared key covers everyone using this bot.
4. **service_account.json** — the bot's access to sheets (below).

`SHEET_ID` is no longer required: each user connects their own sheet at runtime (see
**Multi-user mode**). Set it only to migrate an existing single-sheet deployment — on
startup the `ALLOWED_USER_ID` users are seeded to that sheet so they skip onboarding.

## Your categories

`bot/categories.py` is gitignored — it's your personal budget and stays out of the repo.

```bash
cp bot/categories.example.py bot/categories.py && nano bot/categories.py
```

## The spreadsheet

The `.xlsx` is not shipped in the repo — you generate it from your categories:

```bash
./venv/bin/python tracker/build_tracker.py tracker/budget-tracker.xlsx
```

1. Upload `tracker/budget-tracker.xlsx` to drive.google.com.
2. Open it → **File → Save as Google Sheets** (formulas and tabs carry over).
3. Copy `SHEET_ID` from the address. The expenses tab must match `WORKSHEET` (default
   `Journal`).

## Service account (sheet access)

1. console.cloud.google.com → create/select a project.
2. **APIs & Services → Library** → enable **Google Sheets API** (and **Drive API**).
3. **Credentials → Create credentials → Service account** → create → **Done**.
4. Open it → **Keys → Add key → JSON** → downloads a file → rename it to `service_account.json`.
5. In the file find `client_email` (…@…iam.gserviceaccount.com) and copy it.
6. In the sheet → **Share** → paste that email → **Editor**. Without this the bot can't write.

## Multi-user mode (let others test with their own sheet)

The bot serves several people from one process, each writing to their **own** Google Sheet.
One shared Anthropic key and one service account are used for everyone; only the sheet is
per-user, stored in a small SQLite file (`DB_FILE`, default `data/users.db`).

Owner setup, once:

1. Build the template sheet (`tracker/build_tracker.py`), upload it as a Google Sheet, then
   **Share → General access → Anyone with the link → Viewer**. Put its URL in
   `TEMPLATE_SHEET_URL`.
2. Leave `SHEET_ID` empty. Optionally set `ALLOWED_USER_ID` to invite specific testers only.

What a tester does — the bot walks them through it on `/start`:

1. Open the template → **File → Make a copy** (their own private sheet).
2. **Share** their copy as **Editor** with the service-account email (the bot shows it).
3. Paste the link to their copy. The bot verifies access, checks it's a real copy of the
   template (has the `Journal` tab), and connects it. Errors bounce back to the exact step
   to fix. `/disconnect` unlinks; `/connect <link>` is a shortcut past the wizard.

## Deploy (VPS + systemd)

First-time server setup:

```bash
sudo mkdir -p /opt/expense-bot && sudo chown $USER /opt/expense-bot
cd /opt/expense-bot
# copy the project here (bot/, tracker/, requirements.txt, deploy/, service_account.json)
# e.g.: rsync -av --exclude venv --exclude .git ./ user@IP:/opt/expense-bot/

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp .env.example .env && nano .env      # fill in your keys

# test
set -a; source .env; set +a
./venv/bin/python -m bot.main          # message the bot "5 coffee", then Ctrl+C

# autostart
sudo cp deploy/expense-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now expense-bot
sudo systemctl status expense-bot
journalctl -u expense-bot -f           # logs
```

### Shipping updates

Once the server is set up, deploy new code with the helper script — it rsyncs
`bot/ tracker/ tests/ requirements.txt`, reinstalls deps and restarts the service.
It never touches `.env`, `service_account.json` or `venv/` on the server.

```bash
deploy/deploy.sh            # sync + reinstall deps + restart
deploy/deploy.sh --dry-run  # preview what would change, do nothing
deploy/deploy.sh --no-deps  # code-only change, skip pip install
```

Edit `HOST` / `REMOTE_DIR` / `SERVICE` at the top of the script for your server.

## Voice (optional)

```bash
./venv/bin/pip install faster-whisper && sudo apt install ffmpeg
sudo systemctl restart expense-bot
```

## If you get `403 / PermissionError`

Step 6 was missed — the service account isn't shared on the sheet as Editor.
