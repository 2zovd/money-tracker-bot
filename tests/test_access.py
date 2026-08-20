"""Pure-logic tests for access control (no network). Run: python -m pytest -q"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot import access, config, store


# ---- callback / command parsing ----
def test_parse_callback_roundtrip():
    assert access.parse_callback(access.callback_data("approve", 42)) == (access.APPROVED, 42)
    assert access.parse_callback(access.callback_data("block", 7)) == (access.BLOCKED, 7)


def test_parse_callback_rejects_junk():
    assert access.parse_callback("acc:approve:notanumber") is None
    assert access.parse_callback("acc:delete:42") is None   # unknown action
    assert access.parse_callback("debt:approve:42") is None  # another feature's prefix
    assert access.parse_callback("acc:approve") is None


def test_parse_users_args():
    assert access.parse_users_args(["approve", "42"]) == (access.APPROVED, 42)
    assert access.parse_users_args(["BLOCK", "42"]) == (access.BLOCKED, 42)
    assert access.parse_users_args(["approve"]) is None
    assert access.parse_users_args(["approve", "abc"]) is None
    assert access.parse_users_args([]) is None


# ---- store (temp sqlite file) ----
def _fresh_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # let store create it
    config.DB_FILE = path
    store.init()


def test_unknown_user_has_no_status():
    _fresh_store()
    assert store.access_status(1) is None


def test_request_access_files_pending():
    _fresh_store()
    assert store.request_access(1, "Tester") == access.PENDING
    assert store.access_status(1) == access.PENDING


def test_request_never_downgrades_a_decision():
    _fresh_store()
    store.set_access(1, access.BLOCKED)
    assert store.request_access(1, "Tester") == access.BLOCKED
    store.set_access(2, access.APPROVED)
    assert store.request_access(2, "Tester") == access.APPROVED


def test_approve_and_block():
    _fresh_store()
    store.request_access(1, "Tester")
    store.set_access(1, access.APPROVED)
    assert store.access_status(1) == access.APPROVED
    store.set_access(1, access.BLOCKED)
    assert store.access_status(1) == access.BLOCKED


def test_blocking_keeps_the_sheet_mapping():
    _fresh_store()
    store.set_sheet(1, "SHEET_A")
    store.set_access(1, access.BLOCKED)
    assert store.get_sheet(1) == "SHEET_A"


def test_approve_seed_is_idempotent():
    _fresh_store()
    store.approve_seed(1)
    store.set_access(1, access.BLOCKED)
    store.approve_seed(1)  # ignored, row already exists
    assert store.access_status(1) == access.BLOCKED


def test_list_access_puts_pending_first():
    _fresh_store()
    store.set_access(1, access.APPROVED)
    store.request_access(2, "Waiting")
    rows = store.list_access()
    assert [r["user_id"] for r in rows] == [2, 1]
    assert [r["user_id"] for r in store.list_access(access.APPROVED)] == [1]


def test_format_user_list_handles_empty():
    assert access.format_user_list([]) == __import__("bot.strings", fromlist=["x"]).ACCESS_NO_USERS


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print(f"\n{len(fns)} passed")
