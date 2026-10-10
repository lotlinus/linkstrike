"""Link Strike game rules: map, jetpack physics, weapons, pickups, scoring.

No Flask/SocketIO in here, so it can be tested on its own (see tests/test_game.py).
The server calls Game.step(dt) 30 times a second and broadcasts the snapshot it returns.
"""
import math
import random

# ------------------------------------------------------------------ constants
TILE = 40
COLS, ROWS = 80, 44
W, H = COLS * TILE, ROWS * TILE
PW, PH = 28, 54                 # player hitbox
TARGET_KILLS = 10

# ---- Team Multiplayer (host picks "solo" or "team" in the lobby)
TEAM_MATCH_S = 360              # match length in seconds (6 min)
TEAM_MIN_PLAYERS = 2
SURVIVOR_PCT = 60               # starting share of Survivors; Hunters get the rest (playtest and tune)
SURVIVORS, HUNTERS = 1, 2       # explicit team ids (0 = no team, used in solo mode)
MAX_PLAYERS = 6                 # Solo Battle room size (6 skins / colours)
TEAM_MAX_PLAYERS = 12           # Team Multiplayer room size (one tinted skin per team, so no 6-skin limit)
SLOTS = max(MAX_PLAYERS, TEAM_MAX_PLAYERS)

SPEED = 390                     # px/s sideways
ACC_GROUND, ACC_AIR = 2800, 1700
FRIC_GROUND, FRIC_AIR = 3200, 450
GRAVITY = 1200                  # px/s^2
THRUST = 4300                   # jetpack push; net upward accel = THRUST - GRAVITY
MAX_UP, MAX_FALL = 400, 820

MAX_HP = 100
RESPAWN_S = 3.0
INVULN_S = 1.5
SHOULDER_DY = 31                # muzzle origin: this far below the top of the hitbox
MUZZLE_LEN = 26

ROCKET_RADIUS = 130
ROCKET_DMG = 85
ROCKET_SELF = 0.6
ROCKET_KNOCK = 760

WEAPONS = {
    0: {"name": "Pistol",  "dmg": 18, "cd": 0.26, "speed": 1500, "ammo": -1, "pellets": 1, "spread": 0.02, "life": 0.9,  "type": 0},
    1: {"name": "Shotgun", "dmg": 11, "cd": 0.80, "speed": 1300, "ammo": 8,  "pellets": 7, "spread": 0.20, "life": 0.32, "type": 1},
    2: {"name": "Rocket",  "dmg": 0,  "cd": 1.10, "speed": 760,  "ammo": 4,  "pellets": 1, "spread": 0.0,  "life": 3.0,  "type": 2},
}

SOLIDS = "#SCB"  # steel, slab, crate, building body (street map: the sprite is drawn over it)
ONE_WAY = "=-"   # catwalk grate: land on top, fly up through ("-" = same, but a sprite is drawn instead of a grate)


