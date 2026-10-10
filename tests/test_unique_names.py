"""Run from the project folder:  python tests/test_unique_names.py   (needs the packages in requirements.txt)"""
import sys, os
sys.path.insert(0, os.getcwd())
import app as A

def msgs(c, name): return [x["args"][0] for x in c.get_received() if x["name"] == name]
def new(): return A.socketio.test_client(A.app)
def lobby_names(room): return sorted(m["name"] for m in room.members.values())

host = new(); host.emit("create_room", {"name": "Bob", "device": "device-bob00001"})
code = msgs(host, "joined")[0]["code"]; room = A.rooms[code]

# 1. same name from a different device is refused: ignoring case, spaces, look-alike and invisible characters
for tricky in ["bob", "BOB", " b o b ", "Bob\u200b", "\uff22\uff4f\uff42"]:
    c = new(); c.emit("join", {"code": code, "name": tricky, "device": "device-eve" + str(abs(hash(tricky)) % 10**5).zfill(5)})
    err = msgs(c, "error_msg"); assert err and "already taken" in err[0]["msg"], tricky
    assert not msgs(c, "joined")
assert lobby_names(room) == ["Bob"]

# 2. a refused player isn't pulled out of the room they were already in
other = new(); other.emit("create_room", {"name": "Zed", "device": "device-zed00001"})
zcode = msgs(other, "joined")[0]["code"]
other.emit("join", {"code": code, "name": "bob", "device": "device-zed00001x"})
assert A.sid_room[A.rooms[zcode].host] == zcode and zcode in A.rooms, "failed join must not eject you from your current room"

# 3. blank names are numbered automatically, never clash
b1 = new(); b1.emit("join", {"code": code, "name": "", "device": "device-aaa00001"})
b2 = new(); b2.emit("join", {"code": code, "name": "   ", "device": "device-aaa00002"})
b3 = new(); b3.emit("join", {"code": code, "device": "device-aaa00003"})
assert lobby_names(room) == ["Bob", "Soldier", "Soldier 2", "Soldier 3"], lobby_names(room)

# 4. same device again (second tab / refresh): takes over its seat, no duplicate, keeps id, name, kills
me = next(m for m in room.members.values() if m["name"] == "Bob")
my_id = me["id"]; room.game.players[my_id].kills = 3
tab2 = new(); tab2.emit("join", {"code": code, "name": "Totally Different", "device": "device-bob00001"})
j = msgs(tab2, "joined"); assert j and j[0]["you"] == my_id
assert len(room.members) == 4 and lobby_names(room) == ["Bob", "Soldier", "Soldier 2", "Soldier 3"]
assert room.game.players[my_id].kills == 3, "stats must survive"
assert room.host == next(s for s, m in room.members.items() if m["id"] == my_id), "host seat moves with the player"
old_msgs = msgs(host, "error_msg"); assert old_msgs and old_msgs[0].get("gone") and "another window" in old_msgs[0]["msg"]
host.emit("leave"); host.disconnect()                      # the old tab closing must not remove the new seat
assert len(room.members) == 4 and room.game.players[my_id].kills == 3

# 5. takeover also works when the room is full and while a team match is running
room.mode = "team"
while len(room.members) < 12:
    c = new(); c.emit("join", {"code": code, "name": f"P{len(room.members)}", "device": f"device-fill{len(room.members):04d}"})
assert len(room.members) == 12
tab3 = new(); tab3.emit("join", {"code": code, "name": "x", "device": "device-bob00001"})
assert msgs(tab3, "joined") and len(room.members) == 12
tab3.emit("start_game"); assert room.game.phase == "play" and len(room.game.players) == 12
team_before = room.game.players[my_id].team
tab4 = new(); tab4.emit("join", {"code": code, "name": "x", "device": "device-bob00001"})
assert msgs(tab4, "joined") and room.game.players[my_id].team == team_before and len(room.game.players) == 12
brand_new = new(); brand_new.emit("join", {"code": code, "name": "Newbie", "device": "device-new00001"})
err = msgs(brand_new, "error_msg")[0]["msg"]; assert "full" in err or "in progress" in err, err   # strangers still can't get in

# 6. a name frees up when its owner leaves; the owner-returns path for named rooms checks names too
t = new(); t.emit("create_room", {"name": "Lot", "device": "device-lot00001", "room_name": "NAMEDROOM"})
msgs(t, "joined")
x = new(); x.emit("join", {"code": "NAMEDROOM", "name": "lot", "device": "device-x0000001"})
assert "already taken" in msgs(x, "error_msg")[0]["msg"]
t.disconnect(); x.emit("join", {"code": "NAMEDROOM", "name": "lot", "device": "device-x0000001"})
assert "closed right now" in msgs(x, "error_msg")[0]["msg"]
print("UNIQUE NAME TESTS OK")
