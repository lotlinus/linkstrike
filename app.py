"""Link Strike v0.7.2 - rooms, lobby, jetpack shooting, global leaderboard.

The server owns the game (see game.py): phones send inputs, the server simulates
everyone and broadcasts snapshots ~30 times a second. Rooms live in memory, so run ONE worker.
"""
from gevent import monkey

monkey.patch_all()

import os
import random
import re
import unicodedata
import time

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

import alcatraz
import game as G
import rankings
import roomnames
import store

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
socketio = SocketIO(app, async_mode="gevent", ping_interval=10, ping_timeout=20)

# ---------------------------------------------------------------- config
TICK = 30                     # server updates per second
MAX_PLAYERS = G.MAX_PLAYERS
REMATCH_WAIT = 10                 # seconds the others get to tap Play again once one player has
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
        self.again = set()      # sids that tapped "Play again" on the results screen
        self.again_at = None    # when the rematch starts without the players who haven't tapped (time.time())
        self.map = G.DEFAULT_MAP  # "lab" or "street"; the host picks it in the lobby
        self.cap = MAX_PLAYERS    # how many players may join; the host picks it in the lobby
        self.duration = G.DEFAULT_DURATION  # match length in seconds; the host picks it in the lobby


# ---------------------------------------------------------------- helpers
def clean_cap(raw):
    """The host's player limit: a whole number from 2 up to MAX_PLAYERS; anything else means MAX_PLAYERS."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return MAX_PLAYERS
    return max(2, min(MAX_PLAYERS, n))


def clean_room_name(raw):
    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()[:12]


def clean_name(raw):
    """Tidy a typed player name: normalise look-alike characters, drop invisible/control characters."""
    s = unicodedata.normalize("NFKC", str(raw or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")
    return re.sub(r"\s+", " ", s).strip()[:12]


def name_key(name):
    """What 'the same name' means: ignores capitals and spaces (Bob = bob = B o b)."""
    return re.sub(r"\s", "", clean_name(name)).casefold()


def unique_name(room, raw, sid):
    """(final name, None) or (None, error). Blank names get Soldier, Soldier 2, ... automatically."""
    name = clean_name(raw)
    taken = {name_key(m["name"]) for s_, m in room.members.items() if s_ != sid}
    if not name:
        cand, n = "Soldier", 2
        while name_key(cand) in taken:
            cand, n = f"Soldier {n}", n + 1
        return cand, None
    if name_key(name) in taken:
        return None, f'The name "{name}" is already taken in this room. Pick another name and try again.'
    return name, None


def seat_of(room, device, sid):
    """The sid of another connection from the same device already inside this room, if any."""
    if device:
        for s_, m in room.members.items():
            if m["device"] == device and s_ != sid:
                return s_
    return None


def take_over_seat(room, new_sid, old_sid):
    """Same device came back (second tab, refresh, reconnect before the old socket timed out): move its
    existing player to the new connection. One device = one player per room; kills are kept."""
    m = room.members.pop(old_sid)
    room.members[new_sid] = m
    if old_sid in room.again:
        room.again.discard(old_sid)
        room.again.add(new_sid)
    sid_room.pop(old_sid, None)
    sid_room[new_sid] = room.code
    if room.host == old_sid:
        room.host = new_sid
    leave_room(room.code, sid=old_sid)
    join_room(room.code, sid=new_sid)
    socketio.emit("error_msg", {"msg": "You joined this room from another window, so this one was disconnected.", "gone": True}, to=old_sid)
    return m


SKIN_COUNT = 10                      # characters a player can pick (static/avatars.js lists them)


def pick_skin(room, wanted, slot):
    """The skin the player asked for if nobody in the room has it, otherwise the first free one."""
    taken = {m.get("skin") for m in room.members.values()}
    if isinstance(wanted, int) and not isinstance(wanted, bool) and 0 <= wanted < SKIN_COUNT and wanted not in taken:
        return wanted
    free = [i for i in range(SKIN_COUNT) if i not in taken]
    return free[0] if free else slot % SKIN_COUNT


def add_player(room, sid, name, device=None, skin=None):
    used = {m["id"] for m in room.members.values()}
    slot = next(i for i in range(MAX_PLAYERS) if i not in used)
    m = {"id": slot, "name": clean_name(name), "device": rankings.clean_device(device), "skin": pick_skin(room, skin, slot),
         "weapon": G.DEFAULT_PRIMARY, "paid_kills": 0, "wskin": {}}
    room.members[sid] = m
    room.game.add_player(slot, m["name"])
    if room.host is None:
        room.host = sid
    sid_room[sid] = room.code
    join_room(room.code, sid=sid)
    return m


def lobby_payload(room):
    host = room.members.get(room.host)
    return {
        "code": room.code,
        "state": room.state,
        "host": host["id"] if host else None,
        "max": room.cap,
        "duration": room.duration,
        "durations": list(G.DURATIONS),
        "target": G.TARGET_KILLS,
        "min": MIN_TO_START,
        "map": room.map,
        "weapons": G.weapon_table(),
        "players": sorted(
            ({"id": m["id"], "name": m["name"], "skin": m.get("skin", m["id"] % SKIN_COUNT),
              "weapon": m.get("weapon", G.DEFAULT_PRIMARY), "ws": m.get("wskin", {})} for m in room.members.values()),
            key=lambda m: m["id"],
        ),
        # players who tapped "Play again": the rematch starts once every player has
        "again": sorted(room.members[s]["id"] for s in room.again if s in room.members),
        "again_in": round(max(0.0, room.again_at - time.time()), 1) if room.again_at else None,
    }


def broadcast_lobby(room):
    socketio.emit("lobby", lobby_payload(room), to=room.code)


def remove_player(sid, check=True):
    code = sid_room.pop(sid, None)
    room = rooms.get(code)
    if not room or sid not in room.members:
        return
    m = room.members[sid]
    gone = room.game.players.get(m["id"])
    owed = (gone.kills - m.get("paid_kills", 0)) if gone else 0
    if owed > 0 and m.get("device"):
        socketio.start_background_task(pay_coins, [(sid, m["device"], owed)])
    room.game.remove_player(m["id"])
    del room.members[sid]
    room.again.discard(sid)
    leave_room(code, sid=sid)
    if not room.members:
        rooms.pop(code, None)  # game loop notices and exits
        return
    if room.host == sid:
        room.host = next(iter(room.members))
    if not room.again:
        room.again_at = None
    if check and maybe_rematch(room):    # someone leaving can complete the vote
        return
    if check:
        broadcast_lobby(room)


# ---------------------------------------------------------------- rankings
def save_result(room):
    """Match just finished: queue its result for the leaderboard (only 3+ player matches count)."""
    g = room.game
    entries = [
        {"id": m["id"], "device": m["device"], "name": m["name"], "kills": g.players[m["id"]].kills}
        for m in room.members.values() if m["id"] in g.players
    ]
    results = rankings.build_results(entries, g.winner)
    if results:
        socketio.start_background_task(rankings.record_match, results)
    pays = []
    for sid, m in room.members.items():
        p = g.players.get(m["id"])
        if p and m.get("device") and p.kills > m.get("paid_kills", 0):
            pays.append((sid, m["device"], p.kills - m.get("paid_kills", 0)))
            m["paid_kills"] = p.kills
    if pays:
        socketio.start_background_task(pay_coins, pays)


# ---------------------------------------------------------------- Link Coins
def pay_coins(pays):
    """pays: [(sid, device, kills)]. Adds the coins and tells each player what they got."""
    for sid, device, kills in pays:
        r = store.award(device, kills)
        if r:
            socketio.emit("coins", r, to=sid)


def load_equipped(room, sid):
    """Fetch this player's equipped weapon skins from the database, then tell the room."""
    m = room.members.get(sid)
    if not m or not m.get("device") or not store.enabled():
        return
    eq = store.equipped(m["device"])
    if sid in room.members and eq != m.get("wskin"):
        m["wskin"] = eq
        broadcast_lobby(room)


