"""Run with:  python tests/test_game.py   (no extra packages needed)"""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game as G
from collections import deque

DT = 1 / 30


def skip_count(g):
    """Run the 3-2-1 countdown that follows restart()."""
    for _ in range(int((G.COUNTDOWN_S + 0.2) / DT)): g.step(DT)

def free_cell(c, r):
    return not G.solid(c, r)

def reachable_set():
    """Tile-level flood fill for a 1-wide, 2-tall flyer (jetpack = any direction)."""
    start = (3, 40)
    seen, q = {start}, deque([start])
    while q:
        c, r = q.popleft()
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c + dc, r + dr)
            if n in seen:
                continue
            if free_cell(*n) and free_cell(n[0], n[1] - 1):   # feet tile + head tile
                seen.add(n); q.append(n)
    return seen

def test_map():
    assert len(G.GRID) == G.ROWS and all(len(r) == G.COLS for r in G.GRID)
    reach = reachable_set()
    assert len(G.SPAWNS) == 6 and len(G.BACKUP_SPAWNS) == 3
    for col, row in G.SPAWNS + G.BACKUP_SPAWNS:
        assert free_cell(col, row) and free_cell(col, row - 1) and free_cell(col, row - 2), f"spawn blocked {col},{row}"
        below = G.GRID[row + 1][col]
        assert below in "#SC=", f"spawn {col},{row} not on floor ({below!r})"
        assert (col, row) in reach, f"spawn unreachable {col},{row}"
    for kind, col, row in G.PICKUPS:
        assert free_cell(col, row), f"pickup inside wall {kind} {col},{row}"
        assert (col, row) in reach, f"pickup unreachable {kind} {col},{row}"
    print("map ok:", len(reach), "flyable tiles; all spawns/pickups connected")

def new_game(n=2):
    g = G.Game()
    for i in range(n):
        g.add_player(i, f"P{i}")
    return g

def put(p, col, row):
    p.x, p.y = G.spawn_xy(col, row); p.vx = p.vy = 0

def run(g, secs):
    snap = None
    for _ in range(int(secs / DT)):
        snap = g.step(DT)
    return snap

def test_gravity_and_ground():
    g = new_game(1); p = g.players[0]
    p.x, p.y = G.spawn_xy(28, 40)[0], G.spawn_xy(28, 40)[1] - 100
    run(g, 1.0)
    assert p.ground and abs(p.y - G.spawn_xy(28, 40)[1]) < 1, (p.y, p.ground)
    print("gravity/landing ok")

def test_jetpack_climb():
    g = new_game(1); p = g.players[0]
    put(p, 39, 40)                       # tunnel floor, straight under the floor hatch + roof hatch (cols 38-41)
    p.x = 39 * 40 + 6
    p.my = -1.0
    run(g, 5.0)
    assert p.y < 9 * 40 - G.PH - 40, f"jetpack didn't get up through both hatches (y={p.y})"
    print("jetpack climb ok, y =", round(p.y))

def test_walls_block():
    g = new_game(1); p = g.players[0]
    p.x, p.y = 24 * 40 + 6, 15 * 40.0    # beside the chamber wall (rows 11-26 are solid)
    p.mx = 1.0
    run(g, 0.15)
    assert p.x + G.PW <= 25 * 40 + 0.1, p.x
    put(p, 24, 29); p.mx = 1.0           # the gate (rows 27-29) lets you walk in
    run(g, 1.0)
    assert p.x > 26 * 40, p.x
    print("walls + gate ok, x =", round(p.x))

def test_oneway():
    g = new_game(1); p = g.players[0]
    put(p, 30, 40); p.x = 30 * 40 + 6
    p.my = -1.0; run(g, 0.9)           # fly up through the tunnel catwalk (row 36)
    p.my = 0.0; run(g, 2.5)            # fall back: should land ON it
    assert p.ground and abs(p.y - (36 * 40 - G.PH)) < 1, p.y
    print("one-way catwalk ok, landed y =", round(p.y))