# ------------------------------------------------------------------ the map: the Laboratory
# Side-view cross-section of the lab blueprint: a reactor chamber in the middle, a ring of
# routes around it (roof, left shaft, right shaft, service tunnel underneath).
#   gates   : left/right doorways into the chamber (3 tiles tall, floor level)
#   hatches : roof hatch and floor hatch above/below the chamber centre
#   centre  : catwalk with the two power weapons (rockets)
def build_map():
    g = [["."] * COLS for _ in range(ROWS)]

    def fill(c0, r0, c1, r1, ch):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                g[r][c] = ch

    def both(c0, r0, c1, r1, ch):            # a block and its mirror image
        fill(c0, r0, c1, r1, ch)
        fill(COLS - 1 - c1, r0, COLS - 1 - c0, r1, ch)

    # shell: invisible ceiling, side walls, ground slab (standing row on the ground = 40)
    fill(0, 0, COLS - 1, 0, "#")
    fill(0, 0, 0, ROWS - 1, "#")
    fill(COLS - 1, 0, COLS - 1, ROWS - 1, "#")
    fill(0, 41, COLS - 1, 43, "S")

    # reactor chamber (cols 25-54)
    fill(25, 9, 54, 10, "S"); fill(37, 9, 42, 10, ".")        # roof + roof hatch
    fill(25, 11, 26, 26, "#"); fill(53, 11, 54, 26, "#")      # walls; rows 27-29 stay open = gates
    fill(25, 30, 54, 31, "S"); fill(38, 30, 41, 31, ".")      # floor + floor hatch

    # inside the chamber
    fill(34, 23, 45, 23, "=")                                 # centre catwalk (power weapons)
    fill(34, 28, 35, 29, "C"); fill(44, 28, 45, 29, "C")      # cover under the catwalk
    fill(28, 17, 33, 17, "="); fill(46, 17, 51, 17, "=")      # side perches
    fill(33, 14, 36, 14, "="); fill(43, 14, 46, 14, "=")      # high perches beside the hatch

    # service tunnel under the chamber
    fill(32, 39, 33, 40, "C"); fill(46, 39, 47, 40, "C")
    fill(28, 36, 35, 36, "="); fill(44, 36, 51, 36, "=")

    # outer shafts (built once, mirrored)
    both(1, 9, 10, 10, "S")        # upper corner ledge (spawn)
    both(8, 7, 9, 8, "C")          # cover beside the upper spawn
    both(14, 12, 22, 12, "=")      # high route towards the roof
    both(4, 17, 14, 17, "=")       # upper catwalk
    both(14, 23, 23, 23, "=")      # mid catwalk
    both(2, 30, 10, 30, "=")       # low catwalk
    both(12, 30, 24, 31, "S")      # gate ledge (leads to the chamber gate)
    both(12, 39, 13, 40, "C")      # ground cover
    both(20, 37, 21, 40, "C")      # pillar

    return ["".join(row) for row in g]


GRID = build_map()

# (kind, col, row)  kind: "health" or weapon id. row = floor-standing tile row
PICKUPS = [
    ("health", 20, 22), ("health", 59, 22), ("health", 6, 29), ("health", 73, 29), ("health", 46, 8),
    (1, 28, 29), (1, 51, 29), (1, 16, 29), (1, 63, 29),      # shotguns: gates + gate ledges
    (2, 37, 22), (2, 42, 22),                                  # rockets: the two power spots, centre catwalk
]
PICKUP_RESPAWN = {"health": 25.0, 1: 20.0, 2: 30.0}

SPAWNS = [(3, 8), (76, 8), (3, 40), (76, 40), (32, 8), (40, 40)]       # 6 primary spawn points
BACKUP_SPAWNS = [(8, 16), (9, 29), (71, 16)]                           # used when the primaries are unsafe

# Decoration only (client draws it): [sprite, col, row, scale, anchor]. "b" = bottom edge sits on row*TILE, "t" = top edge hangs from it.
PROPS = [
    ["door_open", 26, 30, 0.85, "b"], ["door_open", 54, 30, 0.85, "b"],
    ["tank_green", 30, 30, 0.55, "b"], ["tank_blue", 49, 30, 0.6, "b"],
    ["term_rack", 32, 30, 0.5, "b"], ["term_desk", 47, 30, 0.5, "b"],
    ["light_cyan", 33, 11, 0.5, "t"], ["light_cyan", 46, 11, 0.5, "t"], ["light_amber", 40, 11, 0.5, "t"],
    ["pipe_long", 30, 13, 0.6, "b"], ["pipe_long", 49, 13, 0.6, "b"], ["light_red", 28, 11, 0.5, "t"], ["light_red", 51, 11, 0.5, "t"],
    ["pipe_long", 29, 33, 0.7, "t"], ["pipe_long", 40, 33, 0.7, "t"], ["pipe_long", 51, 33, 0.7, "t"],
    ["pipe_bundle", 36, 32, 0.45, "t"], ["pipe_bundle", 44, 32, 0.45, "t"], ["term_kiosk", 29, 41, 0.6, "b"], ["term_rack", 50, 41, 0.55, "b"],
    ["term_desk", 5, 9, 0.5, "b"], ["term_desk", 74, 9, 0.5, "b"], ["tank_small", 12, 17, 0.6, "b"], ["tank_small", 67, 17, 0.6, "b"],
    ["term_arcade", 8, 41, 0.6, "b"], ["term_arcade", 71, 41, 0.6, "b"], ["tank_blue", 17, 41, 0.7, "b"], ["tank_green", 62, 41, 0.7, "b"],
    ["term_a", 18, 23, 0.5, "b"], ["term_a", 61, 23, 0.5, "b"], ["light_cyan", 18, 1, 0.5, "t"], ["light_cyan", 61, 1, 0.5, "t"],
    ["light_amber", 40, 1, 0.5, "t"], ["light_red", 6, 1, 0.5, "t"], ["light_red", 73, 1, 0.5, "t"],
]


