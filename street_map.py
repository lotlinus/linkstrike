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
    "ac_unit": (44, 43), "atm": (37, 89), "barrel_blue": (42, 63), "bin": (53, 57), "bld1": (163, 331),
    "bld2": (152, 312), "bld3": (170, 279), "bld4": (144, 297), "bld5": (181, 237), "block_stack": (73, 66),
    "bus_stop_sign": (41, 136), "cone": (24, 32), "crate_wood": (57, 55), "grate": (97, 57), "keke": (65, 54),
    "kiosk_green": (104, 96), "kiosk_yellow": (78, 83), "lamps_a": (15, 123), "lamps_c": (18, 129), "moto": (87, 48),
    "pipe_big": (115, 64), "pipe_end": (62, 68), "planter": (94, 51), "pos_booth": (62, 90), "sewer_drop": (66, 122),
    "sewer_outlet": (121, 84), "sign_lagos": (66, 43), "sign_oneway": (79, 44), "slab_a": (166, 38),
    "steel_bench": (104, 27), "suv": (144, 76), "tires": (46, 51), "van": (140, 68), "wall_right": (267, 87),
}

# building: (sprite, left col, rows of body above the street, roof row inside the sprite, body x range inside the sprite)
BUILDINGS = [
    ("bld1", 1, 10, 57, 7, 157),
    ("bld3", 15, 9, 29, 13, 155),
    ("bld5", 36, 6, 75, 5, 153),
    ("bld4", 59, 10, 37, 9, 129),
    ("bld2", 72, 11, 35, 8, 146),
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
    put("sewer_outlet", 5 * T, 1590, 90)
    put("sewer_outlet", 74 * T, 1590, 90)
    put("sewer_drop", 11 * T, 1440, 110)
    put("sewer_drop", 68 * T, 1440, 110)
    put("pipe_big", 24 * T, floor, 50)
    put("pipe_big", 55 * T, floor, 50)
    put("grate", 40 * T, 1560, 60)
    put("barrel_blue", 20 * T, floor, 56)
    put("crate_wood", 60 * T, floor, 50)
    put("block_stack", 32 * T, floor, 60)
    put("block_stack", 47 * T, floor, 60)
    put("pipe_end", 13.5 * T, floor, 56)
    put("pipe_end", 65.5 * T, floor, 56)

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
    put("tires", 50.4 * T, ground, 44)
    put("cone", 6.9 * T, ground, 28)
    put("cone", 71.9 * T, ground, 28)
    fill(30, GT - 2, 35, GT - 1, "B")                  # cover walls with barbed-wire fence on top
    fill(44, GT - 2, 49, GT - 1, "B")
    put("wall_right", 33 * T, ground, 80)
    put("wall_right", 47 * T, ground, 80)
    put("sign_lagos", 33 * T, ground - 14, 40)
    put("sign_oneway", 47 * T, ground - 14, 38)

    # ---- rooftops (decoration only)
    put("ac_unit", 38 * T, 25 * T, 40)
    put("planter", 40.6 * T, 25 * T, 36)

    # ---- floating platforms: the sky game
    both(8, 25, 11, 25, "-")
    both(23, 22, 27, 22, "-")
    both(3, 17, 6, 17, "-")
    fill(37, 12, 42, 12, "-")                          # high centre: the rocket perch
    fill(33, 18, 35, 18, "-")
    fill(44, 18, 46, 18, "-")
    for c0, r0, c1 in [(8, 25, 11), (68, 25, 71), (23, 22, 27), (52, 22, 56), (3, 17, 6), (73, 17, 76)]:
        w = (c1 - c0 + 1) * T
        put("slab_a", (c0 + (c1 - c0 + 1) / 2) * T, r0 * T + 38 * w / 166, 38 * w / 166)
    put("slab_a", 40 * T, 12 * T + 38 * 240 / 166, 38 * 240 / 166)
    for c0 in (33, 44):
        put("steel_bench", (c0 + 1.5) * T, 18 * T + 27 * 120 / 104, 27 * 120 / 104)
    return ["".join(row) for row in g], props


GRID, PROPS = build()

# (kind, col, row)  kind: "health" or weapon id. row = the tile row the pickup stands on (surface is row+1)
PICKUPS = [
    ("health", 5, 20), ("health", 74, 19), ("health", 37, 24), ("health", 25, 41), ("health", 54, 41), ("health", 41, 34),
    (1, 9, 28), (1, 68, 28), (1, 20, 36), (1, 59, 36), (1, 5, 37), (1, 74, 37),      # shotguns
    (2, 39, 11), (2, 40, 11), (2, 38, 34),                                              # rockets: centre perch + the sewer ledge
]
SPAWNS = [(3, 20), (75, 19), (17, 21), (61, 20), (6, 41), (73, 41)]
BACKUP_SPAWNS = [(39, 24), (12, 30), (66, 30)]

SKY = ["#27304f", "#c0675a", "#f2b46b"]          # dusk over Lagos: top, middle, horizon
SKYLINE = ["#3a3552", "#2a2640"]
SKYLINE_BASE = [470, 800]
