"""Link Strike map: STREET (a Lagos street block with a sewer underneath).

Side-view cross-section, same grid rules as the Laboratory (see game.py):
  '#' boundary wall   'S' concrete slab   'B' building body (solid, the sprite is drawn over it)
  'C' crate           '=' one-way ledge   '-' one-way platform with a sprite on it   '.' open air
Layout, left to right: tall tan building, alley with a van, yellow building, kiosk alley with a manhole,
the shop building in the middle (low, so the centre sky stays open), mirrored on the right.
Under the street: a sewer with a manhole drop in each kiosk alley.
The client draws the sprites in static/img/street from the PROPS list below.
"""
COLS, ROWS = 80, 44
T = 40
GT = 31                       # first row of the street slab; players walk on row GT-1 = 30
SEWER_TOP, SEWER_FLOOR = 33, 42

# natural size (px) of the sprites used below: name -> (w, h)
SZ = {
    "ac_unit": (53, 78), "atm": (134, 113), "barrel_blue": (53, 78), "bin": (81, 87), "bld1": (242, 300),
    "bld2": (249, 301), "bld3": (242, 290), "bld4": (183, 289), "bld5": (180, 194), "block_stack": (113, 104),
    "bus_stop_sign": (53, 160), "cone": (32, 79), "crate_wood": (99, 88), "grate": (103, 59), "keke": (145, 101),
    "kiosk_green": (172, 135), "kiosk_yellow": (133, 126), "lamps_a": (84, 140), "lamps_c": (70, 165),
    "moto": (122, 71), "pipe_big": (182, 173), "pipe_end": (75, 95), "planter": (161, 155), "pos_booth": (93, 122),
    "sewer_drop": (83, 107), "sewer_outlet": (245, 105), "sign_lagos": (183, 137), "sign_oneway": (143, 73),
    "slab_a": (132, 32), "steel_bench": (92, 34), "suv": (241, 117), "tires": (52, 80), "van": (261, 113),
    "wall_right": (144, 98),
}

# building: (sprite, left col, rows of body above the street, roof row inside the sprite, body x range inside the sprite)
BUILDINGS = [
    ("bld1", 1, 8, 42, 6, 236),
    ("bld3", 14, 8, 12, 20, 225),
    ("bld5", 36, 6, 34, 12, 168),
    ("bld4", 59, 8, 35, 13, 170),
    ("bld2", 71, 7, 60, 10, 230),
]