def clear_line(x0, y0, x1, y1, grid=None):
    """True if no solid tile blocks the straight line (used for spawn safety)."""
    n = int(math.hypot(x1 - x0, y1 - y0) // 20) + 1
    for i in range(1, n):
        t = i / n
        if solid_px(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, grid):
            return False
    return True


def solid(c, r, grid=None):
    if c < 0 or c >= COLS or r < 0 or r >= ROWS:
        return True
    return (grid or GRID)[r][c] in SOLIDS


def one_way(c, r, grid=None):
    return 0 <= c < COLS and 0 <= r < ROWS and (grid or GRID)[r][c] in ONE_WAY


def solid_px(x, y, grid=None):
    return solid(int(x // TILE), int(y // TILE), grid)


def spawn_xy(col, row):
    return col * TILE + TILE / 2 - PW / 2, (row + 1) * TILE - PH - 0.01


class MapDef:
    """One playable map: grid, pickups, spawns, decoration, and the art/theme the client uses."""

    def __init__(self, id, name, grid, pickups, spawns, backups, props, art, extra=None):
        self.id, self.name, self.grid = id, name, grid
        self.pickups, self.spawns, self.backups = pickups, spawns, backups
        self.props, self.art, self.extra = props, art, extra or {}


import street_map as _SM  # noqa: E402  (same TILE/COLS/ROWS as above)

MAPS = {
    "lab": MapDef("lab", "Laboratory", GRID, PICKUPS, SPAWNS, BACKUP_SPAWNS, PROPS, "lab"),
    "street": MapDef("street", "Street", _SM.GRID, _SM.PICKUPS, _SM.SPAWNS, _SM.BACKUP_SPAWNS, _SM.PROPS, "street", {
        "sky": _SM.SKY, "skyline": _SM.SKYLINE, "skyline_base": _SM.SKYLINE_BASE, "street_row": _SM.GT,
        "beams": [[24 * TILE, 28 * TILE, _SM.GT * TILE, _SM.SEWER_FLOOR * TILE], [52 * TILE, 56 * TILE, _SM.GT * TILE, _SM.SEWER_FLOOR * TILE]],
    }),
}
DEFAULT_MAP = "lab"


def world_payload(map_id=DEFAULT_MAP):
    m = MAPS.get(map_id) or MAPS[DEFAULT_MAP]
    out = {
        "tile": TILE, "cols": COLS, "rows": ROWS, "grid": m.grid,
        "pw": PW, "ph": PH, "target": TARGET_KILLS,
        "map": m.id, "art": m.art,
        "pickups": [[k, c * TILE + TILE / 2, (r + 1) * TILE - 18] for k, c, r in m.pickups],
        "props": m.props,
        "weapons": {str(k): {"name": v["name"], "ammo": v["ammo"]} for k, v in WEAPONS.items()},
    }
    out.update(m.extra)
    return out


# ------------------------------------------------------------------ entities
class Player:
    def __init__(self, pid, name):
        self.id = pid
        self.name = name
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.mx = self.my = 0.0
        self.aim = 0.0
        self.fire = False
        self.ground = False
        self.thrust = False
        self.hp = MAX_HP
        self.dead = False
        self.dead_t = 0.0
        self.invuln = 0.0
        self.wpn = 0
        self.ammo = -1
        self.cd = 0.0
        self.fire_t = 0.0
        self.kills = 0
        self.deaths = 0
        self.team = 0

    @property
    def cx(self):
        return self.x + PW / 2

    @property
    def cy(self):
        return self.y + PH / 2


class Projectile:
    __slots__ = ("x", "y", "vx", "vy", "owner", "wpn", "type", "dmg", "life", "age", "ang")

    def __init__(self, x, y, ang, speed, owner, wpn, ptype, dmg, life):
        self.x, self.y, self.ang = x, y, ang
        self.vx, self.vy = math.cos(ang) * speed, math.sin(ang) * speed
        self.owner, self.wpn, self.type, self.dmg, self.life = owner, wpn, ptype, dmg, life
        self.age = 0.0


# ------------------------------------------------------------------ the game
class Game:
    def __init__(self, map_id=DEFAULT_MAP):
        self.players = {}
        self.projs = []
        self.events = []
        self.phase = "play"     # "play" or "over"
        self.winner = -1
        self.set_map(map_id)
        self.clock = 0.0
        self.spawn_used = {}    # spawn point -> time it was last used
        self.mode = "solo"      # "solo" (free for all) or "team"
        self.time_left = 0.0    # team mode: seconds left
        self.winner_team = -1   # team mode result: SURVIVORS, HUNTERS, or 0 for a draw (-1 while playing)
        self.final_counts = None

    def set_map(self, map_id):
        self.map = MAPS.get(map_id) or MAPS[DEFAULT_MAP]
        self.grid = self.map.grid
        self.pk_up = [True] * len(self.map.pickups)
        self.pk_t = [0.0] * len(self.map.pickups)

    # ---- membership / input
    def add_player(self, pid, name):
        p = Player(pid, name)
        self.players[pid] = p
        self._respawn(p, first=True)
        return p

    def remove_player(self, pid):
        self.players.pop(pid, None)
        self._check_one_team()      # a team that empties out (disconnects) loses at once

    def set_input(self, pid, mx, my, aim, fire):
        p = self.players.get(pid)
        if not p:
            return
        p.mx = max(-1.0, min(1.0, float(mx)))
        p.my = max(-1.0, min(1.0, float(my)))
        a = float(aim)
        p.aim = a if math.isfinite(a) else 0.0
        p.fire = bool(fire)

    # ---- match flow
    @staticmethod
    def survivor_count(n):
        """Starting Survivors for n players: SURVIVOR_PCT rounded half up, at least one of each team."""
        return max(1, min(n - 1, (n * SURVIVOR_PCT + 50) // 100))

    def team_counts(self):
        s_ = sum(1 for p in self.players.values() if p.team == SURVIVORS)
        h_ = sum(1 for p in self.players.values() if p.team == HUNTERS)
        return s_, h_

    def _assign_teams(self):
        ps = list(self.players.values())
        random.shuffle(ps)
        n_surv = self.survivor_count(len(ps))
        for i, p in enumerate(ps):
            p.team = SURVIVORS if i < n_surv else HUNTERS

    def _finish_team(self):
        """End the team match once: freeze the counts and decide the winner by final population."""
        if self.phase != "play":
            return
        s_, h_ = self.team_counts()
        self.final_counts = (s_, h_)
        self.winner_team = SURVIVORS if s_ > h_ else HUNTERS if h_ > s_ else 0
        self.phase = "over"

    def _check_one_team(self):
        if self.mode == "team" and self.phase == "play" and self.players:
            s_, h_ = self.team_counts()
            if s_ == 0 or h_ == 0:
                self._finish_team()

    def restart(self, mode=None, map_id=None):
        if mode in ("solo", "team"):
            self.mode = mode
        if map_id in MAPS:
            self.set_map(map_id)
        self.phase, self.winner = "play", -1
        self.winner_team, self.final_counts = -1, None
        self.time_left = float(TEAM_MATCH_S)
        if self.mode == "team":
            self._assign_teams()
        else:
            for p in self.players.values():
                p.team = 0
        self.projs.clear()
        self.pk_up = [True] * len(self.map.pickups)
        self.pk_t = [0.0] * len(self.map.pickups)
        spawns = self.map.spawns[:]
        random.shuffle(spawns)
        if len(self.players) > len(spawns):             # big team rooms: use the backup points too
            extra = self.map.backups[:]
            random.shuffle(extra)
            spawns += extra
        for i, p in enumerate(self.players.values()):
            p.kills = 0
            p.deaths = 0
            self._respawn(p, first=True, spot=spawns[i % len(spawns)])

    def _pick_spawn(self, p):
        """Safest spawn: far from enemies, out of their sight, not just used. Backups only win if primaries are unsafe."""
        others = [q for q in self.players.values() if q is not p and not q.dead]
        best, best_s = self.map.spawns[0], -1e18
        for backup, pool in ((False, self.map.spawns), (True, self.map.backups)):
            for col, row in pool:
                x, y = spawn_xy(col, row)
                cx, cy = x + PW / 2, y + PH / 2
                s = min(1500.0, min((math.hypot(cx - q.cx, cy - q.cy) for q in others), default=1500.0))
                for q in others:                                    # an enemy that can see this spot
                    if math.hypot(cx - q.cx, cy - q.cy) < 1100 and clear_line(cx, cy, q.cx, q.cy, self.grid):
                        s -= 700
                if self.clock - self.spawn_used.get((col, row), -99.0) < 6.0:   # used a moment ago
                    s -= 800
                if backup:
                    s -= 250
                s += random.random() * 80
                if s > best_s:
                    best, best_s = (col, row), s
        return best

    def _respawn(self, p, first=False, spot=None):
        if spot is None:
            spot = self._pick_spawn(p)
        self.spawn_used[spot] = self.clock
        p.x, p.y = spawn_xy(*spot)
        p.vx = p.vy = 0.0
        p.hp, p.dead, p.dead_t = MAX_HP, False, 0.0
        p.wpn, p.ammo, p.cd = 0, -1, 0.0
        p.invuln = 0.0 if first else INVULN_S
        p.ground = False

    # ---- simulation
    def step(self, dt):
        self.clock += dt
        if self.mode == "team" and self.phase == "play":
            self.time_left = max(0.0, self.time_left - dt)
            if self.time_left <= 0:
                self._finish_team()
        for p in self.players.values():
            self._update_player(p, dt)
        self._update_pickups(dt)
        self._update_projectiles(dt)
        return self._snapshot()

    def _update_player(self, p, dt):
        p.cd = max(0.0, p.cd - dt)
        p.fire_t = max(0.0, p.fire_t - dt)
        p.invuln = max(0.0, p.invuln - dt)
        if p.dead:
            p.dead_t -= dt
            if p.dead_t <= 0 and self.phase == "play":
                self._respawn(p)
        self._physics(p, dt)
        if not p.dead and self.phase == "play" and p.fire and p.cd <= 0:
            self._shoot(p)

    def _physics(self, p, dt):
        alive = not p.dead
        mx = p.mx if alive else 0.0
        my = p.my if alive else 0.0
        p.thrust = alive and my < -0.35

        if abs(mx) > 0.12:
            acc = ACC_GROUND if p.ground else ACC_AIR
            step = acc * dt
            p.vx += max(-step, min(step, mx * SPEED - p.vx))
        else:
            s = (FRIC_GROUND if p.ground else FRIC_AIR) * dt
            p.vx = 0.0 if abs(p.vx) <= s else p.vx - math.copysign(s, p.vx)

        p.vy += (GRAVITY - THRUST if p.thrust else GRAVITY) * dt
        if alive and my > 0.6 and not p.ground:
            p.vy += 800 * dt
        p.vy = max(-MAX_UP, min(MAX_FALL, p.vy))

        prev_bottom = p.y + PH
        p.ground = False
        self._move_x(p, p.vx * dt)
        self._move_y(p, p.vy * dt, prev_bottom)

    def _move_x(self, p, dx):
        p.x += dx
        top, bot = int(p.y // TILE), int((p.y + PH - 0.01) // TILE)
        if dx > 0:
            c = int((p.x + PW - 0.01) // TILE)
            for r in range(top, bot + 1):
                if solid(c, r, self.grid):
                    p.x, p.vx = c * TILE - PW, 0.0
                    break
        elif dx < 0:
            c = int(p.x // TILE)
            for r in range(top, bot + 1):
                if solid(c, r, self.grid):
                    p.x, p.vx = (c + 1) * TILE, 0.0
                    break

    def _move_y(self, p, dy, prev_bottom):
        p.y += dy
        c0, c1 = int(p.x // TILE), int((p.x + PW - 0.01) // TILE)
        if dy >= 0:
            r = int((p.y + PH - 0.01) // TILE)
            for c in range(c0, c1 + 1):
                if solid(c, r, self.grid) or (one_way(c, r, self.grid) and prev_bottom <= r * TILE + 1):
                    p.y, p.vy, p.ground = r * TILE - PH, 0.0, True
                    break
        else:
            r = int(p.y // TILE)
            for c in range(c0, c1 + 1):
                if solid(c, r, self.grid):
                    p.y, p.vy = (r + 1) * TILE, 0.0
                    break

    # ---- weapons
    def _shoot(self, p):
        w = WEAPONS[p.wpn]
        ox, oy = p.cx, p.y + SHOULDER_DY
        mx, my = ox + math.cos(p.aim) * MUZZLE_LEN, oy + math.sin(p.aim) * MUZZLE_LEN
        if solid_px(mx, my, self.grid):
            mx, my = ox, oy
        for _ in range(w["pellets"]):
            ang = p.aim + random.uniform(-w["spread"], w["spread"])
            spd = w["speed"] * (random.uniform(0.92, 1.08) if w["pellets"] > 1 else 1.0)
            self.projs.append(Projectile(mx, my, ang, spd, p.id, p.wpn, w["type"], w["dmg"], w["life"]))
        self.events.append(["sh", p.id, round(mx), round(my), round(p.aim, 2), p.wpn])
        p.cd = w["cd"]
        p.fire_t = 0.15
        if p.ammo > 0:
            p.ammo -= 1
            if p.ammo == 0:
                p.wpn, p.ammo = 0, -1

    def _update_projectiles(self, dt):
        keep = []
        for pr in self.projs:
            pr.life -= dt
            pr.age += dt
            if pr.life <= 0:
                if pr.type == 2:
                    self._explode(pr.x, pr.y, pr.owner)
                continue
            dist = math.hypot(pr.vx, pr.vy) * dt
            steps = max(1, int(dist // 10) + 1)
            sx, sy = pr.vx * dt / steps, pr.vy * dt / steps
            hit = None
            for _ in range(steps):
                pr.x += sx
                pr.y += sy
                if solid_px(pr.x, pr.y, self.grid):
                    hit = "wall"
                    break
                for q in self.players.values():
                    if q.dead or (q.id == pr.owner and pr.age < 0.15):
                        continue
                    if q.x <= pr.x <= q.x + PW and q.y <= pr.y <= q.y + PH:
                        hit = q
                        break
                if hit:
                    break
            if hit is None:
                keep.append(pr)
                continue
            if pr.type == 2:
                self._explode(pr.x, pr.y, pr.owner)
            elif hit == "wall":
                self.events.append(["hit", round(pr.x), round(pr.y), round(pr.ang, 2)])
            else:
                self._damage(hit, pr.dmg, pr.owner, pr.wpn)
                self.events.append(["bl", round(pr.x), round(pr.y)])
        self.projs = keep

    def _explode(self, x, y, owner):
        self.events.append(["ex", round(x), round(y), ROCKET_RADIUS])
        for q in self.players.values():
            if q.dead:
                continue
            nx, ny = max(q.x, min(x, q.x + PW)), max(q.y, min(y, q.y + PH))
            d = math.hypot(nx - x, ny - y)
            if d >= ROCKET_RADIUS:
                continue
            f = 1.0 - d / ROCKET_RADIUS
            dmg = max(8.0, ROCKET_DMG * f)
            if q.id == owner:
                dmg *= ROCKET_SELF
            self._damage(q, dmg, owner, 2)
            dx, dy = q.cx - x, q.cy - y
            n = math.hypot(dx, dy) or 1.0
            q.vx += dx / n * ROCKET_KNOCK * f
            q.vy += dy / n * ROCKET_KNOCK * f - 140 * f

    def _damage(self, victim, amount, attacker_id, wpn):
        if victim.dead or victim.invuln > 0 or self.phase != "play":
            return
        killer = self.players.get(attacker_id)
        team_mode = self.mode == "team"
        if team_mode and killer and killer is not victim and killer.team == victim.team:
            return                              # no friendly fire in team matches
        victim.hp -= amount
        if victim.hp > 0:
            return
        victim.hp = 0
        victim.dead, victim.dead_t = True, RESPAWN_S
        victim.fire = False
        victim.deaths += 1
        if killer and killer is not victim:
            killer.kills += 1
            if team_mode:
                victim.team = killer.team       # converted: respawns on the killer's team
        self.events.append(["k", attacker_id, victim.id, wpn])
        if team_mode:
            self._check_one_team()              # everyone converted -> instant win
        elif killer and killer is not victim and killer.kills >= TARGET_KILLS:
            self.phase, self.winner = "over", killer.id

    def _update_pickups(self, dt):
        for i, (kind, c, r) in enumerate(self.map.pickups):
            if not self.pk_up[i]:
                self.pk_t[i] -= dt
                if self.pk_t[i] <= 0:
                    self.pk_up[i] = True
                continue
            px, py = c * TILE + TILE / 2, (r + 1) * TILE - 18
            for p in self.players.values():
                if p.dead or abs(p.cx - px) > PW / 2 + 20 or abs(p.cy - py) > PH / 2 + 20:
                    continue
                if kind == "health":
                    if p.hp >= MAX_HP:
                        continue
                    p.hp = min(MAX_HP, p.hp + 40)
                else:
                    p.wpn, p.ammo = kind, WEAPONS[kind]["ammo"]
                self.pk_up[i] = False
                self.pk_t[i] = PICKUP_RESPAWN[kind]
                self.events.append(["pu", i, p.id])
                break

    # ---- output
    def _counts_for_snapshot(self):
        return self.final_counts if self.final_counts else self.team_counts()

    def _snapshot(self):
        players = []
        for p in self.players.values():
            flags = (1 if p.ground else 0) | (2 if p.thrust else 0) | (4 if p.dead else 0) \
                | (8 if p.fire_t > 0 else 0) | (16 if p.invuln > 0 else 0)
            players.append([p.id, round(p.x, 1), round(p.y, 1), round(p.vx), round(p.vy), round(p.aim, 2),
                            int(math.ceil(p.hp)), p.wpn, flags, p.kills, p.ammo, round(max(0.0, p.dead_t), 1), p.team, p.deaths])
        snap = {
            "p": players,
            "b": [[pr.type, round(pr.x), round(pr.y), round(pr.ang, 2)] for pr in self.projs],
            "k": [1 if u else 0 for u in self.pk_up],
            "e": self.events,
            "m": [self.phase, self.winner, self.mode, int(math.ceil(self.time_left)), *self._counts_for_snapshot(), self.winner_team],
        }
        self.events = []
        return snap
