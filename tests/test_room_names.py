"""Run from the project folder:  python tests/test_room_names.py   (needs the packages in requirements.txt)"""
import sys, os
sys.path.insert(0, os.getcwd())
import app as A

def msgs(c, name): return [x["args"][0] for x in c.get_received() if x["name"] == name]
def new(): return A.socketio.test_client(A.app)

# 1. custom name, cleaned + uppercased; link regex accepts it
a = new(); a.emit("create_room", {"name": "Lot", "device": "device-owner01", "room_name": "lots arena!"})
j = msgs(a, "joined"); assert j and j[0]["code"] == "LOTSARENA", j
assert A.CODE_RE.match("LOTSARENA")
assert A.app.test_client().get("/r/lotsarena").status_code == 200

# 2. while live: a stranger can't take it, can't create it; joiners can join by name
b = new(); b.emit("create_room", {"name": "Eve", "device": "device-eve0001", "room_name": "LOTSARENA"})
assert "belongs to someone else" in msgs(b, "error_msg")[0]["msg"]
c = new(); c.emit("join", {"code": "lotsarena", "name": "Cy", "device": "device-cy00001"})
assert msgs(c, "joined")[0]["code"] == "LOTSARENA"

# 3. everyone leaves -> room gone, but name stays the owner's; joiners see "closed", strangers still blocked
a.disconnect(); c.disconnect()
assert "LOTSARENA" not in A.rooms
d = new(); d.emit("join", {"code": "LOTSARENA", "name": "Late"})
assert "closed right now" in msgs(d, "error_msg")[0]["msg"]
b.emit("create_room", {"name": "Eve", "device": "device-eve0001", "room_name": "LOTSARENA"})
assert "belongs to someone else" in msgs(b, "error_msg")[0]["msg"]

# 4. the owner reuses it any time (new connection, same device)
a2 = new(); a2.emit("create_room", {"name": "Lot", "device": "device-owner01", "room_name": "LOTSARENA"})
assert msgs(a2, "joined")[0]["code"] == "LOTSARENA" and "LOTSARENA" in A.rooms

# 5. owner drops while another player holds the room; owner returns -> rejoins and is host again
e = new(); e.emit("join", {"code": "LOTSARENA", "name": "Eli", "device": "device-eli0001"})
a2.disconnect()
room = A.rooms["LOTSARENA"]; assert len(room.members) == 1
a3 = new(); a3.emit("create_room", {"name": "Lot", "device": "device-owner01", "room_name": "LOTSARENA"})
assert room.host == next(s for s, m in room.members.items() if m["name"] == "Lot") and len(room.members) == 2

# 6. validation + one reserved name per device + a name is required (no more random codes)
f = new(); f.emit("create_room", {"device": "device-eve0001", "room_name": "ab"})
assert "3 to 12" in msgs(f, "error_msg")[0]["msg"]
f.emit("create_room", {"name": "Eve", "device": "device-eve0001", "room_name": "EVEROOM"})
f.emit("create_room", {"name": "Eve", "device": "device-eve0001", "room_name": "EVEROOM2"})
assert "EVEROOM" not in A.roomnames._mem and "EVEROOM2" in A.roomnames._mem
g = new(); g.emit("create_room", {"name": "NoDev", "room_name": "NODEVICE"})
assert "verify your device" in msgs(g, "error_msg")[0]["msg"]
h = new(); h.emit("create_room", {"name": "Rand", "device": "device-rand001"})
assert "3 to 12" in msgs(h, "error_msg")[0]["msg"] and not msgs(h, "joined")

# 7. the host picks the player cap (2 to MAX_PLAYERS); junk falls back to MAX_PLAYERS
assert [A.clean_cap(x) for x in (1, 2, 4, 99, "x", None, "3")] == [2, 2, 4, A.MAX_PLAYERS, A.MAX_PLAYERS, A.MAX_PLAYERS, 3]
k = new(); k.emit("create_room", {"name": "Kay", "device": "device-kay00001", "room_name": "KAYROOM", "max_players": 3})
assert A.rooms["KAYROOM"].cap == 3 and msgs(k, "lobby")[-1]["max"] == 3
for i in (1, 2):
    p = new(); p.emit("join", {"code": "KAYROOM", "name": "P%d" % i, "device": "device-kp00000%d" % i}); assert msgs(p, "joined")
late = new(); late.emit("join", {"code": "KAYROOM", "name": "Late", "device": "device-kp000009"})
assert "full" in msgs(late, "error_msg")[0]["msg"]
print("ROOM NAME TESTS OK")
