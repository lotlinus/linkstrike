"""Run with:  python tests/test_game.py   (no extra packages needed)"""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game as G
from collections import deque

DT = 1 / 30

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
        if g.phase == "over": break
    assert g.phase == "over" and g.winner == 0, (g.phase, g.winner)
    print("first-to-10 win ok")
    g.restart()
    assert g.phase == "play" and a.kills == 0 and b.kills == 0
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
    g6 = new_game(6); g6.restart()
    spots = {(round(p.x), round(p.y)) for p in g6.players.values()}
    assert len(spots) == 6
    print("spawn safety ok")

def test_pickups():
    g = new_game(1); p = g.players[0]
    i = next(k for k, pk in enumerate(G.PICKUPS) if pk[0] == 1)
    _, c, r = G.PICKUPS[i]
    put(p, c, r); p.x = c * 40 + 6
    s = run(g, 0.2)
    assert p.wpn == 1 and p.ammo == 8 and g.pk_up[i] is False
    p.hp = 50
    h = next(k for k, pk in enumerate(G.PICKUPS) if pk[0] == "health")
    _, c, r = G.PICKUPS[h]; put(p, c, r); p.x = c * 40 + 6
    run(g, 0.2)
    assert p.hp == 90
    print("pickups ok")

def test_snapshot_shape():
    g = new_game(3); s = g.step(DT)
    assert len(s["p"]) == 3 and len(s["p"][0]) == 14 and len(s["k"]) == len(G.PICKUPS)
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

# ------------------------------------------------------------------ team multiplayer
def team_game(n):
    g = G.Game()
    for i in range(n):
        g.add_player(i, f"P{i}")
    g.restart("team")
    return g

def kill(g, killer, victim):
    v = g.players[victim]; v.invuln = 0
    g._damage(v, 999, killer, 0)

def test_team_allocation():
    expect = {2: (1, 1), 3: (2, 1), 4: (2, 2), 5: (3, 2), 6: (4, 2)}   # 6 = room max
    for n, (s, h) in expect.items():
        assert team_game(n).team_counts() == (s, h), n
    for n, s in {8: 5, 10: 6, 12: 7, 15: 9}.items():                  # spec table (beyond today's room size)
        assert G.Game.survivor_count(n) == s, n
    print("team allocation ok")

def test_team_conversion_and_stats():
    g = team_game(4)
    surv = [p.id for p in g.players.values() if p.team == G.SURVIVORS]
    hunt = [p.id for p in g.players.values() if p.team == G.HUNTERS]
    a, b = surv[0], hunt[0]
    kill(g, a, b)
    assert g.players[b].team == G.SURVIVORS and g.players[a].team == G.SURVIVORS
    assert g.players[a].kills == 1 and g.players[b].deaths == 1 and g.team_counts() == (3, 1)
    kill(g, a, b)                                   # already dead: no double kill / conversion
    assert g.players[a].kills == 1 and g.players[b].deaths == 1
    g.players[b].dead = False; g.players[b].invuln = 0
    kill(g, hunt[1], b)                             # converts back to the Hunters
    assert g.players[b].team == G.HUNTERS and g.players[b].deaths == 2 and g.players[hunt[1]].kills == 1
    g.players[b].dead = False
    assert g.players[b].kills == 0 and g.team_counts() == (2, 2)
    print("conversion + persistent stats ok")

def test_no_friendly_fire_and_suicide():
    g = team_game(4)
    surv = [p.id for p in g.players.values() if p.team == G.SURVIVORS]
    before = g.players[surv[1]].hp
    g._damage(g.players[surv[1]], 50, surv[0], 0)
    assert g.players[surv[1]].hp == before, "teammates must not hurt each other"
    p = g.players[surv[0]]; p.invuln = 0
    g._damage(p, 999, surv[0], 2)                   # self-kill: death counts, team stays
    assert p.deaths == 1 and p.kills == 0 and p.team == G.SURVIVORS
    print("friendly fire / suicide ok")

def test_team_timeout_and_freeze():
    g = team_game(4)                                # 2 v 2 -> draw
    run(g, G.TEAM_MATCH_S + 1)
    snap = g._snapshot()
    assert g.phase == "over" and g.winner_team == 0 and snap["m"][4:6] == [2, 2]
    surv = [p.id for p in g.players.values() if p.team == G.SURVIVORS]
    hunt = [p.id for p in g.players.values() if p.team == G.HUNTERS]
    kill(g, surv[0], hunt[0])                       # late event: must change nothing
    assert g.team_counts() == (2, 2) and g.players[surv[0]].kills == 0 and g.winner_team == 0
    g2 = team_game(5)                               # 3 v 2 -> Survivors by population
    run(g2, G.TEAM_MATCH_S + 1)
    assert g2.winner_team == G.SURVIVORS
    print("timeout + freeze ok")

def test_total_conversion_and_disconnect():
    g = team_game(3)                                # 2 v 1
    surv = [p.id for p in g.players.values() if p.team == G.SURVIVORS]
    h = next(p.id for p in g.players.values() if p.team == G.HUNTERS)
    kill(g, surv[0], h)
    assert g.phase == "over" and g.winner_team == G.SURVIVORS and g.final_counts == (3, 0)
    g = team_game(3)
    h = next(p.id for p in g.players.values() if p.team == G.HUNTERS)
    g.remove_player(h)                              # last Hunter leaves
    assert g.phase == "over" and g.winner_team == G.SURVIVORS
    g = team_game(4)
    g.remove_player(next(iter(g.players)))          # ghost players are gone at once
    assert sum(g.team_counts()) == 3
    print("total conversion + disconnect ok")

def test_solo_mode_unchanged():
    g = new_game(3); g.restart("solo")
    assert g.mode == "solo" and all(p.team == 0 for p in g.players.values())
    kill(g, 0, 1)
    assert g.players[0].kills == 1 and g.players[1].team == 0 and g.players[1].deaths == 1
    run(g, 5); assert g.phase == "play"
    print("solo mode ok")

def test_team_rankings():
    import rankings as R
    es = [{"id": i, "device": f"device-000{i}", "name": f"P{i}", "kills": i} for i in range(3)]
    res = R.build_results(es, -1, ranked_win=False)
    assert len(res) == 3 and not any(r["won"] for r in res) and [r["kills"] for r in res] == [0, 1, 2]
    assert R.build_results(es[:2], -1, ranked_win=False) == []
    print("team rankings ok")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ALL PASSED")
