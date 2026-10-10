"""Run from the project folder:  python tests/test_team_capacity.py   (needs the packages in requirements.txt)"""
import sys, os
sys.path.insert(0, os.getcwd())
import app as A, game as G

def msgs(c, name): return [x["args"][0] for x in c.get_received() if x["name"] == name]
def new(): return A.socketio.test_client(A.app)

# solo rooms still stop at 6
host = new(); host.emit("create_room", {"name": "H", "device": "device-host0001"})
code = [m for m in msgs(host, "lobby")][-1]["code"]
solo = [new() for _ in range(5)]
for i, c in enumerate(solo): c.emit("join", {"code": code, "name": f"S{i}"})
seventh = new(); seventh.emit("join", {"code": code, "name": "Seventh"})
assert "6 of 6" in msgs(seventh, "error_msg")[0]["msg"]

# switching to team lifts the cap to 12; the lobby reports it
host.emit("set_mode", {"mode": "team"})
lob = msgs(host, "lobby")[-1]; assert lob["mode"] == "team" and lob["max"] == 12 and lob["min"] == 2
extra = [new() for _ in range(6)]
for i, c in enumerate(extra): c.emit("join", {"code": code, "name": f"T{i}"})
room = A.rooms[code]; assert len(room.members) == 12
assert sorted(m["id"] for m in room.members.values()) == list(range(12)), "slot ids must be unique 0-11"
late = new(); late.emit("join", {"code": code, "name": "TooMany"})
assert "12 of 12" in msgs(late, "error_msg")[0]["msg"]

# can't fall back to Solo with more than 6 people inside
host.get_received(); host.emit("set_mode", {"mode": "solo"})
assert room.mode == "team" and "fits 6" in msgs(host, "error_msg")[0]["msg"]

# a full 12-player match: 7 Survivors / 5 Hunters, everyone gets a spawn, play runs, conversion works
host.emit("start_game")
g = room.game
assert g.mode == "team" and g.team_counts() == (7, 5) and len(g.players) == 12
for _ in range(150): g.step(1 / 30)
snap = g._snapshot()
assert len(snap["p"]) == 12 and all(len(p) == 14 for p in snap["p"])
assert len({(round(p[1]), round(p[2])) for p in snap["p"]}) > 6, "players should not all share 6 spawn points"
surv = next(p for p in g.players.values() if p.team == 1); hunt = next(p for p in g.players.values() if p.team == 2)
surv.invuln = hunt.invuln = 0
g._damage(hunt, 999, surv.id, 0)
assert hunt.team == 1 and g.team_counts() == (8, 4) and g.phase == "play"
print("snapshot bytes at 12 players:", len(__import__("json").dumps(snap)))
print("TEAM CAPACITY TESTS OK")
