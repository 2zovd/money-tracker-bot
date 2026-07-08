"""Parse expenses from text/photo via Claude. Returns a LIST of expenses (one or
more), each with a resolved date. The client is created lazily."""
import json
import base64
from datetime import datetime

from anthropic import Anthropic

from . import config
from .categories import CATEGORIES, FUEL, GROCERIES, FALLBACK

_client = None


def _c():
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_SYSTEM_TMPL = """You are a personal-expense parser. Today is {today}.
The message is free text (a single line, a list, or a receipt).
Return STRICTLY a JSON ARRAY of objects, one per expense, with no explanation:
[{{"amount": <number in {code} or null>, "category": <exactly one from the list>,
   "date": <"YYYY-MM-DD">, "place": <store/venue/station or "">,
   "method": "cash"|"card"|"", "liters": <liters or null>,
   "price_per_liter": <price per liter or null>, "note": <short note or "">}}]

Dates: today={today}; "yesterday" = -1 day; "day before yesterday" = -2 days;
"DD.MM" -> that date in the current year. A header line ("yesterday", "today", "01.07")
sets the date for every item below it until the next header. No date -> use today.
Items like "1) ... 2) ..." or separate lines are SEPARATE expenses, not one.

The category is ALWAYS exactly one from this list (do not translate it); pick the most
precise one, otherwise "{fallback}":
{cats}

Rules:
- "{groceries}" — food AND household goods from a store/supermarket/market/pharmacy;
  put the shop in `place` (e.g. supermarket, market, corner shop).
- Food/drinks out: "Coffee/snacks" (coffee/snack) or "Dining out" (a full meal);
  delivery -> "Delivery".
- Refuelling -> "{fuel}"; put liters/price-per-liter in their fields, brand/station in place/note.
- Gym/training classes -> "Функц. тренировки"; padel -> "Падел"; medicine, doctor,
  pharmacy -> "Аптека/медицина". Don't lump training into the pharmacy category.
- Gifts/flowers/spending for the girlfriend (подарок девушке, цветы девушке, копилка
  на подарок девушке) -> "Девушка". Money set aside into a general savings/emergency
  buffer (отложено, подушка безопасности, копилка — with NO girlfriend/betting
  context) -> "Подушка безопасности". "Пополнение банкролла" is ONLY for topping up
  the Betfair/betting bot bankroll specifically — never a generic "set aside" phrase.
- amount is a number only. For $/£ convert to {code} (USD*{usd}, GBP*{gbp}) and note it.
- Amount unclear -> amount: null.
Return ONLY the JSON array."""


_INCOME_TMPL = """You are a personal-INCOME parser (money coming in). Today is {today}.
Return STRICTLY a JSON ARRAY of objects, one per income entry, with no explanation:
[{{"amount": <number in {code} or null>, "date": <"YYYY-MM-DD">,
   "source": <source: salary/advance/bonus/freelance/refund/gift/... or "">,
   "note": <short note or "">}}]

Dates: today={today}; "yesterday" = -1 day; "day before yesterday" = -2 days;
"DD.MM" -> that date in the current year. No date -> use today.
A leading "+" ("+4000 salary") just marks income, it is NOT part of the number.
amount is a number only. For $/£ convert to {code} (USD*{usd}, GBP*{gbp}) and note it.
Amount unclear -> amount: null. Return ONLY the JSON array."""


def _system():
    return _SYSTEM_TMPL.format(today=datetime.now().strftime("%Y-%m-%d"),
                               cats=json.dumps(CATEGORIES, ensure_ascii=False),
                               code=config.CURRENCY_CODE, fallback=FALLBACK,
                               groceries=GROCERIES, fuel=FUEL,
                               usd=config.USD_RATE, gbp=config.GBP_RATE)


def _income_system():
    return _INCOME_TMPL.format(today=datetime.now().strftime("%Y-%m-%d"),
                               code=config.CURRENCY_CODE,
                               usd=config.USD_RATE, gbp=config.GBP_RATE)


def parse_income(text: str) -> list:
    m = _c().messages.create(model=config.ANTHROPIC_MODEL, max_tokens=600,
                             system=_income_system(), messages=[{"role": "user", "content": text}])
    return _extract(m.content[0].text)


def _extract(text: str) -> list:
    """Pull out the JSON array (or a single object -> a one-item list)."""
    text = text.strip().strip("`")
    a, o = text.find("["), text.find("{")
    if a != -1 and (o == -1 or a < o):
        return json.loads(text[a: text.rfind("]") + 1])
    return [json.loads(text[o: text.rfind("}") + 1])]


def parse_text(text: str) -> list:
    m = _c().messages.create(model=config.ANTHROPIC_MODEL, max_tokens=800,
                             system=_system(), messages=[{"role": "user", "content": text}])
    return _extract(m.content[0].text)


def parse_image(img_bytes: bytes, caption: str = "") -> list:
    b64 = base64.standard_b64encode(img_bytes).decode()
    content = [
        {"type": "image", "source": {"type": "base64",
         "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": caption or "This is a receipt. Extract the total amount, category, place and date."},
    ]
    m = _c().messages.create(model=config.ANTHROPIC_MODEL, max_tokens=800,
                             system=_system(), messages=[{"role": "user", "content": content}])
    return _extract(m.content[0].text)


def transcribe_voice(ogg_bytes: bytes) -> str:
    """Optional: local faster-whisper (see README)."""
    import tempfile
    from faster_whisper import WhisperModel
    global _WHISPER
    try:
        _WHISPER
    except NameError:
        _WHISPER = WhisperModel("small", device="cpu", compute_type="int8")
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(ogg_bytes); path = f.name
    segments, _ = _WHISPER.transcribe(path)  # auto-detect language
    return " ".join(s.text for s in segments).strip()
