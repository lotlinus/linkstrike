"""Street map checks (plain asserts, no extra packages):  python tests/test_street.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import game as G
import street_map as SM

M = G.MAPS["street"]
STAND = G.SOLIDS + G.ONE_WAY            # tiles a player can stand on


def free(c, r):
    return not G.solid(c, r, M.grid)


def test_shape():
    assert (SM.COLS, SM.ROWS, SM.T) == (G.COLS, G.ROWS, G.TILE)
    assert len(M.grid) == G.ROWS and all(len(r) == G.COLS for r in M.grid)
    assert set("".join(M.grid)) <= set("#SBC=-.")


def test_spawns_and_pickups_stand_on_something():
    assert len(M.spawns) == 6 and len(M.backups) == 3
    for col, row in M.spawns + M.backups:
        assert M.grid[row + 1][col] in STAND, ("no floor under spawn", col, row)
        assert free(col, row) and free(col, row - 1), ("no headroom at spawn", col, row)
        assert free(col + 1 if col + 1 < G.COLS else col, row), ("spawn jammed against a wall", col, row)
    for kind, col, row in M.pickups:
        assert M.grid[row + 1][col] in STAND, ("pickup floats", kind, col, row)
        assert free(col, row), ("pickup inside a block", kind, col, row)
    kinds = [k for k, _, _ in M.pickups]
    assert kinds.count("health") >= 5 and kinds.count(1) >= 4 and kinds.count(2) >= 2


def test_props_have_art():
    root = os.path.join(os.path.dirname(__file__), "..", "static", "img", "street")
    for name, col, row, sc, anchor in M.props:
        assert os.path.isfile(os.path.join(root, name + ".png")), name
        assert sc > 0 and anchor in ("b", "t")


def test_manhole_leads_down():
    # a player dropped over a manhole must end up on the sewer floor, not stuck on the street
    for col in (25, 53):
        g = G.Game("street")
        p = g.add_player(0, "A")
        p.x, p.y = col * G.TILE + 6, 30 * G.TILE - G.PH
        p.vx = p.vy = 0
        for _ in range(240):
            g.step(1 / 30)
        assert p.y > 41 * G.TILE - G.PH - 2 and p.ground, (col, p.y)


def test_walk_on_van_roof():
    g = G.Game("street")
    p = g.add_player(0, "A")
    p.x, p.y = 9 * G.TILE + 6, 26 * G.TILE
    p.vx = p.vy = 0
    for _ in range(120):
        g.step(1 / 30)
    assert p.ground and abs(p.y - (29 * G.TILE - G.PH)) < 1, p.y     # standing on the van roof (row 29)


def test_match_on_street_runs():
    g = G.Game("street")
    for i in range(3):
        g.add_player(i, "P%d" % i)
    g.restart("solo", "street")
    assert g.map.id == "street"
    for _ in range(90):
        g.step(1 / 30)
    snap = g.step(1 / 30)
    assert len(snap["k"]) == len(M.pickups) and len(snap["p"]) == 3
    for p in g.players.values():
        assert free(int(p.cx // G.TILE), int(p.cy // G.TILE)), "player inside a wall"


def test_payload_and_lab_unchanged():
    w = G.world_payload("street")
    assert w["art"] == "street" and w["map"] == "street" and w["street_row"] == SM.GT and w["beams"]
    lab = G.world_payload("lab")
    assert lab["art"] == "lab" and lab["grid"] is G.GRID and "sky" not in lab
    assert G.world_payload("nonsense")["map"] == "lab"          # unknown map ids fall back to the Laboratory


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(name, "ok")
    print("ALL PASSED")
