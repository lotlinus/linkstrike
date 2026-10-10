# Link Strike v0.7.2

Jetpack shooter in the browser. Make a room, send the link, fight (Solo Battle: 2-6 players, first to 10 kills; Team Multiplayer: 2-12 players).

## Controls
Phone (landscape): left thumb flies (push up = jetpack), right thumb aims and auto-fires.
Laptop: WASD / arrows to fly (W, Up or Space = jetpack), mouse to aim, hold click to shoot.
Pick up weapons and health around the base: shotgun, rocket launcher, health packs.

## Run locally
    python -m venv .venv && source .venv/bin/activate      (Windows: .venv\Scripts\activate)
    pip install -r requirements.txt
    python app.py
Open http://localhost:5000 in two tabs (or on a phone: http://<laptop-IP>:5000 on the same Wi-Fi).
Needs Python 3.11 or 3.12.

## Offline / LAN testing (one-time download)
The page needs the Socket.IO browser library. While online, save a copy once:
    curl -L -o static/socket.io.min.js https://cdn.jsdelivr.net/npm/socket.io-client@4.7.5/dist/socket.io.min.js
(Windows PowerShell: use curl.exe.) After that LAN play works without internet.

## Leaderboard (Neon)
Rankings are total kills, wins break ties. Only finished matches with 3+ players count. Players are an anonymous
device id kept in the browser; the username is just a label.
1. Create a Neon project, copy its connection string (postgresql://...?sslmode=require).
2. Set it as the DATABASE_URL env var (Render > Environment, or `export DATABASE_URL=...` locally).
The `players` table is created automatically. No DATABASE_URL (or Neon unreachable) = the game runs normally and the card says "No rankings yet".

## Tests (game rules, no extra packages)
    python tests/test_game.py
    python tests/test_street.py

## Deploy on Render
1. Push this folder to GitHub.
2. Render > New > Blueprint > pick the repo (reads render.yaml).
3. Open the https://link-strike-xxxx.onrender.com URL.
Free plan sleeps after ~15 min idle (first load ~30s). Keep ONE worker: rooms live in memory.
Set MIN_TO_START=2 in Render env vars once you're done solo testing.

## Files
- game.py      maps list, jetpack physics, weapons, pickups, scoring (server-side, tested)
- street_map.py  the Street map (see Maps above)
- app.py       Flask-SocketIO rooms, lobby, game loop, /api/leaderboard
- rankings.py  leaderboard rules + Neon (Postgres) access with offline fallback
- static/      game.js (client), style.css, skins.js + img/ (soldier atlases built from your Craftpix packs)

## Maps (host picks in the lobby)
- **Laboratory**: the original reactor-chamber map.
- **Street**: a Lagos street block. Five buildings (stand on the roofs), a yellow bus and an SUV you can stand on, kiosks next to the
  two manholes, floating slabs, and a sewer underneath. Drop down a manhole to reach it.
The map lives in `street_map.py` (grid, pickups, spawns, sprite placement). Sprites are in `static/img/street/`, cut from the
street sprite sheet. To add another map: build one like `street_map.py`, register it in `MAPS` at the bottom of `game.py`, and
add a button with `data-map="..."` in `templates/index.html`.
Grid letters: `#` wall, `S` slab, `B` building body (solid, sprite drawn over it), `C` crate, `=` one-way ledge with drawn art,
`-` one-way platform whose sprite is placed by the props list, `.` air.

## Game modes (host picks in the lobby)
- **Solo Battle**: every player for themselves, first to 10 kills (unchanged).
- **Team Multiplayer**: Survivors (blue) vs Hunters (red), 6 minute match, 2-12 players (`TEAM_MAX_PLAYERS` in `game.py`).
  Eliminate an opponent and they respawn on YOUR team. Most players at the timer wins
  (equal = draw); if one team ends up empty the match ends instantly. No friendly fire,
  no joining once a team match has started. Kills and deaths persist through every switch;
  team results never change a player's personal leaderboard stats (kills still count).
  Tuning knobs are at the top of `game.py`: `TEAM_MATCH_S`, `SURVIVOR_PCT`, `TEAM_MIN_PLAYERS`.
  Spawn protection reuses the existing `INVULN_S`.

## Custom room names
The host can type a room name (3-12 letters/numbers, e.g. `LOTSARENA`) when creating a room; leave it empty for a random code.
Friends join with the name or the link `/r/LOTSARENA`. The name belongs to the device that first used it and stays reserved
for 30 days after its last use: when the room empties, only the owner can open it again; others see "closed right now".
A device keeps one name at a time (choosing a new one releases the old one).

Names are stored in Postgres (`room_names` table, created automatically, same `DATABASE_URL` as the leaderboard) so they
survive restarts and a sleeping free server. Without `DATABASE_URL`, or if the database is unreachable, names fall back to
server memory and last until the next restart. Code: `roomnames.py`.

## Unique player names
- No two players in a room can share a name (capitals, spaces, look-alike and invisible characters are ignored, so `Bob`, `bob` and `B o b` are the same). The second one is told to pick another name.
- A blank name is filled in automatically: `Soldier`, `Soldier 2`, `Soldier 3`...
- One device = one player per room. If the same device joins a room it's already in (second tab, refresh, reconnect), it takes over its existing seat instead of creating a second player: same name, kills and team, and the old window is disconnected. This works even when the room is full or a team match is running.
- Limit: a device is identified by an id saved in the browser, so someone who clears their site data or uses a private window looks like a new device (they still can't reuse a taken name). Code: `unique_name`, `seat_of` and `take_over_seat` in `app.py`.
