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

def give(g, p, wid):
    """Put weapon wid in p's hands with a full magazine (as if it were the chosen primary)."""
    p.primary = wid
    g._equip(p)

def test_rocket_and_shotgun():
    g = new_game(2)
    a, b = g.players[0], g.players[1]
    put(a, 14, 29); put(b, 18, 29); b.x = a.x + 250; b.y = a.y
    give(g, a, 2)
    a.aim = 0.0; a.fire = True
    ex = []
    for _ in range(40):
        s = g.step(DT); ex += [e for e in s["e"] if e[0] == "ex"]
        if ex: break
    assert ex and b.hp < 100, "rocket should explode and hurt"
    a.fire = False
    # self-damage / knockback exists
    put(a, 14, 29); a.hp = 100; a.invuln = 0; a.cd = 0; give(g, a, 2)
    a.aim = math.pi / 2; a.fire = True      # shoot floor
    run(g, 0.5)
    assert a.hp < 100, "should hurt yourself with a point-blank rocket"
    # shotgun
    put(a, 14, 29); put(b, 18, 29); b.x = a.x + 120; b.y = a.y; b.hp = 100; b.invuln = 0
    a.hp = 100; give(g, a, 1); a.aim = 0.0; a.fire = True; a.cd = 0
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
    import street_map, stairs_map
    for pk in (G.PICKUPS, street_map.PICKUPS, stairs_map.PICKUPS):       # health only: no weapon pickups on any map
        assert pk and all(k == "health" for k, _, _ in pk), pk
    g = new_game(1); p = g.players[0]
    p.hp = 50
    h = next(k for k, pk in enumerate(G.PICKUPS) if pk[0] == "health")
    _, c, r = G.PICKUPS[h]; put(p, c, r); p.x = c * 40 + 6
    run(g, 0.2)
    assert p.hp == 90
    print("pickups ok")

def test_snapshot_shape():
    g = new_game(3); s = g.step(DT)
    assert len(s["p"]) == 3 and len(s["p"][0]) == 15 and len(s["k"]) == len(G.PICKUPS)
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
    g = new_game(3); g.restart()
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

def test_catalogue():
    cat = G.catalogue()
    root = os.path.join(os.path.dirname(__file__), "..", "static")
    assert G.SECONDARY == 0 and G.DEFAULT_PRIMARY in G.PRIMARIES and G.SECONDARY not in G.PRIMARIES
    assert set(cat["weapons"]) == {str(k) for k in G.WEAPONS}
    cats = {c for c, _ in G.CATEGORIES}
    for wid in G.PRIMARIES:
        assert G.WEAPONS[wid]["cat"] in cats, wid
    for k, w in G.WEAPONS.items():
        assert w["mag"] >= 1 and w["reload"] > 0 and w["cd"] > 0, k
        assert os.path.isfile(os.path.join(root, "img", "wpn", w["icon"] + ".png")), w["icon"]
        assert os.path.isfile(os.path.join(root, "img", "wpn", "hand_" + (str(k) if k < 3 else w["icon"]) + ".png")), k
        for snd in (w["snd"], w["rsnd"]):
            assert os.path.isfile(os.path.join(root, "audio", snd + ".wav")), snd
        assert 0.1 < w["muz"] < 80, (k, w["muz"])
    for n in ("weapon_switch", "dry_click"):
        assert os.path.isfile(os.path.join(root, "audio", n + ".wav")), n
    import json; json.dumps(cat)
    print("catalogue ok:", len(G.PRIMARIES), "primaries")

