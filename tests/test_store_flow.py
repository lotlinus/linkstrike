"""Store money flow (earn, daily cap, buy, equip), run against an in-memory SQLite stand-in for Postgres."""
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rankings
import store

_db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)


class FakeConn:
    def run(self, sql, **kw):
        sql = re.sub(r"\bnow\(\)", "CURRENT_TIMESTAMP", sql).replace(" FOR UPDATE", "")
        cur = _db.execute(sql, kw)
        return cur.fetchall() if cur.description else None

    def close(self):
        pass


rankings.enabled = lambda: True
rankings._connect = lambda: FakeConn()
D, E = "device-aaaa1111", "device-bbbb2222"
T = lambda h, d=11: datetime(2026, 11, d, h, 0, tzinfo=timezone.utc)

# nothing yet
assert store.state(D)["coins"] == 0 and store.state(D)["owned"] == []

# earning: 4 kills = 20 coins
r = store.award(D, 4, T(10))
assert (r["earned"], r["coins"], r["today"]) == (20, 20, 20), r

# the daily cap stops at 100, the rest is dropped
store.award(D, 16, T(11))                                  # +80 -> 100 today
r = store.award(D, 10, T(12))                              # would be +50, cap reached
assert (r["earned"], r["wanted"], r["coins"], r["today"]) == (0, 50, 100, 100), r

# new day (after midnight Nigeria time) the counter resets but the balance stays
r = store.award(D, 3, T(23))                               # 00:00 WAT on the 12th
assert (r["earned"], r["coins"], r["today"]) == (15, 115, 15), r
assert store.state(D, T(23))["today"] == 15 and store.state(D, T(10))["today"] == 0

# buying: not enough coins, then enough
assert store.buy(D, "ak47_lightning")["error"] == "coins"             # 500
assert store.state(D)["coins"] == 115
r = store.buy(D, "ak47_flame")                                        # 150, still short by 35
assert r["ok"] is False and r["error"] == "coins"
store.award(D, 7, T(23))                                              # +35 -> 150 coins
r = store.buy(D, "ak47_flame")
assert r["ok"] and r["state"]["coins"] == 0 and r["state"]["owned"] == ["ak47_flame"], r
assert r["state"]["equipped"] == {"3": "ak47_flame"}                  # bought skins are put on
assert store.buy(D, "ak47_flame")["error"] == "owned"                 # no double charge
assert store.state(D)["coins"] == 0

# equip / unequip, only what you own
assert store.equip(D, "mp5_red")["error"] == "not_owned"
assert store.equip(D, weapon=3)["state"]["equipped"] == {}
assert store.equip(D, "ak47_flame")["state"]["equipped"] == {"3": "ak47_flame"}
assert store.equipped(D) == {"3": "ak47_flame"}

# unknown skins and other devices
assert store.buy(D, "nope")["ok"] is False and store.equip(D, "nope")["ok"] is False
assert store.state(E)["owned"] == [] and store.equipped(E) == {}
v = store.view(E)
assert v["enabled"] and len(v["skins"]) == 10 and not any(s["owned"] for s in v["skins"]), v
v = store.view(D)
assert [s["id"] for s in v["skins"] if s["owned"]] == ["ak47_flame"]
assert [s["id"] for s in v["skins"] if s["equipped"]] == ["ak47_flame"]
print("store flow tests passed")