def apply_equipped(device, eq):
    """A player changed their skins in the Store: update every room they are sitting in."""
    for room in list(rooms.values()):
        changed = False
        for m in room.members.values():
            if m.get("device") == device:
                m["wskin"] = eq
                changed = True
        if changed:
            broadcast_lobby(room)


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
        if room.again_at:
            if snap["m"][0] != "over":
                room.again.clear()
                room.again_at = None
            elif time.time() >= room.again_at:
                maybe_rematch(room, force=True)     # the wait is up: go with whoever tapped Play again
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


@app.route("/api/store")
def api_store():
    resp = jsonify(store.view(rankings.clean_device(request.args.get("device"))))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def store_action(fn):
    data = request.get_json(silent=True) if (request.content_length or 0) < 1024 else None
    data = data if isinstance(data, dict) else {}
    device = rankings.clean_device(data.get("device"))
    if not device:
        return jsonify({"ok": False, "error": "unavailable"}), 400
    result = fn(device, data)
    if result["ok"] and result["state"]:
        apply_equipped(device, result["state"]["equipped"])
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/store/buy", methods=["POST"])
def api_store_buy():
    return store_action(lambda device, d: store.buy(device, d.get("skin")))


@app.route("/api/store/equip", methods=["POST"])
def api_store_equip():
    def go(device, d):
        wid = d.get("weapon")
        return store.equip(device, d.get("skin"), wid if isinstance(wid, int) and not isinstance(wid, bool) else None)
    return store_action(go)


