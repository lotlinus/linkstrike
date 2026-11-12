"""Store rules that need no database: catalog, coin maths, daily cap, Nigeria-time day roll-over."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store

# catalog: every skin is valid, unique, priced by tier, and has both of its images
assert store.CATALOG, "skins.json is empty or unreadable"
ids = [s["id"] for s in store.CATALOG]
assert len(ids) == len(set(ids))
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for s in store.CATALOG:
    assert s["tier"] in store.TIERS and s["price"] > 0 and s["id"].startswith(s["weapon"] + "_"), s
    for f in (s["id"] + ".png", "hand_" + s["id"] + ".png"):
        assert os.path.exists(os.path.join(root, "static", "img", "wpn", "skins", f)), f
assert {s["price"] for s in store.CATALOG if s["tier"] == "common"} == {150}
assert {s["price"] for s in store.CATALOG if s["tier"] == "rare"} == {500}

# a bad skins.json entry is skipped, not fatal
import json, tempfile
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump([{"id": "ak47_x", "weapon": "ak47", "name": "X", "tier": "common", "price": 150},
               {"id": "bad1", "weapon": "nope", "tier": "common", "price": 1},
               {"id": "ak47_y", "weapon": "ak47", "tier": "epic", "price": 5},
               {"id": "ak47_x", "weapon": "ak47", "tier": "rare", "price": 9}, "junk"], f)
assert [s["id"] for s in store.load_catalog(f.name)] == ["ak47_x"]
os.unlink(f.name)

# coins: 5 per kill, never negative, junk becomes 0
assert store.coins_for_kills(4) == 20 and store.coins_for_kills(0) == 0
assert store.coins_for_kills(-3) == 0 and store.coins_for_kills("x") == 0 and store.coins_for_kills(None) == 0

# daily cap of 100, per day
day = "2026-11-11"
assert store.grant(0, day, day, 20) == (20, 20)
assert store.grant(90, day, day, 50) == (10, 100)           # only what is left under the cap
assert store.grant(100, day, day, 5) == (0, 100)            # capped
assert store.grant(100, "2026-11-10", day, 50) == (50, 50)  # new day: the counter starts over

# the day changes at midnight Nigeria time (UTC+1), not midnight UTC
assert store.today(datetime(2026, 11, 11, 22, 59, tzinfo=timezone.utc)) == "2026-11-11"
assert store.today(datetime(2026, 11, 11, 23, 0, tzinfo=timezone.utc)) == "2026-11-12"

# without a database everything degrades quietly
os.environ.pop("DATABASE_URL", None)
assert not store.enabled() and store.state("abcdefgh12") is None and store.award("abcdefgh12", 5) is None
assert store.buy("abcdefgh12", "ak47_flame")["ok"] is False
assert store.view("abcdefgh12")["enabled"] is False and store.view("abcdefgh12")["skins"] == []
print("store tests passed")
