"""Configuration from environment variables."""
import json
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
# Optional in multi-user mode: used only to seed existing ALLOWED_USER_IDS on first run.
SHEET_ID = os.environ.get("SHEET_ID", "")
WORKSHEET = os.environ.get("WORKSHEET", "Journal")
INCOME_WORKSHEET = os.environ.get("INCOME_WORKSHEET", "Income log")
DEBTS_WORKSHEET = os.environ.get("DEBTS_WORKSHEET", "Debts")
REPAYMENTS_WORKSHEET = os.environ.get("REPAYMENTS_WORKSHEET", "Debt repayments")
SA_FILE = os.environ.get("GOOGLE_SA_FILE", "service_account.json")

# Per-user store: maps a Telegram user to their own spreadsheet.
DB_FILE = os.environ.get("DB_FILE", "data/users.db")
# Public template users copy during onboarding (share -> anyone with link -> viewer).
TEMPLATE_SHEET_URL = os.environ.get("TEMPLATE_SHEET_URL", "")


def _service_account_email():
    """The service account's email — users must share their sheet with it. Read from the
    key file's client_email so there's nothing extra to configure; env can override, and
    an empty string is fine when the file is absent (e.g. in tests)."""
    env = os.environ.get("GOOGLE_SA_EMAIL", "")
    if env:
        return env
    try:
        with open(SA_FILE, encoding="utf-8") as f:
            return json.load(f).get("client_email", "")
    except (OSError, ValueError):
        return ""


SA_EMAIL = _service_account_email()

# Currency: symbol shown to the user, code stored, and FX rates the parser uses to
# convert foreign amounts into the base currency.
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "€")
CURRENCY_CODE = os.environ.get("CURRENCY_CODE", "EUR")
USD_RATE = float(os.environ.get("USD_RATE", "0.92"))  # 1 USD -> base
GBP_RATE = float(os.environ.get("GBP_RATE", "1.16"))  # 1 GBP -> base

# Comma-separated Telegram user IDs allowed to use the bot. Empty = open to anyone.
ALLOWED_USER_IDS = [s.strip() for s in os.environ.get("ALLOWED_USER_ID", "").split(",") if s.strip()]

# SHEET_ID is no longer required: each user connects their own sheet at runtime.
_REQUIRED = ("TELEGRAM_TOKEN", "ANTHROPIC_API_KEY")

def validate():
    missing = [k for k in _REQUIRED if not globals()[k]]
    if missing:
        raise SystemExit("Missing environment variables: " + ", ".join(missing))