def test_magazine_and_auto_reload():
    g = new_game(2); a, b = g.players[0], g.players[1]
    put(a, 14, 29); put(b, 18, 29);
    give(g, a, 4)                                    # M4A1: 30 rounds, 2.0 s reload
    assert a.wpn == 4 and a.ammo == 30 and a.reload_t == 0
    a.aim = math.pi / 2; a.fire = True               # shoot at the floor so nobody dies
    shots = 0
    for _ in range(int(4.0 / DT)):
        s = g.step(DT); shots += sum(1 for e in s["e"] if e[0] == "sh" and e[1] == 0)
        if a.reload_t > 0: break
    assert shots == 30, f"a 30 round magazine should fire exactly 30 shots, fired {shots}"
    assert a.ammo == 0 and abs(a.reload_t - G.WEAPONS[4]["reload"]) < 0.1, (a.ammo, a.reload_t)
    # cannot fire while reloading, even with the trigger held
    sh = 0; ev = []
    for _ in range(int(1.0 / DT)):
        s = g.step(DT); ev += s["e"]; sh += sum(1 for e in s["e"] if e[0] == "sh")
    assert sh == 0 and a.reload_t > 0.5
    run(g, 1.2)
    ev = []
    for _ in range(4):
        ev += g.step(DT)["e"]
    assert a.reload_t == 0 or a.ammo > 0
    print("magazine + auto reload ok")

def test_reload_events_and_manual_reload():
    g = new_game(1); a = g.players[0]
    put(a, 14, 29); give(g, a, 3); a.mags[3] = 10
    assert g.reload(0) is True and g.reload(0) is False       # second press does nothing
    s = g.step(DT)
    assert any(e[0] == "rl" and e[1] == 0 and e[2] == 3 for e in g.events + s["e"]) or a.reload_t > 0
    ev = []
    for _ in range(int((G.WEAPONS[3]["reload"] + 0.3) / DT)):
        ev += g.step(DT)["e"]
    assert a.ammo == 30 and a.reload_t == 0 and any(e[0] == "rd" for e in ev), (a.ammo, a.reload_t)
    assert g.reload(0) is False                                # full magazine: nothing to reload
    print("manual reload ok")

def test_switch_weapons():
    g = new_game(1); a = g.players[0]
    put(a, 14, 29); give(g, a, 6)                             # AWM
    assert a.wpn == 6 and a.slot == 0
    a.mags[6] = 2; g.reload(0)
    assert a.reload_t > 0
    assert g.switch(0) is True and a.wpn == G.SECONDARY and a.slot == 1
    assert a.reload_t == 0, "swapping cancels the reload"
    assert a.mags[G.SECONDARY] == 15 and a.mags[6] == 2, "each weapon keeps its own magazine"
    assert g.switch(0) is False, "swap spam is rate limited"
    run(g, 0.4)
    assert g.switch(0, 0) is True and a.wpn == 6 and a.slot == 0
    run(g, 0.4)
    assert g.switch(0, 0) is False, "already holding it"
    # cannot fire right after a swap
    a.aim = math.pi / 2; a.fire = True; a.cd = 0
    g.switch(0, 1); assert a.cd >= G.SWITCH_S - 1e-9
    print("switch ok")

def test_primary_choice_rules():
    g = new_game(2); a, b = g.players[0], g.players[1]
    assert a.primary == G.DEFAULT_PRIMARY
    for bad in (0, 99, -1, "x", None, 3.7 if False else 12):
        assert g.set_primary(0, bad) is False, bad
    assert a.primary == G.DEFAULT_PRIMARY
    assert g.set_primary(0, 6) is True and g.set_primary(1, "10") is True
    assert a.primary == 6 and b.primary == 10
    g.restart()                                                # chosen weapons are what you spawn with, with full mags
    assert a.wpn == 6 and a.ammo == 5 and b.wpn == 10 and b.ammo == 100
    put(a, 14, 29); a.dead = True; a.dead_t = 0.01; g.step(DT); g.step(DT)
    assert a.wpn == 6 and a.ammo == 5, "respawn keeps the chosen primary"
    print("primary choice ok")

def test_every_weapon_fires_and_balances():
    for wid in G.PRIMARIES + [G.SECONDARY]:
        g = new_game(2); a, b = g.players[0], g.players[1]
        put(a, 14, 29); put(b, 18, 29); b.x = a.x + 200; b.y = a.y; b.invuln = 0
        give(g, a, wid); a.aim = 0.0; a.fire = True
        s = run(g, 0.4)
        assert b.hp < 100 or wid == 2, (wid, b.hp)
        w = G.WEAPONS[wid]
        if wid not in (1, 2):
            dps = w["dmg"] / w["cd"]
            assert 50 <= dps <= 160 or wid == 6, (wid, dps)    # nothing wildly over or under powered (AWM is burst)
    print("all weapons fire ok")

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ALL PASSED")
