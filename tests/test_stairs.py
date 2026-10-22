"""Staircase map checks (plain asserts, no extra packages):  python tests/test_stairs.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game as G
import stairs_map as SM

M = G.MAPS["stairs"]
STAND = G.SOLIDS + G.ONE_WAY


def free(c, r):
    return not G.solid(c, r, M.grid)


def test_shape():
    assert (SM.COLS, SM.ROWS, SM.T) == (G.COLS, G.ROWS, G.TILE)
    assert len(M.grid) == G.ROWS and all(len(r) == G.COLS for r in M.grid)
    assert set("".join(M.grid)) <= set("#SC=.")


def test_spawns_and_pickups_stand_on_something():
    assert len(M.spawns) == 6 and len(M.backups) == 3
    for col, row in M.spawns + M.backups:
        assert M.grid[row + 1][col] in STAND, ("no floor under spawn", col, row)
        assert free(col, row) and free(col, row - 1), ("no headroom at spawn", col, row)
        assert free(col + 1, row), ("spawn jammed against a wall", col, row)
    for kind, col, row in M.pickups:
        assert M.grid[row + 1][col] in STAND, ("pickup floats", kind, col, row)
        assert free(col, row), ("pickup inside a block", kind, col, row)
    kinds = [k for k, _, _ in M.pickups]
    assert kinds.count("health") >= 5 and kinds.count(1) >= 4 and kinds.count(2) >= 2


def test_everything_is_connected():
    """A flying player (2 tiles tall, 1 wide) can get from any spawn to every spawn and pickup."""
    def ok(c, r):
        return 0 < c < G.COLS - 1 and 1 <= r < G.ROWS and free(c, r) and free(c, r - 1)
    start = M.spawns[0]
    seen, todo = {start}, [start]
    while todo:
        c, r = todo.pop()
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c + dc, r + dr)
            if n not in seen and ok(*n):
                seen.add(n)
                todo.append(n)
    for col, row in M.spawns + M.backups:
        assert (col, row) in seen, ("spawn cut off", col, row)
    for kind, col, row in M.pickups:
        assert (col, row) in seen, ("pickup cut off", kind, col, row)


def _walk(col, row, mx, secs):
    g = G.Game("stairs")
    p = g.add_player(0, "A")
    p.x, p.y = col * G.TILE + 6, (row + 1) * G.TILE - G.PH - 0.01
    p.vx = p.vy = 0
    p.mx, p.my = mx, 0
    for _ in range(int(secs * 30)):
        p.mx, p.my = mx, 0
        g._physics(p, 1 / 30)
    return p


def test_walk_up_right_stair_to_the_stub():
    p = _walk(56, 27, 1, 4)                           # hall floor, walk right, no jetpack
    assert p.ground and abs(p.y - (G.TILE * 15 - G.PH)) < 1 and p.x > 70 * G.TILE, (p.x, p.y)


def test_walk_up_left_stair_to_the_mezzanine():
    p = _walk(3, 24, 1, 1.5)                          # on the first step, walk right
    assert p.ground and abs(p.y - (G.TILE * 15 - G.PH)) < 1 and p.x > 14 * G.TILE, (p.x, p.y)


def test_walk_through_corridor_door_from_the_upper_stair():
    p = _walk(26, 7, 1, 2)
    assert p.ground and abs(p.y - (G.TILE * 8 - G.PH)) < 1 and p.x > 31 * G.TILE, (p.x, p.y)


def test_no_autostep_on_other_maps():
    g = G.Game("street")
    p = g.add_player(0, "A")
    p.x, p.y = 29 * G.TILE - G.PW - 2, 30 * G.TILE - G.PH          # beside the cover wall (2 tiles high)
    p.vx = p.vy = 0
    for _ in range(30):
        p.mx, p.my = 1, 0
        g._physics(p, 1 / 30)
    assert p.x < 30 * G.TILE, p.x


def test_match_on_stairs_runs():
    g = G.Game("stairs")
    for i in range(3):
        g.add_player(i, "P%d" % i)
    g.restart("stairs")
    assert g.map.id == "stairs"
    for _ in range(90):
        g.step(1 / 30)
    snap = g.step(1 / 30)
    assert len(snap["k"]) == len(M.pickups) and len(snap["p"]) == 3
    for p in g.players.values():
        assert free(int(p.cx // G.TILE), int(p.cy // G.TILE)), "player inside a wall"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
