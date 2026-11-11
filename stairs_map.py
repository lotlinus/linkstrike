"""Link Strike map: STAIRCASE (built from the hand-drawn staircase sketch).

Same grid rules as the other maps (see game.py): '#' wall, 'S' solid, 'C' crate, '=' one-way catwalk, '.' air.
Layout, top to bottom:
  top corridor (middle)  - roof + railed walkway, a door at each end where the upper stairs arrive
  upper rooms (left/right) - a room each side, reached by the upper stairs or through the gap above a lower stair
  mezzanines            - left floor and right floor at row 15, hanging walls leave a 3-tile crawl gap above the ground
  ground hall           - the big open hall in the middle, a lower staircase on each side
  basement              - corridor under the hall, a stepped mound in the middle, ladder holes at both ends,
                          a secret room on the right (reached only from the right ladder) and a closet behind it
Stairs are one-tile steps; on this map walking into a one-tile step climbs it (see `autostep` in game.py).
"""
COLS, ROWS, T = 80, 44, 40

GROUND = 28            # top row of the ground slab (players walk on row 27)
MEZZ = 15              # top row of the mezzanine floors / stubs
BRIDGE = 8             # top row of the corridor floor (= hall ceiling)
BASE_FLOOR = 40        # top row of the main basement floor
SHELF_FLOOR = 36       # top row of the left basement shelf


def build():
    g = [["."] * COLS for _ in range(ROWS)]

    def fill(c0, r0, c1, r1, ch):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                g[r][c] = ch

    # ---- shell: roofs, side walls, everything below the ground is solid until carved
    fill(0, 0, COLS - 1, 2, "#")
    fill(0, 3, 28, 3, "S")                          # the left roof sits one row lower than the middle/right
    fill(0, 0, 0, ROWS - 1, "#")
    fill(COLS - 1, 0, COLS - 1, ROWS - 1, "#")
    fill(1, GROUND, COLS - 2, ROWS - 1, "S")

    # ---- basement (carved out of the block)
    fill(17, 28, 18, 35, ".")                       # left ladder shaft + shelf, open to the hall above
    fill(19, 30, 28, 35, ".")                       # left shelf (6 tiles tall)
    fill(29, 30, 73, 39, ".")                       # main basement (10 tiles tall)
    fill(72, 28, 73, 29, ".")                       # right ladder hole, up into the secret room
    fill(75, 30, 78, 39, ".")                       # closet behind the right ladder
    fill(74, 37, 74, 39, ".")                       # closet door
    # stepped mound in the middle of the basement
    for i, c in enumerate(range(44, 50)):
        fill(c, 39 - i, c, 39, "S")                 # up: rows 39..34
        fill(63 - i, 39 - i, 63 - i, 39, "S")       # down (mirror): cols 63..58
    fill(50, 33, 57, 39, "S")                       # plateau, top row 33

    # ---- central tower: roof, hanging walls with a crawl gap, corridor floor, doors at both ends
    fill(29, 3, 29, 24, "#"); fill(55, 3, 55, 24, "#")
    fill(29, 5, 29, 7, "."); fill(55, 5, 55, 7, ".")        # doors into the corridor
    fill(30, BRIDGE, 54, BRIDGE + 1, "S")                   # corridor floor / hall ceiling

    # ---- mezzanines (row 15)
    fill(1, MEZZ, 9, MEZZ, "S")                             # left stub; cols 10-12 stay open = the gap above the stair
    fill(13, MEZZ, 28, MEZZ, "S")                           # left mezzanine floor
    fill(14, MEZZ, 14, 24, "#")                             # thin hanging wall; rows 25-27 stay open to crawl under
    fill(56, MEZZ, 66, MEZZ, "S")                           # right mezzanine floor
    fill(70, MEZZ, 78, MEZZ, "S")                           # right stub; cols 67-69 stay open

    # ---- lower stairs (hollow: one tile per step, the space under them stays open)
    for c in range(3, 14):                                  # left: col 3 (row 25) up to col 13 (row 15)
        g[28 - c][c] = "S"
    for c in range(58, 71):                                 # right: col 58 (row 27) up to col 70 (row 15)
        g[27 - (c - 58)][c] = "S"

    # ---- upper stairs (filled, they stand on the mezzanine floors)
    for c in range(20, 29):                                 # left: rises to the corridor door, landing cols 26-28
        top = max(BRIDGE, 14 - (c - 20))
        fill(c, top, c, MEZZ - 1, "S")
    for c in range(56, 65):                                 # right: landing cols 56-58, then down to the floor
        top = min(14, BRIDGE + max(0, c - 58))
        fill(c, top, c, MEZZ - 1, "S")

    # ---- cover and catwalks
    fill(3, 10, 8, 10, "="); fill(71, 10, 76, 10, "=")      # upper rooms
    fill(18, 22, 22, 22, "=")                               # under the left mezzanine
    fill(24, 26, 25, 27, "C")
    fill(33, 21, 38, 21, "="); fill(46, 21, 51, 21, "=")    # hall catwalks
    fill(40, 15, 44, 15, "=")
    fill(36, 26, 37, 27, "C"); fill(47, 26, 48, 27, "C")    # hall cover
    fill(24, 34, 25, 35, "C")                               # shelf cover
    fill(33, 38, 34, 39, "C"); fill(67, 38, 68, 39, "C")    # basement cover
    fill(35, 34, 41, 34, "="); fill(66, 34, 71, 34, "=")    # basement catwalks
    return ["".join(r) for r in g]


GRID = build()

# (kind, col, row)  kind: "health" or weapon id. row = the tile row the pickup stands on (surface is row+1)
PICKUPS = [
    ("health", 5, 14), ("health", 75, 14), ("health", 50, 7), ("health", 42, 27), ("health", 23, 35), ("health", 74, 27),
    (1, 16, 14), (1, 66, 14), (1, 16, 27), (1, 31, 39), (1, 77, 39),                  # shotguns
    (2, 42, 7), (2, 54, 32), (2, 76, 27),                                              # rockets: corridor, mound top, secret room
]
SPAWNS = [(4, 14), (74, 14), (36, 7), (48, 7), (16, 27), (65, 39)]
BACKUP_SPAWNS = [(42, 27), (21, 35), (16, 14)]

SKY = ["#1b2132", "#2a3248", "#3d4560"]
# decoration drawn in code: ladders (col, top row, bottom row, width in cols) and the corridor railing (col0, col1, floor row)
LADDERS = [[17, 28, 36, 2], [72, 28, 40, 2]]
RAILS = [[31, 53, BRIDGE]]
