"""Pure-logic tests for multi-user setup (no network). Run: python -m pytest -q"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import onboarding, config, store


# ---- parse_sheet_id ----
_ID = "1AbC_dEfGhIjKlMnOpQrStUvWxYz0123456789abcd"


def test_parse_sheet_id_from_full_url():
    url = f"https://docs.google.com/spreadsheets/d/{_ID}/edit#gid=0"
    assert onboarding.parse_sheet_id(url) == _ID


def test_parse_sheet_id_from_url_with_query():
    url = f"https://docs.google.com/spreadsheets/d/{_ID}/edit?usp=sharing"
    assert onboarding.parse_sheet_id(url) == _ID


def test_parse_sheet_id_bare_id():
    assert onboarding.parse_sheet_id(f"  {_ID}  ") == _ID


def test_parse_sheet_id_rejects_junk():
    assert onboarding.parse_sheet_id("hello there") is None
    assert onboarding.parse_sheet_id("short") is None
    assert onboarding.parse_sheet_id("") is None


# ---- wizard step transitions ----
def test_next_step_advances_forward():
    assert onboarding.next_step(onboarding.STEP_WELCOME, onboarding.CB_START) == onboarding.STEP_COPY
    assert onboarding.next_step(onboarding.STEP_COPY, onboarding.CB_COPIED) == onboarding.STEP_GRANT
    assert onboarding.next_step(onboarding.STEP_GRANT, onboarding.CB_GRANTED) == onboarding.STEP_LINK


def test_next_step_ignores_wrong_button_for_step():
    assert onboarding.next_step(onboarding.STEP_WELCOME, onboarding.CB_GRANTED) is None
    assert onboarding.next_step(onboarding.STEP_LINK, onboarding.CB_START) is None


# ---- store (temp sqlite file) ----
def _fresh_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # let store create it
    config.DB_FILE = path
    store.init()
    return path


def test_store_set_get_and_connected():
    _fresh_store()
    assert store.is_connected(42) is False
    assert store.get_sheet(42) is None
    store.set_sheet(42, "SHEET_A")
    assert store.get_sheet(42) == "SHEET_A"
    assert store.is_connected(42) is True


def test_store_reconnect_overwrites():
    _fresh_store()
    store.set_sheet(7, "OLD")
    store.set_sheet(7, "NEW")
    assert store.get_sheet(7) == "NEW"


def test_store_seed_is_idempotent():
    _fresh_store()
    store.seed(1, "SEED")
    store.seed(1, "OTHER")  # ignored, row already exists
    assert store.get_sheet(1) == "SEED"


def test_store_disconnect():
    _fresh_store()
    store.set_sheet(9, "X")
    store.disconnect(9)
    assert store.is_connected(9) is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
