"""Run from the project folder:  python tests/test_alcatraz.py   (needs the packages in requirements.txt)"""
import os, sys
os.environ["LS_NO_SCHEDULER"] = "1"          # no background clock while testing; we drive it by hand
sys.path.insert(0, os.getcwd())
from datetime import datetime, timezone
import alcatraz, pushnotify
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

# 2. push subscriptions are validated
good = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "k", "auth": "a"}}
assert pushnotify.clean_sub(good) == good
for bad in (None, "x", {}, {"endpoint": "http://x/y", "keys": good["keys"]}, {"endpoint": good["endpoint"]},
            {"endpoint": good["endpoint"], "keys": {"p256dh": "k"}}, {"endpoint": "https://" + "a" * 700, "keys": good["keys"]}):
    assert pushnotify.clean_sub(bad) is None, bad
assert pushnotify.claim_night("2099-01-01") is True and pushnotify.claim_night("2099-01-01") is False

# 3. the nightly clock: nothing before 8pm, opens once at 8pm, announces once, never reopens after it empties
sent = []
A.pushnotify.send_all = lambda *a: sent.append(a)
A.rooms.pop("ALCATRAZ", None)
A.alcatraz_tick(at(18, 0)); assert "ALCATRAZ" not in A.rooms
A.alcatraz_tick(at(19, 0)); A.socketio.sleep(0.05)
assert "ALCATRAZ" in A.rooms and len(sent) == 1 and sent[0][2] == "/r/ALCATRAZ", sent
A.alcatraz_tick(at(19, 1)); A.socketio.sleep(0.05); assert len(sent) == 1       # one announcement per night

# 4. anyone can join; the first one in is host; the name can't be created by someone else
a = new(); a.emit("join", {"code": "alcatraz", "name": "Ann", "device": "device-ann0001"})
assert msgs(a, "joined")[0]["code"] == "ALCATRAZ"
room = A.rooms["ALCATRAZ"]; assert room.host in room.members
b = new(); b.emit("create_room", {"name": "Eve", "device": "device-eve0001", "room_name": "ALCATRAZ"})
assert "belongs to someone else" in msgs(b, "error_msg")[0]["msg"] or "in use" in msgs(b, "error_msg")[0]["msg"]

# 5. everybody leaves -> room is gone for the night and does not reopen; joiners are told when it opens
a.disconnect(); assert "ALCATRAZ" not in A.rooms
A.alcatraz_tick(at(21, 0)); A.socketio.sleep(0.05); assert "ALCATRAZ" not in A.rooms and len(sent) == 1
c = new(); c.emit("join", {"code": "ALCATRAZ", "name": "Late", "device": "device-late001"})
assert "8pm" in msgs(c, "error_msg")[0]["msg"]

# 6. next night it opens again; an unjoined room is closed in the morning
A.alcatraz_tick(at(19, 0, 22)); A.socketio.sleep(0.05)
assert "ALCATRAZ" in A.rooms and len(sent) == 2
A.alcatraz_tick(at(5, 0, 23)); assert "ALCATRAZ" not in A.rooms

# 7. http: service worker at the site root, push key, subscribe / unsubscribe
cl = A.app.test_client()
r = cl.get("/sw.js"); assert r.status_code == 200 and r.headers["Service-Worker-Allowed"] == "/"
assert cl.get("/api/push/key").get_json()["enabled"] is False
assert cl.post("/api/push/subscribe", json={"sub": good}).status_code == 400          # push not configured
pushnotify.VAPID_PUBLIC, pushnotify.VAPID_PRIVATE = "pub", "priv"
assert cl.get("/api/push/key").get_json() == {"enabled": True, "key": "pub"}
assert cl.post("/api/push/subscribe", json={"sub": good, "device": "device-ann0001"}).status_code == 200
assert good["endpoint"] in pushnotify._subs
assert cl.post("/api/push/subscribe", json={"sub": {"endpoint": "nope"}}).status_code == 400
assert cl.post("/api/push/unsubscribe", json={"endpoint": good["endpoint"]}).status_code == 200
assert good["endpoint"] not in pushnotify._subs
print("alcatraz tests passed")
