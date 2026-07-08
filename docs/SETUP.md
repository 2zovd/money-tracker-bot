# Setup & deploy

Requires Python 3.10+.

## Five things you need

1. **TELEGRAM_TOKEN** — @BotFather → `/newbot`.
2. **ALLOWED_USER_ID** — @userinfobot (so only you can message the bot). Optional; leave
   empty to let anyone use it. Comma-separated for several people.
3. **ANTHROPIC_API_KEY** — console.anthropic.com → API Keys (add a few $ of credit).
4. **SHEET_ID** — from the Google Sheet URL (between `/d/` and `/edit`).
5. **service_account.json** — the bot's access to the sheet (below).

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
