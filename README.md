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

## Deploy on Render
1. Push this folder to GitHub.
2. Render > New > Blueprint > pick the repo (reads render.yaml).
3. Open the https://link-strike-xxxx.onrender.com URL.
Free plan sleeps after ~15 min idle (first load ~30s). Keep ONE worker: rooms live in memory.
Set MIN_TO_START=2 in Render env vars once you're done solo testing.

## Files
- game.py      map, jetpack physics, weapons, pickups, scoring (server-side, tested)
- app.py       Flask-SocketIO rooms, lobby, game loop, /api/leaderboard
- rankings.py  leaderboard rules + Neon (Postgres) access with offline fallback
- static/      game.js (client), style.css, skins.js + img/ (soldier atlases built from your Craftpix packs)

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
