"""Link Strike v0.7.2 - rooms, lobby, jetpack shooting, global leaderboard.

The server owns the game (see game.py): phones send inputs, the server simulates
everyone and broadcasts snapshots ~30 times a second. Rooms live in memory, so run ONE worker.
"""
from gevent import monkey

monkey.patch_all()

import os
import random
import re
import time

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

import game as G
import rankings
import roomnames

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
socketio = SocketIO(app, async_mode="gevent", ping_interval=10, ping_timeout=20)

# ---------------------------------------------------------------- config
TICK = 30                     # server updates per second
MAX_PLAYERS = G.MAX_PLAYERS          # Solo Battle; Team Multiplayer allows G.TEAM_MAX_PLAYERS
MIN_TO_START = int(os.environ.get("MIN_TO_START", "1"))  # set to 2 for real matches

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
CODE_RE = re.compile(r"^[A-Z0-9]{3,12}$")      # random codes (5 chars) and host-chosen room names
NAME_RE = re.compile(r"^[A-Z0-9]{3,12}$")

rooms = {}      # code -> Room
sid_room = {}   # socket id -> room code


class Room:
    def __init__(self, code):
        self.code = code
        self.members = {}   # sid -> {"id": slot, "name": str}
        self.host = None    # sid of host
        self.state = "lobby"
        self.loop_running = False
        self.game = G.Game()
        self.recorded = False   # this match's result already saved?
        self.mode = "solo"      # "solo" or "team"; the host picks it in the lobby


# ---------------------------------------------------------------- helpers
def new_code():
    while True:
        code = "".join(random.choice(CODE_ALPHABET) for _ in range(5))
        if code not in rooms and not roomnames.cached(code):
            return code


def clean_room_name(raw):
    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()[:12]


def clean_name(raw):
    name = re.sub(r"\s+", " ", str(raw or "")).strip()[:12]
    return name or "Soldier"


def add_player(room, sid, name, device=None):
    used = {m["id"] for m in room.members.values()}
    slot = next(i for i in range(G.SLOTS) if i not in used)
    m = {"id": slot, "name": clean_name(name), "device": rankings.clean_device(device)}
    room.members[sid] = m
    room.game.add_player(slot, m["name"])
    if room.host is None:
        room.host = sid
    sid_room[sid] = room.code
    join_room(room.code, sid=sid)
    return m


def room_max(room):
    return G.TEAM_MAX_PLAYERS if room.mode == "team" else MAX_PLAYERS


def lobby_payload(room):
    host = room.members.get(room.host)
    return {
        "code": room.code,
        "state": room.state,
        "host": host["id"] if host else None,
        "max": room_max(room),
        "min": G.TEAM_MIN_PLAYERS if room.mode == "team" else MIN_TO_START,
        "mode": room.mode,
        "players": sorted(
            ({"id": m["id"], "name": m["name"]} for m in room.members.values()),
            key=lambda m: m["id"],
        ),
    }


def broadcast_lobby(room):
    socketio.emit("lobby", lobby_payload(room), to=room.code)


def remove_player(sid):
    code = sid_room.pop(sid, None)
    room = rooms.get(code)
    if not room or sid not in room.members:
        return
    room.game.remove_player(room.members[sid]["id"])
    del room.members[sid]
    leave_room(code, sid=sid)
    if not room.members:
        rooms.pop(code, None)  # game loop notices and exits
        return
    if room.host == sid:
        room.host = next(iter(room.members))
    broadcast_lobby(room)


# ---------------------------------------------------------------- rankings
def save_result(room):
    """Match just finished: queue its result for the leaderboard (only 3+ player matches count)."""
    g = room.game
    entries = [
        {"id": m["id"], "device": m["device"], "name": m["name"], "kills": g.players[m["id"]].kills}
        for m in room.members.values() if m["id"] in g.players
    ]
    # team matches: kills count, but a team win or loss never touches personal stats
    results = rankings.build_results(entries, g.winner, ranked_win=(g.mode != "team"))
    if results:
        socketio.start_background_task(rankings.record_match, results)


# ---------------------------------------------------------------- game loop
def game_loop(room):
    dt = 1.0 / TICK
    next_t = time.time()
    while rooms.get(room.code) is room:
        snap = room.game.step(dt)
        socketio.emit("state", snap, to=room.code)
        if snap["m"][0] == "over" and not room.recorded:
            room.recorded = True
            save_result(room)
        next_t += dt
        wait = next_t - time.time()
        if wait > 0:
            socketio.sleep(wait)
        else:
            next_t = time.time()  # fell behind, don't try to catch up
    room.loop_running = False


# ---------------------------------------------------------------- http
@app.route("/")
def index():
    return render_template("index.html", room_code="")


@app.route("/r/<code>")
def invite(code):
    code = code.upper()
    return render_template("index.html", room_code=code if CODE_RE.match(code) else "")


@app.route("/api/leaderboard")
def api_leaderboard():
    limit = request.args.get("limit", type=int) or rankings.TOP_CARD
    device = rankings.clean_device(request.args.get("device"))
    resp = jsonify(rankings.leaderboard(limit, device))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/healthz")
def healthz():
    return "ok"