def test_combat_and_win():
    g = new_game(2)
    a, b = g.players[0], g.players[1]
    put(a, 14, 29); put(b, 18, 29)
    b.x = a.x + 300; b.y = a.y
    a.aim = 0.0; a.fire = True
    snap = run(g, 0.3)
    assert b.hp < 100, "pistol didn't hit"
    for _ in range(300):
        snap = g.step(DT)
        if b.dead: break
    assert b.dead and a.kills == 1
    # kill event emitted somewhere
    print("pistol kill ok; victim hp", b.hp, "kills", a.kills)
    # respawn
    a.fire = False
    run(g, G.RESPAWN_S + 0.2)
    assert not b.dead and b.hp == 100 and b.invuln > 0
    # win at 10
    a.kills = 9
    put(b, 18, 29); put(a, 14, 29); b.x = a.x + 200; b.y = a.y; b.invuln = 0
    a.fire = True; a.aim = 0.0
    for _ in range(400):
        snap = g.step(DT)
        if g.phase == "final": break
    assert g.phase == "final" and g.winner == 0, (g.phase, g.winner)
    # 3-second finisher window: no more damage or kills, then the results screen
    k0 = a.kills
    for _ in range(int((G.FINAL_S - 0.5) / DT)): g.step(DT)
    assert g.phase == "final" and a.kills == k0
    for _ in range(int(1.0 / DT)): g.step(DT)
    assert g.phase == "over" and g.winner == 0, (g.phase, g.winner)
    print("first-to-10 win ok")
    g.restart()
    assert g.phase == "count" and a.kills == 0 and b.kills == 0
    skip_count(g)
    assert g.phase == "play"
    print("restart ok")

def test_rocket_and_shotgun():
    g = new_game(2)
    a, b = g.players[0], g.players[1]
    put(a, 14, 29); put(b, 18, 29); b.x = a.x + 250; b.y = a.y
    a.wpn, a.ammo = 2, 4
    a.aim = 0.0; a.fire = True
    ex = []
    for _ in range(40):
        s = g.step(DT); ex += [e for e in s["e"] if e[0] == "ex"]
        if ex: break
    assert ex and b.hp < 100, "rocket should explode and hurt"
    a.fire = False
    # self-damage / knockback exists
    put(a, 14, 29); a.hp = 100; a.invuln = 0; a.cd = 0; a.wpn, a.ammo = 2, 4
    a.aim = math.pi / 2; a.fire = True      # shoot floor
    run(g, 0.5)
    assert a.hp < 100, "should hurt yourself with a point-blank rocket"
    # shotgun
    put(a, 14, 29); put(b, 18, 29); b.x = a.x + 120; b.y = a.y; b.hp = 100; b.invuln = 0
    a.hp = 100; a.wpn, a.ammo = 1, 8; a.aim = 0.0; a.fire = True; a.cd = 0
    run(g, 0.15)
    assert b.hp < 70, f"shotgun at 120px should do big damage, hp={b.hp}"
    print("rocket/shotgun ok; ammo left", a.ammo)

def test_walls_stop_bullets():
    g = new_game(2)
    a, b = g.players[0], g.players[1]
    # a outside the chamber wall (cols 25-26), b inside, same height: the wall must stop the shot
    ay, by = G.spawn_xy(23, 16)[1], G.spawn_xy(30, 16)[1]
    a.x, b.x = G.spawn_xy(23, 16)[0], G.spawn_xy(30, 16)[0]
    a.aim = 0.0; a.fire = True
    for _ in range(10):
        a.y, b.y = ay, by; a.vy = b.vy = 0
        g.step(DT)
    assert b.hp == 100, "bullet passed through the wall"
    print("walls stop bullets ok")

def test_spawn_safety():
    g = new_game(2)
    a, b = g.players[0], g.players[1]
    for _ in range(40):                  # whichever spot b stands on, a never respawns in sight within 1100px
        col, row = G.SPAWNS[_ % len(G.SPAWNS)]
        put(b, col, row); b.dead = False
        g.clock += 10                    # forget recent use
        spot = g._pick_spawn(a)
        x, y = G.spawn_xy(*spot)
        d = math.hypot(x - b.x, y - b.y)
        assert d > 700, f"spawned {d:.0f}px from an enemy (enemy at {col},{row}, picked {spot})"
    # recent-use protection: the spot just used is not picked again straight away
    first = g._pick_spawn(a); g.spawn_used[first] = g.clock
    assert g._pick_spawn(a) != first
    # a full room of 6 gets six different primary spawns
    g6 = new_game(6); g6.restart(); skip_count(g6)
    spots = {(round(p.x), round(p.y)) for p in g6.players.values()}
    assert len(spots) == 6
    print("spawn safety ok")

def test_pickups():
    g = new_game(1); p = g.players[0]
    assert all(pk[0] == "health" for pk in g.map.pickups), "only medkits spawn on the map"
    assert g.map.pickups, "map still has medkits"
    wpn = p.wpn
    p.hp = 50
    _, c, r = g.map.pickups[0]; put(p, c, r); p.x = c * 40 + 6
    run(g, 0.2)
    assert p.hp == 90 and p.wpn == wpn
    print("pickups ok")