def build():
    g = [["."] * COLS for _ in range(ROWS)]
    props = []

    def fill(c0, r0, c1, r1, ch):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                g[r][c] = ch

    def both(c0, r0, c1, r1, ch):            # a block and its mirror image
        fill(c0, r0, c1, r1, ch)
        fill(COLS - 1 - c1, r0, COLS - 1 - c0, r1, ch)

    def put(name, cx, bottom, h):
        """Decoration: sprite centred on pixel x `cx`, bottom edge on pixel y `bottom`, `h` px tall."""
        sc = h / SZ[name][1]
        props.append([name, round((cx - T / 2) / T, 3), round(bottom / T, 3), round(sc, 4), "b"])

    def stand(name, c0, ncols, rows, row):
        """A prop you can stand on: `rows` tiles tall, one-way platform on tile row `row` (its roof)."""
        fill(c0, row, c0 + ncols - 1, row, "-")
        put(name, (c0 + ncols / 2) * T, (row + rows) * T, rows * T)

    # ---- shell: invisible ceiling, side walls, street slab, sewer floor, manholes
    fill(0, 0, COLS - 1, 0, "#")
    fill(0, 0, 0, ROWS - 1, "#")
    fill(COLS - 1, 0, COLS - 1, ROWS - 1, "#")
    fill(1, GT, COLS - 2, GT + 1, "S")
    fill(1, SEWER_FLOOR, COLS - 2, ROWS - 1, "S")
    fill(24, GT, 27, GT + 1, ".")
    fill(52, GT, 55, GT + 1, ".")

    # ---- sewer (drawn first so street props sit above it in the list)
    both(15, SEWER_TOP, 16, 37, "S")                   # bulkheads hanging from the street slab
    both(3, 38, 8, 38, "=")
    both(9, 35, 13, 35, "=")
    both(18, 37, 22, 37, "=")
    both(28, 37, 32, 37, "=")
    fill(36, 35, 43, 35, "=")
    both(37, 40, 38, 41, "S")                          # cover blocks under the centre ledge
    floor = SEWER_FLOOR * T
    put("sewer_outlet", 5 * T, 1590, 62)
    put("sewer_outlet", 74 * T, 1590, 62)
    put("sewer_drop", 11 * T, 1440, 110)
    put("sewer_drop", 68 * T, 1440, 110)
    put("pipe_big", 24 * T, floor, 70)
    put("pipe_big", 55 * T, floor, 70)
    put("grate", 40 * T, 1560, 60)
    put("barrel_blue", 20 * T, floor, 56)
    put("crate_wood", 60 * T, floor, 50)
    put("block_stack", 32 * T, floor, 72)
    put("block_stack", 47 * T, floor, 72)
    put("pipe_end", 13.5 * T, floor, 84)
    put("pipe_end", 65.5 * T, floor, 84)

    # ---- buildings: solid body + sprite on top
    for name, left, n, roof, bx0, bx1 in BUILDINGS:
        s = n * T / (SZ[name][1] - roof)          # scale so the body is exactly n tiles tall
        x = left * T
        c0 = round((x + bx0 * s) / T)
        c1 = round((x + (bx1 + 1) * s) / T) - 1
        fill(c0, GT - n, c1, GT - 1, "B")
        props.append([name, round((x + SZ[name][0] * s / 2 - T / 2) / T, 3), GT, round(s, 4), "b"])

    # ---- street level
    ground = GT * T
    stand("van", 8, 4, 2, GT - 2)                      # yellow bus: stand on its roof
    stand("suv", 67, 4, 2, GT - 2)
    stand("kiosk_green", 21, 3, 3, GT - 3)             # kiosks flush against the manholes
    stand("kiosk_yellow", 56, 3, 3, GT - 3)
    put("keke", 13.6 * T, ground, 50)
    put("moto", 64.4 * T, ground, 40)
    put("lamps_a", 7.5 * T, ground, 170)
    put("lamps_c", 71.3 * T, ground, 170)
    put("bus_stop_sign", 43.5 * T, ground, 140)
    put("pos_booth", 29.3 * T, ground, 100)
    put("atm", 51.0 * T, ground, 80)
    put("bin", 14.3 * T, ground, 44)
    put("tires", 50.4 * T, ground, 50)
    put("cone", 6.9 * T, ground, 40)
    put("cone", 71.9 * T, ground, 40)
    fill(30, GT - 2, 35, GT - 1, "B")                  # cover walls with barbed-wire fence on top
    fill(44, GT - 2, 49, GT - 1, "B")
    for cx in (33, 47):                                # two fence panels side by side cover each 6-tile wall
        put("wall_right", (cx - 1.47) * T, ground, 80)
        put("wall_right", (cx + 1.47) * T, ground, 80)
    put("sign_lagos", 33 * T, ground - 80, 58)
    put("sign_oneway", 47 * T, ground - 80, 46)

    # ---- rooftops (decoration only)
    put("ac_unit", 38 * T, 25 * T, 44)
    put("planter", 40.6 * T, 25 * T, 84)

    # ---- floating platforms: the sky game
    both(8, 25, 11, 25, "-")
    both(23, 22, 27, 22, "-")
    both(3, 17, 6, 17, "-")
    fill(37, 12, 42, 12, "-")                          # high centre: the rocket perch
    fill(33, 18, 35, 18, "-")
    fill(44, 18, 46, 18, "-")
    for c0, r0, c1 in [(8, 25, 11), (68, 25, 71), (23, 22, 27), (52, 22, 56), (3, 17, 6), (73, 17, 76)]:
        w = (c1 - c0 + 1) * T
        hh = SZ["slab_a"][1] * w / SZ["slab_a"][0]
        put("slab_a", (c0 + (c1 - c0 + 1) / 2) * T, r0 * T + hh, hh)
    hh = SZ["slab_a"][1] * 240 / SZ["slab_a"][0]
    put("slab_a", 40 * T, 12 * T + hh, hh)
    for c0 in (33, 44):
        hh = SZ["steel_bench"][1] * 120 / SZ["steel_bench"][0]
        put("steel_bench", (c0 + 1.5) * T, 18 * T + hh, hh)
    return ["".join(row) for row in g], props


GRID, PROPS = build()

# (kind, col, row)  kind: "health" or weapon id. row = the tile row the pickup stands on (surface is row+1)
PICKUPS = [
    ("health", 5, 22), ("health", 74, 23), ("health", 37, 24), ("health", 25, 41), ("health", 54, 41), ("health", 41, 34),
    (1, 9, 28), (1, 68, 28), (1, 20, 36), (1, 59, 36), (1, 5, 37), (1, 74, 37),      # shotguns
    (2, 39, 11), (2, 40, 11), (2, 38, 34),                                              # rockets: centre perch + the sewer ledge
]
SPAWNS = [(3, 22), (75, 23), (17, 22), (61, 22), (6, 41), (73, 41)]
BACKUP_SPAWNS = [(39, 24), (12, 30), (66, 30)]

SKY = ["#27304f", "#c0675a", "#f2b46b"]          # dusk over Lagos: top, middle, horizon
SKYLINE = ["#3a3552", "#2a2640"]
SKYLINE_BASE = [470, 800]