# ---------------------------------------------------------------- sockets
def enter_room(room, sid, name, device=None):
    remove_player(sid)  # in case they were in another room
    m = add_player(room, sid, name, device)
    emit("joined", {"code": room.code, "you": m["id"]})
    if room.state == "playing":
        emit("start", {"world": G.world_payload()})
    broadcast_lobby(room)


@socketio.on("create_room")
def on_create(data):
    data = data or {}
    wanted = str(data.get("room_name") or "").strip()
    if not wanted:
        room = Room(new_code())
        rooms[room.code] = room
        enter_room(room, request.sid, data.get("name"), data.get("device"))
        return

    # a custom room name: owned by the device that first used it, reusable by that device any time
    name = clean_room_name(wanted)
    device = rankings.clean_device(data.get("device"))
    if not NAME_RE.match(name):
        emit("error_msg", {"msg": "Room names need 3 to 12 letters or numbers."})
        return
    if not device:
        emit("error_msg", {"msg": "Couldn't verify your device. Refresh and try again."})
        return
    owner = roomnames.owner_of(name)
    if owner and owner != device:
        emit("error_msg", {"msg": f"The room name {name} belongs to someone else. Pick another."})
        return
    existing = rooms.get(name)
    if existing:
        if not owner:                                   # a random code that happens to match
            emit("error_msg", {"msg": f"The room name {name} is in use right now. Pick another."})
            return
        roomnames.claim(name, device)                   # the owner is back: refresh, rejoin, take host again
        enter_room(existing, request.sid, data.get("name"), device)
        existing.host = request.sid
        broadcast_lobby(existing)
        return
    if roomnames.claim(name, device) != device:         # someone claimed it a split second ago
        emit("error_msg", {"msg": f"The room name {name} belongs to someone else. Pick another."})
        return
    room = Room(name)
    rooms[name] = room
    enter_room(room, request.sid, data.get("name"), device)


@socketio.on("join")
def on_join(data):
    data = data or {}
    code = str(data.get("code", "")).strip().upper()
    room = rooms.get(code)
    if not room:
        if roomnames.owner_of(code):
            emit("error_msg", {"msg": f"{code} is closed right now. Ask the host to open it again.", "gone": True})
        else:
            emit("error_msg", {"msg": "Room not found. Check the code and try again.", "gone": True})
        return
    cap = room_max(room)
    if len(room.members) >= cap and request.sid not in room.members:
        emit("error_msg", {"msg": f"This room is full ({cap} of {cap} players)."})
        return
    if room.mode == "team" and room.state == "playing" and room.game.phase == "play" and request.sid not in room.members:
        emit("error_msg", {"msg": "A team match is already in progress. Try again when it ends."})
        return
    enter_room(room, request.sid, data.get("name"), data.get("device"))


@socketio.on("start_game")
def on_start():
    room = rooms.get(sid_room.get(request.sid))
    if not room or room.host != request.sid or room.state == "playing":
        return
    need = G.TEAM_MIN_PLAYERS if room.mode == "team" else MIN_TO_START
    if len(room.members) < need:
        emit("error_msg", {"msg": f"Need at least {need} players to start."})
        return
    room.state = "playing"
    room.recorded = False
    room.game.restart(room.mode)
    socketio.emit("start", {"world": G.world_payload()}, to=room.code)
    broadcast_lobby(room)
    if not room.loop_running:
        room.loop_running = True
        socketio.start_background_task(game_loop, room)


@socketio.on("set_mode")
def on_set_mode(data):
    room = rooms.get(sid_room.get(request.sid))
    mode = (data or {}).get("mode")
    if not room or room.host != request.sid or room.state != "lobby" or mode not in ("solo", "team"):
        return
    if mode == "solo" and len(room.members) > MAX_PLAYERS:
        emit("error_msg", {"msg": f"Solo Battle fits {MAX_PLAYERS} players and {len(room.members)} are in the room."})
        return
    room.mode = mode
    broadcast_lobby(room)


@socketio.on("rematch")
def on_rematch():
    room = rooms.get(sid_room.get(request.sid))
    if room and room.host == request.sid and room.game.phase == "over":
        if room.mode == "team" and len(room.members) < G.TEAM_MIN_PLAYERS:
            emit("error_msg", {"msg": f"Need at least {G.TEAM_MIN_PLAYERS} players for a team match."})
            return
        room.recorded = False
        room.game.restart(room.mode)


@socketio.on("input")
def on_input(data):
    room = rooms.get(sid_room.get(request.sid))
    m = room.members.get(request.sid) if room else None
    if not m:
        return
    d = data or {}
    try:
        room.game.set_input(m["id"], d.get("mx", 0), d.get("my", 0), d.get("aim", 0), d.get("fire", False))
    except (TypeError, ValueError):
        pass


@socketio.on("pingx")
def on_ping():
    return "ok"  # acknowledgement lets the client measure round-trip time


@socketio.on("leave")
def on_leave():
    remove_player(request.sid)


@socketio.on("disconnect")
def on_disconnect():
    remove_player(request.sid)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"Link Strike running on http://0.0.0.0:{port}")
    socketio.run(app, host="0.0.0.0", port=port)