def test_loadout_and_reload():
    g = new_game(2); a, b = g.players[0], g.players[1]
    g.set_primary(0, 11)                       # AWM
    g.restart(); skip_count(g)
    assert a.wpn == 11 and a.ammo == G.WEAPONS[11]["mag"] and a.mags[0] == G.WEAPONS[0]["mag"]
    g.set_primary(0, 999); assert a.primary == 11, "unknown weapon ids are ignored"
    # magazine drains, then reloads on its own
    a.invuln = 0; a.aim = 0.0; a.fire = True; a.cd = 0
    run(g, 0.05)
    assert a.ammo == G.WEAPONS[11]["mag"] - 1
    a.ammo = 1; a.cd = 0; run(g, 0.05)
    assert a.ammo == 0 and a.reload_t > 0, "empty magazine starts a reload"
    a.fire = False
    run(g, G.WEAPONS[11]["reload"] + 0.2)
    assert a.ammo == G.WEAPONS[11]["mag"] and a.reload_t == 0
    # swap to the pistol and back; each weapon keeps its own magazine; swapping cancels a reload
    a.ammo = 2; g.swap(0)
    assert a.wpn == 0 and a.ammo == G.WEAPONS[0]["mag"] and a.mags[11] == 2
    g.reload(0); g.reload(0)                   # full mag: nothing to reload
    assert a.reload_t == 0
    a.ammo = 3; g.reload(0); assert a.reload_t > 0
    g.swap(0)
    assert a.wpn == 11 and a.ammo == 2 and a.reload_t == 0
    # death and respawn: full mags, primary back in hand
    a.wpn, a.ammo = 0, 1; a.dead = True; g._respawn(a)
    assert a.wpn == 11 and a.ammo == G.WEAPONS[11]["mag"] and a.mags[0] == G.WEAPONS[0]["mag"]
    print("loadout/reload ok")

def test_snapshot_shape():
    g = new_game(3); s = g.step(DT)
    assert len(s["p"]) == 3 and len(s["p"][0]) == 13 and len(s["k"]) == len(g.map.pickups)
    import json; json.dumps(s)
    print("snapshot ok,", len(json.dumps(s)), "bytes")

def test_rankings_rules():
    import rankings as R
    mk = lambda i, k: {"id": i, "device": f"device-{i:04d}", "name": f"P{i}", "kills": k}
    three = [mk(0, 10), mk(1, 4), mk(2, 7)]
    res = R.build_results(three, 0)
    assert [r["won"] for r in res] == [True, False, False] and [r["kills"] for r in res] == [10, 4, 7]
    assert R.build_results(three[:2], 0) == [], "2-player match must not count"
    assert R.build_results(three, -1) == [], "unfinished match must not count"
    anon = [mk(0, 10), mk(1, 4), dict(mk(2, 7), device=None)]
    assert len(R.build_results(anon, 0)) == 2, "players without a device id are skipped"
    assert R.clean_device("abcd-1234-efgh") and not R.clean_device("x") and not R.clean_device("a b c d e f g h")
    print("ranking rules ok")

def test_rankings_offline():
    import os, rankings as R
    os.environ.pop("DATABASE_URL", None)
    assert R.leaderboard(3, "device-0000") == {"enabled": False, "top": [], "me": None}
    assert R.record_match([{"device": "device-0000", "name": "A", "kills": 10, "won": True}]) is False
    os.environ["DATABASE_URL"] = "postgresql://u:p@127.0.0.1:1/db"      # nothing listening: must not raise
    assert R.leaderboard(3)["top"] == [] and R.record_match([{"device": "device-0000", "name": "A", "kills": 1, "won": False}]) is False
    os.environ.pop("DATABASE_URL")
    print("offline fallback ok")

# ------------------------------------------------------------------ match rules
def kill(g, killer, victim):
    v = g.players[victim]; v.invuln = 0
    g._damage(v, 999, killer, 0)

def test_kill_counts_and_match_goes_on():
    g = new_game(3); g.restart(); skip_count(g)
    kill(g, 0, 1)
    assert g.players[0].kills == 1 and g.players[1].deaths == 1
    kill(g, 0, 1)                                   # already dead: no double kill
    assert g.players[0].kills == 1 and g.players[1].deaths == 1
    p = g.players[2]; p.invuln = 0
    g._damage(p, 999, 2, 2)                         # self-kill: a death, no kill
    assert p.deaths == 1 and p.kills == 0
    run(g, 5); assert g.phase == "play"
    print("kills ok")