@app.route("/api/alcatraz")
def api_alcatraz():
    try:
        alcatraz_tick()      # also opens it on a visit, in case the server was asleep at 8pm
    except Exception as exc:
        print("alcatraz: tick failed:", exc)
    room = rooms.get(alcatraz.NAME)
    resp = jsonify({"open": bool(room), "players": len(room.members) if room else 0})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/healthz")
def healthz():
    return "ok"


# ---------------------------------------------------------------- web app manifest
@app.route("/manifest.webmanifest")
def manifest():
    resp = app.send_static_file("manifest.webmanifest")
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp


# ---------------------------------------------------------------- ALCATRAZ (opens every night at 8pm Nigeria time)
def alcatraz_tick(now=None):
    """Keep ALCATRAZ open all night (reopening it if it empties); close it in the morning if nobody is in it."""
    night = alcatraz.night(now)
    room = rooms.get(alcatraz.NAME)
    if night is None:
        if room and not room.members:
            rooms.pop(alcatraz.NAME, None)
        return
    if room:                                          # already open
        return
    room = Room(alcatraz.NAME)
    room.map = "stairs"                                # ALCATRAZ always opens on the Staircase map
    rooms[alcatraz.NAME] = room
    roomnames.claim(alcatraz.NAME, alcatraz.DEVICE)   # keeps the name reserved so nobody else can create it


def alcatraz_loop():
    roomnames.claim(alcatraz.NAME, alcatraz.DEVICE)
    while True:
        try:
            alcatraz_tick()
        except Exception as exc:
            print("alcatraz: tick failed:", exc)
        socketio.sleep(30)


# ---------------------------------------------------------------- sockets
def enter_room(room, sid, name, device=None, skin=None):
    """Seat a connection in a room. Returns False (after telling the player why) if the name is taken."""
    dev = rankings.clean_device(device)
    old = seat_of(room, dev, sid)
    if old:
        m = take_over_seat(room, sid, old)          # keeps the existing name, id and kills
    else:
        final, err = unique_name(room, name, sid)
        if err:
            emit("error_msg", {"msg": err})
            return False
        remove_player(sid)  # in case they were in another room
        m = add_player(room, sid, final, device, skin)
    emit("joined", {"code": room.code, "you": m["id"]})
    socketio.start_background_task(load_equipped, room, sid)
    if room.state == "playing":
        emit("start", {"world": G.world_payload(room.map)})
    broadcast_lobby(room)
    return True


@socketio.on("create_room")
def on_create(data):
    data = data or {}
    # every room has a name: owned by the device that first used it, reusable by that device any time
    name = clean_room_name(data.get("room_name"))
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
        if enter_room(existing, request.sid, data.get("name"), device, data.get("skin")):
            existing.host = request.sid
            broadcast_lobby(existing)
        return
    if roomnames.claim(name, device) != device:         # someone claimed it a split second ago
        emit("error_msg", {"msg": f"The room name {name} belongs to someone else. Pick another."})
        return
    room = Room(name)
    room.cap = clean_cap(data.get("max_players"))
    rooms[name] = room
    enter_room(room, request.sid, data.get("name"), device, data.get("skin"))


@socketio.on("join")
def on_join(data):
    data = data or {}
    code = str(data.get("code", "")).strip().upper()
    room = rooms.get(code)
    if not room:
        if code == alcatraz.NAME:
            emit("error_msg", {"msg": "ALCATRAZ opens every night at 8pm (Nigeria time).", "gone": True})
        elif roomnames.owner_of(code):
            emit("error_msg", {"msg": f"{code} is closed right now. Ask the host to open it again.", "gone": True})
        else:
            emit("error_msg", {"msg": "Room not found. Check the name and try again.", "gone": True})
        return
    returning = seat_of(room, rankings.clean_device(data.get("device")), request.sid)
    cap = room.cap
    if not returning and len(room.members) >= cap and request.sid not in room.members:
        emit("error_msg", {"msg": f"This room is full ({cap} of {cap} players)."})
        return
    enter_room(room, request.sid, data.get("name"), data.get("device"), data.get("skin"))


