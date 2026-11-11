"""Skin choice checks (plain asserts):  python tests/test_skins.py
Needs none of the web packages: flask_socketio, gevent and friends are replaced by stand-ins just for this test."""
import os, sys, types
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
for name in ("gevent", "gevent.monkey", "flask_socketio", "pg8000", "pg8000.native", "pg8000.dbapi"):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = mock.MagicMock()
os.environ.setdefault("DATABASE_URL", "")
import app as A  # noqa: E402


class FakeRoom:
    def __init__(self):
        self.members, self.host, self.code, self.cap, self.map, self.state = {}, None, "TEST", 6, "lab", "lobby"
        self.game = mock.MagicMock()


def seat(room, sid, name, skin=None):
    with mock.patch.object(A, "join_room"):
        return A.add_player(room, sid, name, None, skin)


def test_pick_is_kept_and_unique():
    r = FakeRoom()
    a = seat(r, "s1", "A", 4)
    b = seat(r, "s2", "B", 4)                 # same wish: must get a different one
    assert a["skin"] == 4 and b["skin"] != 4 and 0 <= b["skin"] < 6, (a, b)


def test_no_choice_gets_first_free():
    r = FakeRoom()
    assert seat(r, "s1", "A", 0)["skin"] == 0
    assert seat(r, "s2", "B", None)["skin"] == 1
    assert seat(r, "s3", "C", "junk")["skin"] == 2
    assert seat(r, "s4", "D", 99)["skin"] == 3
    assert seat(r, "s5", "E", -1)["skin"] == 4
    assert seat(r, "s6", "F", True)["skin"] == 5   # a bool is not a skin number


def test_full_room_all_skins_distinct():
    r = FakeRoom()
    skins = [seat(r, f"s{i}", f"P{i}", 2)["skin"] for i in range(6)]
    assert sorted(skins) == list(range(6)), skins


def test_leaving_frees_the_skin():
    r = FakeRoom()
    seat(r, "s1", "A", 3)
    del r.members["s1"]
    assert seat(r, "s2", "B", 3)["skin"] == 3


def test_lobby_payload_has_skins():
    r = FakeRoom()
    seat(r, "s1", "A", 5)
    seat(r, "s2", "B", 1)
    r.host = "s1"
    p = A.lobby_payload(r)
    assert [(q["id"], q["skin"]) for q in p["players"]] == [(0, 5), (1, 1)], p


if __name__ == "__main__":
    for fn in [v for k, v in dict(globals()).items() if k.startswith("test_")]:
        fn()
        print(fn.__name__, "ok")
    print("ALL PASSED")