def test_no_win_results_keep_kills():
    import rankings as R
    es = [{"id": i, "device": f"device-000{i}", "name": f"P{i}", "kills": i} for i in range(3)]
    res = R.build_results(es, -1, ranked_win=False)
    assert len(res) == 3 and not any(r["won"] for r in res) and [r["kills"] for r in res] == [0, 1, 2]
    assert R.build_results(es[:2], -1, ranked_win=False) == []
    print("rankings ok")

def _match(n=3, duration=None):
    g = new_game(n); g.restart(None, duration); return g

def test_countdown_freezes_everyone():
    g = _match(2); a = g.players[0]
    assert g.phase == "count" and abs(g.count_t - G.COUNTDOWN_S) < 1e-6
    a.mx, a.fire = 1.0, True
    x0 = a.x
    for _ in range(int(2.0 / DT)): g.step(DT)
    assert g.phase == "count" and a.x == x0 and not g.projs
    assert g.time_left == g.duration                  # the clock has not started
    assert g.step(DT)["m"][0] == "count"
    skip_count(g)
    assert g.phase == "play"
    print("countdown ok")

def test_timer_runs_and_is_in_snapshot():
    g = _match(2); skip_count(g)
    t0 = g.time_left
    for _ in range(int(10 / DT)): snap = g.step(DT)
    assert abs((t0 - g.time_left) - 10) < 0.5
    assert snap["m"][0] == "play" and abs(snap["m"][2] - g.time_left) < 0.06 and snap["m"][3] == 0
    print("timer ok")

def test_time_up_highest_kills_wins():
    g = _match(3, 180); skip_count(g)
    g.players[1].kills = 4; g.players[0].kills = 2; g.players[2].kills = 1
    g.time_left = 0.05
    for _ in range(5): g.step(DT)
    assert g.phase == "over" and g.winner == 1 and g.reason == "time" and g.time_left == 0
    print("time-up winner ok")

def test_tie_goes_to_sudden_death():
    g = _match(3); skip_count(g)
    g.players[0].kills = 3; g.players[1].kills = 3; g.players[2].kills = 1
    g.time_left = 0.05
    for _ in range(5): g.step(DT)
    assert g.phase == "play" and g.sudden and sorted(g.sd_ids) == [0, 1]
    snap = g.step(DT)
    assert snap["m"][3] == 1 and sorted(snap["m"][4]) == [0, 1]
    for _ in range(int(20 / DT)): g.step(DT)          # no clock in sudden death
    assert g.phase == "play"
    # a kill by the player who was NOT tied does not end it
    g.players[1].invuln = 0; kill(g, 2, 1)
    assert g.phase == "play" and g.sudden
    # a kill by a tied player does
    g.players[2].invuln = 0; g.players[0].invuln = 0; kill(g, 0, 2)
    assert g.phase == "final" and g.winner == 0 and g.reason == "sudden"
    for _ in range(int((G.FINAL_S + 0.5) / DT)): g.step(DT)
    assert g.phase == "over"
    print("sudden death ok")

def test_sudden_death_leaver_does_not_hang():
    g = _match(3); skip_count(g)
    g.players[0].kills = g.players[1].kills = 2
    g.time_left = 0.05
    for _ in range(5): g.step(DT)
    assert g.sudden
    g.remove_player(1)
    g.step(DT)
    assert g.phase == "over" and g.winner == 0
    print("sudden death leaver ok")

def test_first_to_ten_still_wins_before_time():
    g = _match(2); skip_count(g)
    g.players[0].kills = G.TARGET_KILLS - 1
    kill(g, 0, 1)
    assert g.phase == "final" and g.winner == 0 and g.reason == "kills"
    print("first to 10 ok")

def test_duration_choice_and_rematch():
    g = _match(2, 600); assert g.duration == 600 and g.time_left == 600
    g.restart(None, 12345)                                 # not an allowed length: keeps 600
    assert g.duration == 600
    g.restart(None, 180); assert g.time_left == 180
    g.phase = "over"; g.restart(); assert g.phase == "count" and g.time_left == 180 and not g.sudden
    print("durations ok")

def test_damage_event_for_client_feedback():
    g = new_game(2); g.restart(); skip_count(g)
    v = g.players[1]; v.invuln = 0; v.hp = 100; g.events.clear()
    g._damage(v, 22, 0, 3)
    dm = [e for e in g.events if e[0] == "dm"]
    assert len(dm) == 1 and dm[0][1:4] == [1, 0, 22] and dm[0][6] == 0
    g.events.clear(); g._damage(v, 999, 0, 3)
    dm = [e for e in g.events if e[0] == "dm"]
    assert dm and dm[0][6] == 1 and any(e[0] == "k" for e in g.events)   # kill flag set, kill event still sent
    print("damage event ok")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ALL PASSED")
