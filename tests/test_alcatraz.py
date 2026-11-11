"""Run from the project folder:  python tests/test_alcatraz.py   (needs the packages in requirements.txt)"""
import os, sys
os.environ["LS_NO_SCHEDULER"] = "1"          # no background clock while testing; we drive it by hand
sys.path.insert(0, os.getcwd())
from datetime import datetime, timezone
import alcatraz
import app as A

def at(h, m=0, d=21): return datetime(2026, 10, d, h, m, tzinfo=timezone.utc)
def msgs(c, name): return [x["args"][0] for x in c.get_received() if x["name"] == name]
def new(): return A.socketio.test_client(A.app)

# 1. the window: 20:00 Nigeria time (19:00 UTC) until 06:00
assert alcatraz.night(at(18, 59)) is None
assert alcatraz.night(at(19, 0)) == "2026-10-21"
assert alcatraz.night(at(23, 59)) == "2026-10-21"
assert alcatraz.night(at(2, 0, 22)) == "2026-10-21"      # after midnight it is still last night's room
assert alcatraz.night(at(4, 59, 22)) == "2026-10-21"
assert alcatraz.night(at(5, 0, 22)) is None

# 2. the nightly clock: nothing before 8pm, opens at 8pm, reopens if it empties
A.rooms.pop("ALCATRAZ", None)
A.alcatraz_tick(at(18, 0)); assert "ALCATRAZ" not in A.rooms
A.alcatraz_tick(at(19, 0)); assert "ALCATRAZ" in A.rooms
A.alcatraz_tick(at(19, 1)); assert "ALCATRAZ" in A.rooms

# 3. anyone can join; the first one in is host; the name can't be created by someone else
a = new(); a.emit("join", {"code": "alcatraz", "name": "Ann", "device": "device-ann0001"})
assert msgs(a, "joined")[0]["code"] == "ALCATRAZ"
room = A.rooms["ALCATRAZ"]; assert room.host in room.members
b = new(); b.emit("create_room", {"name": "Eve", "device": "device-eve0001", "room_name": "ALCATRAZ"})
assert "belongs to someone else" in msgs(b, "error_msg")[0]["msg"] or "in use" in msgs(b, "error_msg")[0]["msg"]

# 4. everybody leaves -> the next tick reopens it; late joiners get in
a.disconnect(); assert "ALCATRAZ" not in A.rooms
A.alcatraz_tick(at(21, 0)); assert "ALCATRAZ" in A.rooms
assert A.rooms["ALCATRAZ"].map == "stairs"
c = new(); c.emit("join", {"code": "ALCATRAZ", "name": "Late", "device": "device-late001"})
assert msgs(c, "joined")[0]["code"] == "ALCATRAZ"
c.disconnect()
A.rooms.pop("ALCATRAZ", None)

# 5. next night it opens again; an unjoined room is closed in the morning
A.alcatraz_tick(at(19, 0, 22)); assert "ALCATRAZ" in A.rooms
A.alcatraz_tick(at(5, 0, 23)); assert "ALCATRAZ" not in A.rooms

print("alcatraz tests passed")
