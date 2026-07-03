"""Configuration from environment variables."""
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
SHEET_ID = os.environ.get("SHEET_ID", "")
WORKSHEET = os.environ.get("WORKSHEET", "Journal")
INCOME_WORKSHEET = os.environ.get("INCOME_WORKSHEET", "Income log")
SA_FILE = os.environ.get("GOOGLE_SA_FILE", "service_account.json")

# Currency: symbol shown to the user, code stored, and FX rates the parser uses to
# convert foreign amounts into the base currency.
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "€")
CURRENCY_CODE = os.environ.get("CURRENCY_CODE", "EUR")
USD_RATE = float(os.environ.get("USD_RATE", "0.92"))  # 1 USD -> base
GBP_RATE = float(os.environ.get("GBP_RATE", "1.16"))  # 1 GBP -> base

# Comma-separated Telegram user IDs allowed to use the bot. Empty = open to anyone.
ALLOWED_USER_IDS = [s.strip() for s in os.environ.get("ALLOWED_USER_ID", "").split(",") if s.strip()]

_REQUIRED = ("TELEGRAM_TOKEN", "ANTHROPIC_API_KEY", "SHEET_ID")

def validate():
    missing = [k for k in _REQUIRED if not globals()[k]]
    if missing:
        raise SystemExit("Missing environment variables: " + ", ".join(missing))
