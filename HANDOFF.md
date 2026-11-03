# Link Strike Android App: Handoff

Read this whole file before doing anything. Then do **only the chunk you were assigned** and nothing else.

## 1. Goal

Turn Link Strike (browser multiplayer shooter, Flask + Flask-SocketIO, server-authoritative `game.py`) into an Android app.

- Locked to **landscape**, fullscreen.
- **Solo vs bots** runs fully on the phone (no server needed).
- **Online play** connects to the **existing hosted Flask-SocketIO server** (confirmed by the owner). The server URL lives in **one config file** (`config.js`) so it can be changed in one place.
- Suggested wrapper: **Capacitor** (wraps the existing web code in an Android WebView project). If you pick something else, note why in the Log at the bottom.

## 2. Ground rules

- Work on your own branch: `chunk-a`, `chunk-b` or `chunk-c`.
- Only edit the files your chunk owns (section 5). If you must touch another chunk's file, make the smallest possible change and write it in the Log.
- Do not redesign anything listed in section 3. Those decisions are final.
- When done: commit, tick your boxes in section 6, and add notes to the Log for the next person.
- The code is not described here in detail. Read the repo first and verify file names and structure. Known files: `index.html`, `style.css`, `game.js`, `game.py`, `static/img/`.

## 3. Final design decisions

### In-match HUD
- **Remove:** room name, ping text, FULL button, and the separate SOUND, MIC OFF, VOICE and EXIT buttons.
- **Add:** one small **pause button**, plus a **network-bars indicator** (online only) that replaces the ping number.
- **Pause menu** contains: Resume, Sound, Exit. **Voice and Mic appear in online games only.**
- **Exit lives only in the pause menu**, not on the HUD (too easy to hit by accident on touch).
- Android **back button opens the pause menu**, it never quits the match.
- **Solo pause freezes the match** (the simulation runs on the phone). Online cannot pause.
- **Keep:** health bar, weapon and ammo panel, scoreboard, kill feed, and the two round buttons on the right (weapon swap and reload).
- The old room name overlapped the HP number. Make sure nothing overlaps after the change.
- Solo has **no voice or mic controls at all**.

### Home screen
- Three action buttons, **all equal in size**: **Play vs Bots**, **Create room**, **Join a room**.
- **Avatar:** fold the Avatar button into the name chip. Tapping the chip opens the avatar picker.
- **Keep:** version footer, Leaderboard (online only, greyed out with no connection).
- **Settings:** keep the Volume slider (0 = mute). Remove the Sound toggle and the ALCATRAZ alerts toggle.

### Solo setup screen (new)
- Solo skips the lobby entirely (no room code, player list, invite link or voice).
- Setup screen has: **map picker** (reuse the lobby's map cards), **bot count 1 to 5**, **difficulty Easy / Medium / Hard**, then **Start**.

### Online lobby
- Keep as is.
- Replace "Share invite link" with **Android's native share sheet** (so players can send it straight to WhatsApp).
- Make the Mic and Voice buttons small icons.

### Game-over screen
- Solo: "Leave room" becomes **"Back to menu"**.
- **Play again** shows for the player immediately, with no waiting on a host (solo).

### Remove entirely
- **Store** (it is a "Coming soon" placeholder).
- Rotate gate and the "Rotate your phone screen" overlay (app is landscape-locked).
- Service worker and manifest.
- Google Fonts `<link>` tags. **Bundle the three fonts locally** so text renders correctly offline.
- Duplicate images (for example `hero.png` and `hero.jpg`, and `a0` to `a5` as both `.png` and `.jpg`). Check which ones the code actually references, delete the unused ones, and list what you deleted in the Log.

## 4. Chunks

### Chunk A: Scaffold, clean-up, UI (do this first)
1. Create the Android project (Capacitor), landscape-locked, fullscreen. Put the server URL in `config.js`.
2. Do all the "Remove entirely" items in section 3. Bundle fonts and assets for offline use.
3. Build the new HUD, pause menu, home screen, solo setup screen and game-over changes.
4. For the solo setup screen, wire **Start** to a clearly named function (for example `startSoloMatch({ map, botCount, difficulty })`) that Chunk B will implement. A stub that logs the values is fine.
5. Make sure the app builds and launches before handing over.

### Chunk B: Solo port and bots (starts after Chunk A is merged, or on a stub)
1. Move the game simulation to run **on the device** for solo, so a match against bots needs no server.
2. Implement `startSoloMatch(...)` and **pause that freezes the match**.
3. Build the bots: movement, aiming, shooting. **Easy / Medium / Hard**, **1 to 5 bots**.
4. Reuse the existing game rules and weapon behavior. Check `game.py` for how the server does it so solo and online feel the same.
5. Solo game-over: "Back to menu" and immediate Play again.

### Chunk C: Online, testing, release
1. Point the app at the hosted server through `config.js`. Test create room, join room, leaderboard, voice and mic.
2. Add the native share sheet for invites.
3. Handle dropped connections, reconnecting, and the network-bars indicator (suggested: show a warning state when latency is above about 150 ms).
4. Check the Android back button behavior online (opens pause menu, does not quit).
5. Test on real devices: performance, touch controls, solo and online.
6. Release: app icon, splash screen, signed APK, and a test of the release build before distributing.

## 5. File ownership (to avoid merge conflicts)

| Area | Owner |
|---|---|
| `index.html`, `style.css` (HUD, menus, home, setup screen, game-over layout) | Chunk A |
| Android project files, `config.js`, fonts, asset clean-up | Chunk A |
| `game.js` (solo simulation, bots, pause freeze) | Chunk B (Chunk A touches only HUD and UI hooks) |
| New bot and solo files (for example `solo.js`, `bots.js`) | Chunk B |
| Socket and online code, share sheet, reconnect handling | Chunk C |
| Icons, splash screen, signing, release build | Chunk C |

`game.js` is the most likely conflict point. Chunk A should keep its edits there to the HUD and button hooks. Chunk B owns the game loop.

## 6. Progress checklist

**Chunk A**
- [ ] Android project created, landscape-locked, fullscreen
- [ ] `config.js` holds the server URL
- [ ] Removed items done (Store, rotate gate, service worker, manifest, toggles, Google Fonts, duplicate images)
- [ ] Fonts and assets bundled for offline use
- [ ] New HUD and pause menu
- [ ] Home screen (three equal buttons, avatar in name chip)
- [ ] Solo setup screen with `startSoloMatch` stub
- [ ] Game-over changes
- [ ] App builds and launches

**Chunk B**
- [ ] Solo simulation runs on the device
- [ ] `startSoloMatch` implemented
- [ ] Pause freezes the match
- [ ] Bots with Easy / Medium / Hard
- [ ] 1 to 5 bots per match
- [ ] Solo game-over flow

**Chunk C**
- [ ] Online play works against the hosted server
- [ ] Native share sheet for invites
- [ ] Network bars and reconnect handling
- [ ] Back button behavior verified online
- [ ] Tested on real devices
- [ ] Icon, splash, signed APK, release build tested

## 7. Log (add notes here as you finish)

- Chunk A: _(what you did, what you deleted, anything the next person must know)_
- Chunk B: _
- Chunk C: _