@socketio.on("start_game")
def on_start():
    room = rooms.get(sid_room.get(request.sid))
    if not room or room.host != request.sid or room.state == "playing":
        return
    if len(room.members) < MIN_TO_START:
        emit("error_msg", {"msg": f"Need at least {MIN_TO_START} players to start."})
        return
    room.state = "playing"
    room.recorded = False
    for m in room.members.values():
        m["paid_kills"] = 0
    room.game.restart(room.map, room.duration)
    socketio.emit("start", {"world": G.world_payload(room.map)}, to=room.code)
    broadcast_lobby(room)
    if not room.loop_running:
        room.loop_running = True
        socketio.start_background_task(game_loop, room)


@socketio.on("set_map")
def on_set_map(data):
    room = rooms.get(sid_room.get(request.sid))
    map_id = (data or {}).get("map")
    if not room or room.host != request.sid or room.state != "lobby" or map_id not in G.MAPS:
        return
    room.map = map_id
    broadcast_lobby(room)


@socketio.on("set_cap")
def on_set_cap(data):
    """Host-only, lobby-only: how many players may be in the room (never below who is already in it)."""
    room = rooms.get(sid_room.get(request.sid))
    if not room or room.host != request.sid or room.state != "lobby":
        return
    room.cap = max(clean_cap((data or {}).get("max")), len(room.members))
    broadcast_lobby(room)


@socketio.on("set_duration")
def on_set_duration(data):
    """Host-only, lobby-only: match length in seconds (one of G.DURATIONS)."""
    room = rooms.get(sid_room.get(request.sid))
    try:
        secs = int((data or {}).get("duration"))
    except (TypeError, ValueError):
        return
    if not room or room.host != request.sid or room.state != "lobby" or secs not in G.DURATIONS:
        return
    room.duration = secs
    broadcast_lobby(room)


@socketio.on("set_weapon")
def on_set_weapon(data):
    """A player's primary weapon. Only in the lobby or on the game-over screen: it stays fixed during a match."""
    room = rooms.get(sid_room.get(request.sid))
    m = room.members.get(request.sid) if room else None
    try:
        wid = int((data or {}).get("weapon"))
    except (TypeError, ValueError):
        return
    if not m or wid not in G.PRIMARIES or not (room.state == "lobby" or room.game.phase == "over"):
        return
    m["weapon"] = wid
    room.game.set_primary(m["id"], wid)
    broadcast_lobby(room)


@socketio.on("swap")
def on_swap():
    room = rooms.get(sid_room.get(request.sid))
    m = room.members.get(request.sid) if room else None
    if m:
        room.game.swap(m["id"])


@socketio.on("reload")
def on_reload():
    room = rooms.get(sid_room.get(request.sid))
    m = room.members.get(request.sid) if room else None
    if m:
        room.game.reload(m["id"])


def maybe_rematch(room, force=False):
    """Start the next match once every player on the results screen has tapped Play again. After
    REMATCH_WAIT seconds (force=True) it starts anyway with the players who did; the rest go back to the menu."""
    if room.game.phase != "over" or not room.members:
        return False
    voters = [s for s in room.members if s in room.again]
    if len(voters) < len(room.members):
        if not force:
            return False
        if len(voters) < MIN_TO_START:      # not enough people want another round: everyone stays on the results screen
            room.again.clear()
            room.again_at = None
            socketio.emit("error_msg", {"msg": "Not enough players tapped Play again."}, to=room.code)
            broadcast_lobby(room)
            return False
        for s in [s for s in room.members if s not in room.again]:
            socketio.emit("error_msg", {"msg": "You didn't tap Play again, so the next match started without you.", "gone": True}, to=s)
            remove_player(s, check=False)
    room.again.clear()
    room.again_at = None
    room.recorded = False
    for m in room.members.values():
        m["paid_kills"] = 0
    room.game.restart(room.map, room.duration)
    broadcast_lobby(room)
    return True


@socketio.on("rematch")
def on_rematch():
    """Each player decides for themselves: tap once to vote for a rematch, tap again to take it back.
    The first tap starts a REMATCH_WAIT-second countdown for everyone else."""
    room = rooms.get(sid_room.get(request.sid))
    if not room or request.sid not in room.members or room.game.phase != "over":
        return
    if request.sid in room.again:
        room.again.discard(request.sid)
        if not room.again:
            room.again_at = None
    else:
        room.again.add(request.sid)
        if not room.again_at:
            room.again_at = time.time() + REMATCH_WAIT
    if not maybe_rematch(room):
        broadcast_lobby(room)


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


if os.environ.get("LS_NO_SCHEDULER") != "1":          # tests switch the nightly clock off
    socketio.start_background_task(alcatraz_loop)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"Link Strike running on http://0.0.0.0:{port}")
    socketio.run(app, host="0.0.0.0", port=port)
