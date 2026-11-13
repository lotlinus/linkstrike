function start() {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const COLORS = ["#7fb04a", "#d8dde3", "#ff9a3c", "#e0453f", "#a65fe0", "#3f8fe0", "#d6b23a", "#2fbfa5", "#e06fa8", "#8a8f99"];   // one per soldier
  const SKIN_N = (window.AVATARS || []).length || 6;                                  // number of playable soldiers (from avatars.js)
  const INTERP_MS = 100;           // render this far in the past for smooth motion
  const SPR = 0.85;                // sprite scale (128px frames)
  const PIV = 77;                  // aim pivot row in a 128px frame (gun height)
  const SPLIT = 96;                // frame rows above this swing with the aim; legs stay put
  const TIP = 0.0;                 // the held weapon points straight ahead
  // weapon held in the hands (id -> sprite length in frame px, x from the pivot, y below the aim line)
  const HAND = [{ len: 18, x: 12, y: 5 }, { len: 38, x: -3, y: 5 }, { len: 44, x: -10, y: 3 },
    { len: 46, x: -4, y: 4 }, { len: 44, x: -4, y: 4 }, { len: 44, x: -4, y: 4 }, { len: 36, x: -2, y: 4 },
    { len: 36, x: -2, y: 4 }, { len: 26, x: 4, y: 5 }, { len: 36, x: -2, y: 4 }, { len: 48, x: -6, y: 4 }, { len: 54, x: -8, y: 4 }];
  // per weapon id: 0 Pistol, 1 Shotgun, 2 Rocket, 3 AK-47, 4 M4A1, 5 SCAR, 6 MP5, 7 UMP45, 8 MAC-10, 9 P90, 10 M249, 11 AWM
  const W_ICON = ["glock", "shotgun", "rocket", "ak47", "m4a1", "scar", "mp5", "ump45", "mac10", "p90", "m249", "awm"];
  const W_HAND = ["0", "1", "2", "ak47", "m4a1", "scar", "mp5", "ump45", "mac10", "p90", "m249", "awm"];
  const W_FLASH = [0, 1, 2, 0, 1, 1, 0, 0, 0, 0, 1, 1];                         // which flash sprite
  const FLASH_W = [26, 46, 58, 30, 38, 40, 28, 28, 26, 28, 40, 48];   // muzzle flash sprite width in world px, per weapon
  const W_SND = ["pistol_fire", "shotgun_fire", "rocket_launch", "rifle_heavy_fire", "rifle_fire", "rifle_heavy_fire", "smg_fire", "smg_fire", "smg_fire", "smg_fire", "rifle_heavy_fire", "sniper_fire"];
  const W_RELOAD = ["reload_pistol", "reload_shotgun", "reload_rocket", "reload_rifle", "reload_rifle", "reload_rifle", "reload_smg", "reload_smg", "reload_smg", "reload_smg", "reload_lmg", "reload_sniper"];
  const W_VERB = [" shot ", " shredded ", " rocketed ", " shot ", " shot ", " shot ", " sprayed ", " sprayed ", " sprayed ", " sprayed ", " gunned down ", " sniped "];
  const AIM_LIMIT = 1.3;
  const BULLET_SPEED = [1500, 1300, 760, 2600];   // by projectile type (3 = sniper round)
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const dprNow = () => Math.min(window.devicePixelRatio || 1, 2);

  // ------------------------------------------------------------ state
  let me = null, code = null, world = null, isHost = false, lobby = null;
  let snaps = [], evq = [], rtt = null, rafId = 0, toastTimer = 0;
  let phase = "play", winner = -1, overShown = false;
  let clockLeft = 0, sudden = false, sdIds = [], endReason = "", prevPhase = "", prevSudden = false, lastCountN = 0, goUntil = 0, sdTimer = 0;
  // Final-kill finisher: slow-mo + zoom on the victim, then a swing to the killer.
  const FIN_SLOW = 0.25, FIN_MAX_S = 4;
  let pnow = 0, fxMs = 0, zoomCur = 1, finisher = null, finQueued = false, lastKill = null;
  let latest = null;
  let localAim = 0, myPos = null;
  let shake = 0, hurtFlash = 0, lastFrame = 0, boardKey = "";
  let actx = null, noiseBuf = null, muted = false, volume = 1, ambientG = null;
  let sfxVol = 1, musicVol = 1, shakeOn = true, fireThr = 14, padK = 1;   // saved in Settings
  const cam = { x: 1600, y: 1200 };
  const view = { sc: 1 };
  const pst = new Map();
  const parts = [], expls = [], flashes = [];
  // immersion: damage numbers, hit markers, streaks, jetpack voices, ambience ducking
  const floaters = [], marks = [], jets = new Map(), streaks = new Map();
  let multiN = 0, multiAt = 0, streakTimer = 0, hbAt = 0, hbPulse = 0, lowHp = 0, fdtCur = 1 / 60, duck = 0;
  let ambKey = "", ambFilter = null;

  const socket = io();
  let connectedOnce = false, creating = false;

  // ------------------------------------------------------------ ui helpers
  function show(name) {
    for (const id of ["home", "lobby", "game"]) $(id).classList.toggle("active", id === name);
    for (const id of ["roomSheet", "avSheet", "storeSheet", "setSheet", "lbSheet", "helpSheet"]) $(id).hidden = true;   // menu sheets never follow you into a room
    if (name === "game") { resetPads(); startRender(); }
    else { cancelAnimationFrame(rafId); rafId = 0; stopJets(); }
    syncAmbient();
  }

  function toast(msg, bad) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.toggle("bad", !!bad);
    if (bad) play("button_error", 0.8);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
  }

  function myName() {
    const n = $("nameInput").value.trim();      // blank is fine: the server hands out Soldier, Soldier 2, ...
    try { localStorage.setItem("ls_name", n); } catch (e) {}
    return n;
  }
  // anonymous id for the leaderboard; the name is only a label
  function deviceId() {
    let d = "";
    try { d = localStorage.getItem("ls_device") || ""; } catch (e) {}
    if (!/^[A-Za-z0-9-]{8,64}$/.test(d)) {
      d = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : "d" + Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
      try { localStorage.setItem("ls_device", d); } catch (e) {}
    }
    return d;
  }
  const inviteUrl = () => location.origin + "/r/" + code;
  // which character a player is wearing: the one they picked (the server makes it unique in the room)
  const skinOf = (id) => {
    const p = lobby && lobby.players.find((q) => q.id === id);
    return p && Number.isInteger(p.skin) ? p.skin % SKIN_N : id % SKIN_N;
  };
  const colorOf = (id) => COLORS[skinOf(id) % COLORS.length];
  // the weapon skin a player has on for weapon wid (null = the standard look)
  const wskinOf = (id, wid) => {
    const p = lobby && lobby.players.find((q) => q.id === id);
    return (p && p.ws && p.ws[String(wid)]) || null;
  };
  const wIconSrc = (wid, id) => { const k = wskinOf(id, wid); return k ? "/static/img/wpn/skins/" + k + ".png?v=1" : "/static/img/wpn/" + (W_ICON[wid] || "glock") + ".png?v=1"; };
  const AVATARS = window.AVATARS || [];
  function mySkin() {            // saved choice from the Avatar screen; null lets the server give the first free one
    try { const v = parseInt(localStorage.getItem("ls_skin"), 10); if (v >= 0 && v < SKIN_N) return v; } catch (e) {}
    return null;
  }
  const nameOf = (id) => {
    const p = lobby && lobby.players.find((q) => q.id === id);
    return p ? p.name : "Soldier";
  };

  // ------------------------------------------------------------ home
  try { $("nameInput").value = localStorage.getItem("ls_name") || ""; } catch (e) {}
  try { $("roomNameInput").value = localStorage.getItem("ls_room") || ""; } catch (e) {}
  if (window.ROOM_CODE) {
    $("inviteCode").textContent = window.ROOM_CODE;
    $("inviteBlock").hidden = false;
    $("mainBlock").hidden = true;
  }
  function online() {
    if (socket.connected) return true;
    toast("Not connected to the server yet. Retrying...", true);
    return false;
  }
  const cap = 6;   // every room is 6 players
  // top-left server pill on the landing page
  const nameBox = $("nameBox");
  function doCreate() {
    if (!online()) return;
    const rn = $("roomNameInput").value.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    if (rn.length < 3) return toast("Name your room: 3 to 12 letters or numbers.", true);
    try { localStorage.setItem("ls_room", rn); } catch (e) {}
    creating = true;
    socket.emit("create_room", { name: myName(), device: deviceId(), skin: mySkin(), room_name: rn, max_players: cap });
  }
  $("createBtn").onclick = () => { if (online()) openRoomSheet("create"); };
  $("joinOpenBtn").onclick = () => { if (online()) openRoomSheet("join"); };
  $("nameGoBtn").onclick = doCreate;
  $("roomNameInput").addEventListener("keydown", (e) => { if (e.key === "Enter") doCreate(); });

  // ALCATRAZ: the button only shows while tonight's room is open; whoever joins first is host and picks the map
  async function checkAlcatraz() {
    try {
      const res = await fetch("/api/alcatraz", { cache: "no-store" });
      const d = await res.json();
      const live = !!d.open && !window.ROOM_CODE;
      $("alcBlock").hidden = !live;
      if (live) $("alcSub").textContent = d.players ? d.players + " inside \u00b7 tap to join" : "Tap to join \u00b7 first in picks the map";
    } catch (e) {}
  }
  $("alcBtn").onclick = () => { if (online()) socket.emit("join", { code: "ALCATRAZ", name: myName(), device: deviceId(), skin: mySkin() }); };
  checkAlcatraz();
  setInterval(() => { if (!document.hidden) checkAlcatraz(); }, 15000);
  $("joinBtn").onclick = joinTyped;
  $("codeInput").addEventListener("keydown", (e) => { if (e.key === "Enter") joinTyped(); });
  $("acceptBtn").onclick = () => { if (online()) socket.emit("join", { code: window.ROOM_CODE, name: myName(), device: deviceId(), skin: mySkin() }); };
  $("ownRoomBtn").onclick = () => {
    history.replaceState(null, "", "/");
    window.ROOM_CODE = "";
    $("inviteBlock").hidden = true;
    $("mainBlock").hidden = false;
  };
  function joinTyped() {
    const c = $("codeInput").value.trim().toUpperCase();
    if (c.length < 3) return toast("Enter the room code or name.", true);
    if (online()) socket.emit("join", { code: c, name: myName(), device: deviceId(), skin: mySkin() });
  }


  // ------------------------------------------------------------ leaderboard
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pad2 = (n) => (n < 10 ? "0" : "") + n;
  function lbRow(r, mine, cls) {
    return '<li class="lb-row ' + (cls || "") + (mine ? " me" : "") + '"><span class="rk">' + pad2(r.rank) +
      '</span><span class="nm">' + esc(r.name) + '</span><span class="kl">' + r.kills.toLocaleString() +
      '<small>' + (r.kills === 1 ? "kill" : "kills") + '</small></span></li>';
  }
  async function fetchBoard(limit) {
    try {
      const res = await fetch("/api/leaderboard?limit=" + limit + "&device=" + encodeURIComponent(deviceId()), { cache: "no-store" });
      if (!res.ok) throw new Error(res.status);
      return await res.json();
    } catch (e) { return { enabled: false, top: [], me: null }; }
  }
  $("lbAll").onclick = async () => {
    $("lbSheet").hidden = false;
    $("lbFull").innerHTML = '<li class="lb-empty">Loading...</li>';
    $("lbMe").innerHTML = "";
    const d = await fetchBoard(20);
    const m = d.me;
    $("lbFull").innerHTML = d.top.length
      ? d.top.map((r, i) => lbRow(r, m && r.rank === m.rank && r.name === m.name && r.kills === m.kills, i < 3 ? "r" + (i + 1) : "")).join("")
      : '<li class="lb-empty">No rankings yet</li>';
    $("lbMe").innerHTML = m
      ? '<ol class="lb-list">' + lbRow(m, true, "") + '</ol>'
      : (d.enabled ? '<div class="lb-empty">Finish a match with 3+ players to get ranked</div>' : "");
  };
  const closeBoard = () => { $("lbSheet").hidden = true; };
  $("lbClose").onclick = closeBoard;
  $("lbSheet").addEventListener("click", (e) => { if (e.target === $("lbSheet")) closeBoard(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeBoard(); });

  // ------------------------------------------------------------ settings
  $("setBtn").onclick = () => openSettings();
  const closeSettings = () => { $("setSheet").hidden = true; };
  $("setClose").onclick = closeSettings;
  $("setSheet").addEventListener("click", (e) => { if (e.target === $("setSheet")) closeSettings(); });

  // ------------------------------------------------------------ menu sheets: room name, avatar, store
  const sheetIds = ["roomSheet", "avSheet", "storeSheet", "setSheet", "lbSheet", "helpSheet"];
  function bindSheet(id, closeId) {
    const el = $(id), close = () => { el.hidden = true; };
    if (closeId) $(closeId).onclick = close;
    el.addEventListener("click", (e) => { if (e.target === el) close(); });
  }
  bindSheet("roomSheet", "roomClose");
  bindSheet("avSheet", "avClose");
  bindSheet("storeSheet", "storeClose");
  bindSheet("helpSheet", "helpClose");
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") for (const id of sheetIds) $(id).hidden = true;
  });
  function openRoomSheet(kind) {                // one small sheet for both: type the room name, then go
    $("nameBox").hidden = kind !== "create";
    $("joinBox").hidden = kind !== "join";
    $("roomSheet").hidden = false;
    setTimeout(() => $(kind === "create" ? "roomNameInput" : "codeInput").focus(), 50);
  }

  // home hero: the soldier in the centre is the player's saved avatar, and tapping it opens the avatar picker
  const heroEl = $("avHero"), heroSprite = $("heroSprite"), heroSlot = heroEl.querySelector(".st-slot");
  let heroShown;                                // last skin drawn (undefined until the first draw)
  function fitHero() {                          // whole-number pixel scale keeps the pixel art crisp at any screen size
    const h = heroSlot.clientHeight;
    if (h) heroEl.style.setProperty("--k", String(clamp(Math.floor((h - 4) / 73), 1, 6)));
  }
  function syncHero() {
    const v = mySkin(), a = AVATARS.find((q) => q.skin === v), sk = v === null ? 0 : v;
    heroEl.classList.toggle("unset", v === null);              // nothing picked yet: dark silhouette + "choose" prompt
    heroEl.style.setProperty("--ac", COLORS[sk % COLORS.length]);
    heroSprite.style.backgroundImage = 'url("/static/img/skin' + sk + '.png?v=4")';
    $("heroName").textContent = a ? a.name : "Choose your soldier";
    heroEl.setAttribute("aria-label", a ? "Your soldier is " + a.name + ". Change avatar" : "Choose your avatar");
    if (heroShown !== undefined && heroShown !== v) {          // little pop when the pick changes
      heroSprite.classList.remove("pop");
      void heroSprite.offsetWidth;
      heroSprite.classList.add("pop");
    }
    heroShown = v;
  }
  if (window.ResizeObserver) new ResizeObserver(fitHero).observe(heroSlot);
  addEventListener("resize", fitHero);
  addEventListener("orientationchange", fitHero);

  function syncMenuFace() {                     // profile chip + home soldier show the character you picked
    syncHero();
    const v = mySkin(), img = $("chipFace");
    img.toggleAttribute("hidden", v === null);                 // (SVG elements have no .hidden property)
    $("chipIcon").toggleAttribute("hidden", v !== null);
    if (v !== null) img.src = "/static/img/avatars/a" + v + ".jpg?v=1";
    const a = AVATARS.find((q) => q.skin === v);
    $("avNow").textContent = a ? "Playing as " + a.name : "Pick your character";
  }
  function renderAvatars() {
    const grid = $("avGrid"), cur = mySkin();
    grid.textContent = "";
    for (const a of AVATARS) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "av-card" + (cur === a.skin ? " on" : "");
      b.setAttribute("aria-pressed", String(cur === a.skin));
      b.style.setProperty("--ac", COLORS[a.skin % COLORS.length]);
      const img = document.createElement("img");
      img.src = "/static/img/avatars/a" + a.skin + ".png?v=1";
      img.alt = "";
      img.draggable = false;
      const nm = document.createElement("span");
      nm.textContent = a.name;
      b.append(img, nm);
      b.onclick = () => {
        try { localStorage.setItem("ls_skin", String(a.skin)); } catch (e) {}
        renderAvatars();
        syncMenuFace();
      };
      grid.append(b);
    }
  }
  heroEl.onclick = () => { renderAvatars(); syncMenuFace(); $("avSheet").hidden = false; };   // the soldier is the avatar button
  // ------------------------------------------------------------ store (Link Coins -> weapon skins)
  let storeData = null;
  function setCoinChip(n) {         // Link Coin balance on the home screen's Store tile
    $("tileCoinsN").textContent = n;
    $("tileCoins").hidden = false;
  }
  const SKIN_DIR = "/static/img/wpn/skins/";
  async function storeCall(path, body) {
    const res = await fetch(path, { method: body ? "POST" : "GET", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(Object.assign({ device: deviceId() }, body)) : undefined });
    return res.json();
  }
  function renderStore() {
    const d = storeData, list = $("storeList");
    list.textContent = "";
    $("storeBal").hidden = !(d && d.enabled);
    if (!d || !d.enabled) { $("storeMsg").textContent = d ? "The store is offline right now. Try again later." : "Loading..."; $("storeMsg").hidden = false; return; }
    $("storeMsg").hidden = true;
    $("storeCoins").textContent = d.coins;
    $("storeToday").textContent = d.today + " / " + d.cap;
    const byW = new Map();
    for (const k of d.skins) { if (!byW.has(k.wid)) byW.set(k.wid, []); byW.get(k.wid).push(k); }
    for (const [wid, skins] of byW) {
      const h = document.createElement("div"); h.className = "sk-w"; h.textContent = skins[0].weapon.toUpperCase(); list.append(h);
      for (const k of skins) {
        const row = document.createElement("div"); row.className = "sk-row" + (k.equipped ? " on" : "");
        const im = document.createElement("img"); im.src = SKIN_DIR + k.id + ".png?v=1"; im.alt = ""; im.loading = "lazy";
        const nm = document.createElement("span"); nm.className = "sk-name";
        const t = document.createElement("b"); t.textContent = k.name;
        const tier = document.createElement("small"); tier.className = "sk-tier " + k.tier; tier.textContent = k.tier;
        nm.append(t, tier);
        const btn = document.createElement("button"); btn.type = "button"; btn.className = "sk-btn";
        if (k.equipped) { btn.textContent = "Equipped"; btn.dataset.a = "off"; }
        else if (k.owned) { btn.textContent = "Equip"; btn.dataset.a = "equip"; }
        else { btn.textContent = k.price + " coins"; btn.dataset.a = "buy"; btn.classList.toggle("poor", d.coins < k.price); }
        btn.onclick = () => storeAct(k, btn.dataset.a);
        row.append(im, nm, btn); list.append(row);
      }
    }
  }
  function applyStoreState(st) {
    if (!storeData || !st) return;
    const own = new Set(st.owned), eq = new Set(Object.values(st.equipped));
    storeData.coins = st.coins; storeData.today = st.today; setCoinChip(st.coins);
    for (const k of storeData.skins) { k.owned = own.has(k.id); k.equipped = eq.has(k.id); }
  }
  async function storeAct(k, act) {
    if (act === "off") { try { const r = await storeCall("/api/store/equip", { weapon: k.wid }); if (r.ok) { applyStoreState(r.state); renderStore(); } } catch (e) {} return; }
    try {
      const r = act === "buy" ? await storeCall("/api/store/buy", { skin: k.id }) : await storeCall("/api/store/equip", { skin: k.id });
      if (r.state) applyStoreState(r.state);
      if (!r.ok) toast(r.error === "coins" ? "Not enough Link Coins" : r.error === "owned" ? "You already own this skin" : "Couldn't do that. Try again.", true);
      else if (act === "buy") toast(k.name + " is yours and equipped");
      renderStore();
    } catch (e) { toast("Couldn't reach the store", true); }
  }
  async function openStore() {
    $("storeSheet").hidden = false;
    renderStore();
    try { storeData = await storeCall("/api/store?device=" + encodeURIComponent(deviceId())); } catch (e) { storeData = { enabled: false }; }
    if (storeData.enabled) setCoinChip(storeData.coins);
    renderStore();
  }
  $("storeBtn").onclick = openStore;
  // show the balance on the home screen without opening the Store
  storeCall("/api/store?device=" + encodeURIComponent(deviceId())).then((d) => { if (d && d.enabled) { storeData = d; setCoinChip(d.coins); } }).catch(() => {});
  syncMenuFace();
  fitHero();
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSettings(); });
  $("setSound").onclick = toggleMute;
  $("setVol").oninput = (e) => {
    volume = clamp(Number(e.target.value) / 100, 0, 1);
    try { localStorage.setItem("ls_vol", String(volume)); } catch (err) {}
    setAmbVol();
  };
  // ------------------------------------------------------------ lobby
  $("codeBtn").onclick = () => copy(code, "Room name copied");
  $("copyBtn").onclick = () => copy(code, "Room name copied");
  $("shareBtn").onclick = async () => {
    const url = inviteUrl();
    if (navigator.share) {
      try { await navigator.share({ title: "Link Strike", text: "Join my Link Strike room", url }); return; }
      catch (e) { if (e && e.name === "AbortError") return; }
    }
    copy(url, "Invite link copied");
  };
  $("startBtn").onclick = () => { socket.emit("start_game"); enterFullscreen(); };
  $("leaveLobbyBtn").onclick = leaveRoom;
  // weapon select: the primary weapon is chosen here and stays fixed for the match
  function myWeapon() {
    const m = lobby && lobby.players.find((q) => q.id === me);
    return m ? m.weapon : 3;
  }
  function renderWeaponTable() {
    if (!lobby || !lobby.weapons) return;
    const mine = myWeapon();
    $("wpnRows").innerHTML = lobby.weapons.map((w) =>
      '<tr class="pick' + (w.id === mine ? " on" : "") + '" data-w="' + w.id + '"><td><span class="wn"><img src="/static/img/wpn/' + W_ICON[w.id] + '.png?v=1" alt="">' + w.name + "</span></td>" +
      "<td>" + (w.pellets > 1 ? w.dmg + "\u00d7" + w.pellets : w.dmg) + (w.id === 2 ? " splash" : "") + "</td><td>" + w.rate + "/s</td><td>" + w.mag + "</td><td>" + w.reload + "s</td></tr>").join("");
  }
  const openWeapons = () => { if (lobby && (lobby.state === "lobby" || phase === "over")) { renderWeaponTable(); $("wpnSheet").hidden = false; } };
  $("overWpnBtn").onclick = openWeapons;
  $("wpnRows").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-w]");
    if (!tr) return;
    socket.emit("set_weapon", { weapon: Number(tr.dataset.w) });
    $("wpnSheet").hidden = true;
  });
  const closeWpn = () => { $("wpnSheet").hidden = true; };
  $("wpnClose").onclick = closeWpn;
  $("wpnSheet").addEventListener("click", (e) => { if (e.target === $("wpnSheet")) closeWpn(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeWpn(); });
  // ---- lobby: map preview, weapon strip, capacity and match-time selectors
  const MAP_UI = [
    { id: "lab", name: "Laboratory", desc: "A reactor chamber with catwalks all around it.", img: "/static/img/map_lab.jpg?v=1" },
    { id: "street", name: "Lagos Street", desc: "Rooftops, kiosks and a sewer under the road.", img: "/static/img/map_street.jpg?v=2" },
    { id: "stairs", name: "Staircase", desc: "Stairs, a top corridor, a big hall and a basement with ladders.", img: "/static/img/map_stairs.jpg?v=1" },
  ];
  const stepMap = (dir) => {
    if (!isHost || !lobby) return;
    const i = Math.max(0, MAP_UI.findIndex((m) => m.id === lobby.map));
    socket.emit("set_map", { map: MAP_UI[(i + dir + MAP_UI.length) % MAP_UI.length].id });
  };
  $("mapPrev").onclick = () => stepMap(-1);
  $("mapNext").onclick = () => stepMap(1);
  $("mapDots").addEventListener("click", (e) => {
    const d = e.target.closest("[data-map]");
    if (d && isHost) socket.emit("set_map", { map: d.dataset.map });
  });
  $("capSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (b && isHost && !b.disabled) socket.emit("set_cap", { max: Number(b.dataset.v) });
  });
  $("durSeg").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (b && isHost) socket.emit("set_duration", { duration: Number(b.dataset.v) });
  });
  $("wpnStrip").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-w]");
    if (b && lobby && lobby.state === "lobby") socket.emit("set_weapon", { weapon: Number(b.dataset.w) });
  });
  const fmtTime = (sec) => { sec = Math.max(0, Math.ceil(sec)); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); };
  $("exitBtn").onclick = leaveRoom;
  $("overLeave").onclick = leaveRoom;
  $("againBtn").onclick = () => socket.emit("rematch");
  // every player votes for the rematch themselves; it starts when all of them have
  // The first tap starts a 10 s countdown; when it ends the match starts with the players who tapped.
  let againEnd = 0;
  function renderAgain() {
    const b = $("againBtn");
    if (phase !== "over" || !lobby) { b.hidden = true; $("againWait").hidden = true; return; }
    const votes = lobby.again || [], voted = votes.includes(me);
    const left = againEnd ? Math.max(0, Math.ceil((againEnd - performance.now()) / 1000)) : null;
    b.hidden = false;
    b.textContent = (voted ? "Waiting " : "Play again ") + "(" + votes.length + "/" + lobby.players.length + ")" + (left !== null ? " \u00b7 " + left + "s" : "");
    b.classList.toggle("on", voted);
    $("againWait").hidden = false;
    $("againWait").textContent = left === null ? "Tap Play again. Others get 10 seconds to join you."
      : voted ? "Starting in " + left + "s with everyone who tapped. Tap again to cancel."
      : "Starting in " + left + "s. Tap Play again or you'll go back to the menu.";
  }
  setInterval(() => { if (phase === "over") renderAgain(); }, 250);
  $("fsBtn").onclick = () => { enterFullscreen(); closePause(); };
  // in-match menu (Sound, Full screen, Settings); Exit stays on the HUD
  const closePause = () => { $("pauseSheet").hidden = true; };
  $("pauseBtn").onclick = () => { $("pauseSheet").hidden = false; };
  $("resumeBtn").onclick = closePause;
  $("pauseSheet").addEventListener("click", (e) => { if (e.target === $("pauseSheet")) closePause(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePause(); });
  // connection bars: green (under 100 ms), yellow (under 250 ms), red (slower)
  function setNet(ms) {
    const q = ms < 100 ? 3 : ms < 250 ? 2 : 1;
    $("netBars").className = "bars q" + q;
    $("hudPing").textContent = ms;
  }
  function toggleMute() {
    muted = !muted;
    try { localStorage.setItem("ls_mute", muted ? "1" : "0"); } catch (e) {}
    $("sndBtn").textContent = muted ? "Muted" : "Sound";
    $("setSound").textContent = muted ? "Off" : "On";
    syncAmbient();
  }
  $("sndBtn").onclick = toggleMute;

  function copy(text, okMsg) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast(okMsg), () => toast(text));
    } else toast(text);
  }

  // phones held upright get a rotate prompt; the tap that dismisses it goes fullscreen and locks landscape (Android Chrome).
  // Where the browser can't lock (iPhone), the prompt just asks them to turn the phone and goes away on its own.
  const gate = $("rotateGate"), upright = matchMedia("(orientation: portrait)"), touchy = matchMedia("(pointer: coarse)");
  const canLock = !!(screen.orientation && screen.orientation.lock);
  const syncGate = () => { gate.hidden = !(touchy.matches && upright.matches); };
  $("rgBtn").hidden = !canLock;
  upright.addEventListener("change", syncGate);
  gate.addEventListener("click", () => { enterFullscreen(); });
  syncGate();

  function enterFullscreen() {
    const el = document.documentElement;
    const req = el.requestFullscreen || el.webkitRequestFullscreen;
    if (req && !document.fullscreenElement) {
      Promise.resolve(req.call(el)).then(() => {
        if (screen.orientation && screen.orientation.lock) screen.orientation.lock("landscape").catch(() => {});
      }).catch(() => {});
    }
  }


  function leaveRoom() {
    renderLobby.scrolled = false;
    socket.emit("leave");
    code = null; world = null; lobby = null; snaps = []; evq = []; latest = null; me = null;
    pst.clear(); parts.length = 0; expls.length = 0; flashes.length = 0; resetFx();
    $("over").hidden = true; $("feed").textContent = "";
    history.replaceState(null, "", "/");
    window.ROOM_CODE = "";
    $("inviteBlock").hidden = true;
    $("mainBlock").hidden = false;
    $("nameBox").hidden = true;
    show("home");
  }

  function renderLobby() {
    if (!lobby) return;
    isHost = lobby.host === me;
    $("codeBtn").textContent = lobby.code;
    $("playerCount").textContent = lobby.players.length + " / " + lobby.max;

    // roster: one row per player, then dim "open" slots up to the room's capacity
    const ul = $("playerList");
    ul.textContent = "";
    for (const p of lobby.players) {
      const li = document.createElement("li");
      li.className = "rs" + (p.id === me ? " me" : "");
      li.style.setProperty("--pc", colorOf(p.id));
      const av = document.createElement("img");
      av.className = "avatar";
      av.alt = "";
      av.src = "/static/img/avatars/a" + skinOf(p.id) + ".jpg?v=1";
      const who = document.createElement("span");
      who.className = "rs-who";
      const nm = document.createElement("b");
      nm.textContent = p.name;
      const sub = document.createElement("small");
      const pw = lobby.weapons && lobby.weapons.find((w) => w.id === p.weapon);
      sub.textContent = (p.id === lobby.host ? "Host" : p.id === me ? "You" : "Player") + (pw ? " \u00b7 " + pw.name : "");
      who.append(nm, sub);
      const st = document.createElement("span");
      st.className = "rs-st";
      st.textContent = "Ready";
      li.append(av, who, st);
      ul.append(li);
    }
    for (let i = lobby.players.length; i < lobby.max; i++) {
      const li = document.createElement("li");
      li.className = "rs open";
      const av = document.createElement("span");
      av.className = "avatar ph";
      const who = document.createElement("span");
      who.className = "rs-who";
      who.innerHTML = "<b>Open slot</b>";
      li.append(av, who);
      ul.append(li);
    }

    // map preview
    const mi = Math.max(0, MAP_UI.findIndex((m) => m.id === (lobby.map || "lab")));
    const mp = MAP_UI[mi];
    if ($("mapImg").dataset.s !== mp.img) { $("mapImg").dataset.s = mp.img; $("mapImg").src = mp.img; }
    $("mapName").textContent = mp.name;
    $("mapDesc").textContent = mp.desc;
    $("mapDots").innerHTML = MAP_UI.map((m, i) => '<i data-map="' + m.id + '" class="' + (i === mi ? "on" : "") + '"></i>').join("");
    $("mapBox").classList.toggle("locked", !isHost);
    $("mapPrev").disabled = $("mapNext").disabled = !isHost;
    $("mapLock").hidden = isHost;

    // capacity + match time (host edits, everyone sees)
    const caps = [2, 3, 4, 5, 6];
    $("capSeg").innerHTML = caps.map((n) =>
      '<button type="button" role="radio" data-v="' + n + '" class="' + (n === lobby.max ? "on" : "") + '"' +
      (!isHost || n < lobby.players.length ? " disabled" : "") + ' aria-checked="' + (n === lobby.max) + '">' + n + "</button>").join("");
    const durs = lobby.durations || [180, 300, 600];
    $("durSeg").innerHTML = durs.map((d) =>
      '<button type="button" role="radio" data-v="' + d + '" class="' + (d === lobby.duration ? "on" : "") + '"' +
      (!isHost ? " disabled" : "") + ' aria-checked="' + (d === lobby.duration) + '">' + Math.round(d / 60) + " min</button>").join("");
    $("ruleLine").textContent = "First to " + (lobby.target || 10) + " kills, or most kills at " + fmtTime(lobby.duration || 300) + ". Ties go to sudden death.";

    // weapons: pick right here, locked once the match starts
    const mine = myWeapon(), open = lobby.state === "lobby";
    if (lobby.weapons) {
      const strip = $("wpnStrip"), keepX = strip.scrollLeft;
      strip.innerHTML = lobby.weapons.map((w) =>
        '<button type="button" role="option" data-w="' + w.id + '" class="wchip' + (w.id === mine ? " on" : "") + '"' + (open ? "" : " disabled") +
        ' aria-selected="' + (w.id === mine) + '"><img src="/static/img/wpn/' + W_ICON[w.id] + '.png?v=1" alt="" loading="lazy" decoding="async"><span>' + w.name + "</span></button>").join("");
      strip.scrollLeft = keepX;
      const sel = strip.querySelector(".on");
      if (sel && !renderLobby.scrolled) { renderLobby.scrolled = true; strip.scrollLeft = sel.offsetLeft - strip.clientWidth / 2 + sel.offsetWidth / 2; }
    }
    const mw = lobby.weapons && lobby.weapons.find((w) => w.id === mine);
    $("wpnStats").textContent = mw ? "DMG " + (mw.pellets > 1 ? mw.dmg + "\u00d7" + mw.pellets : mw.dmg) + " \u00b7 " + mw.rate + "/s \u00b7 MAG " + mw.mag + " \u00b7 RLD " + mw.reload + "s" : "";

    // actions
    const canStart = lobby.players.length >= lobby.min;
    $("startBtn").hidden = !isHost;
    $("startBtn").disabled = !canStart;
    $("startBtn").textContent = canStart ? "Start match" : "Need " + lobby.min + " players";
    $("waitMsg").hidden = isHost;
    $("overWpnText").textContent = "Choose weapon";
    $("overWpnBtn").title = mw ? "Current: " + mw.name : "";
    renderAgain();
    $("overWpnIcon").src = "/static/img/wpn/" + (W_ICON[mine] || "ak47") + ".png?v=1";
    if (!$("wpnSheet").hidden) renderWeaponTable();
    boardKey = "";
    if (latest) updateHud();
  }

  // ------------------------------------------------------------ socket events
  const connEl = $("conn");
  function status(msg, cls) { connEl.textContent = msg; connEl.className = "conn " + (cls || ""); }
  socket.on("connect_error", () => { status("Can't reach the server. Retrying...", "bad"); });
  socket.on("connect", () => {
    status("Connected", "ok");
    setTimeout(() => { if (socket.connected) connEl.className = "conn hide"; }, 1500);
    if (connectedOnce && code) socket.emit("join", { code, name: myName(), device: deviceId(), skin: mySkin() });
    connectedOnce = true;
  });
  socket.on("disconnect", () => { status("Connection lost. Reconnecting...", "bad"); });

  socket.on("joined", (d) => {
    code = d.code; me = d.you;
    history.replaceState(null, "", "/r/" + code);
    if (creating) { creating = false; play("room_created", 0.9); }
    if (!$("game").classList.contains("active")) show("lobby");
    renderLobby();
  });
  socket.on("lobby", (d) => {
    if (lobby && lobby.code === d.code && me != null) {      // someone else came or went
      const had = new Set(lobby.players.map((q) => q.id)), now = new Set(d.players.map((q) => q.id));
      if (d.players.some((q) => !had.has(q.id) && q.id !== me)) play("player_joined", 0.9);
      else if (lobby.players.some((q) => !now.has(q.id))) play("player_left", 0.9);
    }
    lobby = d; againEnd = d.again_in != null ? performance.now() + d.again_in * 1000 : 0; renderLobby();
  });

  socket.on("start", (d) => {
    world = d.world;
    loadArt(world);
    snaps = []; evq = []; latest = null;
    pst.clear(); parts.length = 0; expls.length = 0; flashes.length = 0; resetFx();
    $("over").hidden = true; $("feed").textContent = "";
    phase = "count"; overShown = false; sudden = false; prevPhase = ""; prevSudden = false; lastCountN = 0; goUntil = 0;
    clearFinisher(); finQueued = false; lastKill = null;
    buildTiles();
    show("game");
    play("match_start", 0.9);
  });

  socket.on("state", (d) => {
    const at = performance.now();
    snaps.push({ at, p: d.p, b: d.b });
    if (snaps.length > (finQueued ? 150 : 12)) snaps.shift();
    for (const e of d.e) evq.push({ due: at + INTERP_MS, e });
    if (d.m[0] === "final" && !finQueued) {       // the winning kill is in this snapshot: start the finisher after its events
      finQueued = true;
      evq.push({ due: at + INTERP_MS, e: ["fin", d.m[1]] });
    } else if ((d.m[0] === "play" || d.m[0] === "count") && finQueued) {  // rematch
      finQueued = false; lastKill = null; clearFinisher();
    }
    latest = d;
    trackPlayers(d, at);
    phase = d.m[0]; winner = d.m[1];
    clockLeft = d.m[2] || 0; sudden = !!d.m[3]; sdIds = d.m[4] || []; endReason = d.m[5] || "";
    if (phase === "over" && finisher) clearFinisher();   // results screen takes over
    updateHud();
  });

  socket.on("coins", (d) => {
    if (storeData && storeData.enabled) { storeData.coins = d.coins; storeData.today = d.today; }
    setCoinChip(d.coins);
    if (d.earned > 0) toast("+" + d.earned + " Link Coins" + (d.earned < d.wanted ? " (daily limit reached)" : ""));
    else if (d.wanted > 0) toast("Daily Link Coin limit reached");
  });
  socket.on("error_msg", (d) => {
    creating = false;
    toast(d.msg, true);
    if (d.gone && code) leaveRoom();
  });

  setInterval(() => {
    if (!socket.connected) return;
    const t0 = performance.now();
    socket.emit("pingx", () => {
      rtt = Math.round(performance.now() - t0);
      setNet(rtt);
    });
  }, 2000);

  // ------------------------------------------------------------ per-player visual state
  function trackPlayers(d, at) {
    const seen = new Set();
    for (const p of d.p) {
      seen.add(p[0]);
      let st = pst.get(p[0]);
      if (!st) { st = { hp: p[6], dead: false, deadAt: 0, hurtAt: 0, hurtUntil: 0, air: false, airVy: 0, stepD: 0, lastX: null }; pst.set(p[0], st); }
      const dead = !!(p[8] & 4);
      if (dead && !st.dead) st.deadAt = at;
      if (!dead && st.dead) { st.hp = p[6]; if (p[0] === me) SFX.respawn(); }
      // footsteps while walking on the ground, a thud when landing from a real fall
      if (!dead && (p[8] & 1)) {
        if (st.air && st.airVy > 160) { SFX.land(p[1], p[2]); landDust(p[1] + world.pw / 2, p[2] + world.ph, st.airVy); }
        else if (st.lastX != null) {
          st.stepD += Math.abs(p[1] - st.lastX);
          if (st.stepD > 70) { st.stepD = 0; SFX.step(p[1], p[2]); }
        }
        st.air = false;
      } else { st.air = true; st.airVy = p[4]; st.stepD = 0; }
      st.lastX = dead ? null : p[1];
      if (!dead && p[6] < st.hp) {
        st.hurtAt = at; st.hurtUntil = at + 220;
        if (p[0] === me) { hurtFlash = 1; SFX.hurt(); }
      }
      st.hp = p[6]; st.dead = dead;
    }
    for (const id of Array.from(pst.keys())) if (!seen.has(id)) pst.delete(id);
  }

  // ------------------------------------------------------------ match clock (the server owns it; this only displays it)
  function updateClock(mine) {
    const target = (world && world.target) || (lobby && lobby.target) || 10;
    const box = $("hudTimer"), cd = $("countdown");
    let t, sub;
    if (phase === "count") { t = fmtTime(lobby ? lobby.duration : 300); sub = "Get ready"; }
    else if (sudden) { t = "0:00"; sub = sdIds.includes(me) ? "Sudden death: next kill wins" : "Sudden death"; }
    else { t = fmtTime(clockLeft); sub = "Kills " + (mine ? mine[9] : 0) + " / " + target; }
    if (phase === "over" || phase === "final") sub = phase === "final" ? "Final kill" : "Match over";
    $("timeText").textContent = t;
    $("timeSub").textContent = sub;
    box.classList.toggle("low", phase === "play" && !sudden && clockLeft <= 30);
    box.classList.toggle("sd", sudden && phase !== "over");
    box.classList.toggle("wait", phase === "count");
    // 3-2-1-GO
    const now = performance.now();
    if (phase === "count") {
      const n = Math.max(1, Math.ceil(clockLeft));
      cd.hidden = false; cd.textContent = String(n); cd.className = "countdown";
      if (n !== lastCountN) { lastCountN = n; cd.classList.add("pop"); play("button_click", 0.55); }
    } else if (prevPhase === "count" && phase === "play") {
      goUntil = now + 800; lastCountN = 0;
      cd.hidden = false; cd.textContent = "GO!"; cd.className = "countdown go pop";
      play("match_start", 0.6);
      setTimeout(() => { if (performance.now() >= goUntil) cd.hidden = true; }, 850);
    } else if (now >= goUntil) cd.hidden = true;
    if (phase !== "play") { $("sdBanner").hidden = true; clearTimeout(sdTimer); }
    // sudden death flash (once)
    if (sudden && !prevSudden && phase === "play") {
      const sdb = $("sdBanner");
      sdb.textContent = sdIds.includes(me) ? "Sudden death: next kill wins" : "Sudden death";
      sdb.hidden = false; clearTimeout(sdTimer); sdTimer = setTimeout(() => { sdb.hidden = true; }, 2600);
      play("kill_confirm", 0.7);
    }
    prevSudden = sudden; prevPhase = phase;
  }

  // ------------------------------------------------------------ HUD
  function updateHud() {
    if (!latest) return;
    const mine = latest.p.find((p) => p[0] === me);
    updateClock(mine);
    if (mine) {
      const hp = mine[6];
      $("hpFill").style.width = hp + "%";
      $("hpFill").style.background = hp > 55 ? "#5fc24a" : hp > 25 ? "#e8b02e" : "#d24a43";
      $("hpText").textContent = hp;
      const w = world && world.weapons[String(mine[7])];
      $("wpnText").textContent = w ? w.name : "";
      $("wpnAmmo").textContent = w ? ((mine[8] & 32) ? "Reload" : mine[10] + " / " + w.mag) : "";
      const wi = $("wpnIcon"), wsrc = wIconSrc(mine[7], me);
      if (wi && wi.dataset.s !== wsrc) { wi.dataset.s = wsrc; wi.src = wsrc; }
      const pt = $("hudFace");
      const fsrc = "/static/img/avatars/a" + skinOf(me) + ".jpg?v=1";
      if (pt && pt.dataset.s !== fsrc) { pt.dataset.s = fsrc; pt.src = fsrc; }
      const b = $("banner");
      if ((mine[8] & 4) && phase === "play") {
        b.hidden = false;
        b.textContent = "Respawning in " + Math.max(1, Math.ceil(mine[11]));
      } else b.hidden = true;
    }
    const rows = latest.p.slice().sort((a, b) => b[9] - a[9] || a[0] - b[0]);
    const key = rows.map((p) => p[0] + ":" + p[9] + ":" + p[12]).join(",") + "|" + (lobby ? lobby.players.length : 0);
    if (key !== boardKey) {
      boardKey = key;
      fillBoard($("board"), rows, false);
      if (phase === "over") fillBoard($("overBoard"), rows, true);
    }
    if (phase === "over" && !overShown) {
      overShown = true;
      fillBoard($("overBoard"), rows, true);
      const sub = $("overSub");
      $("overTitle").textContent = winner === me ? "You win!" : nameOf(winner) + " wins!";
      sub.textContent = endReason === "time" ? "Time's up \u00b7 most kills wins"
        : endReason === "sudden" ? "Won in sudden death"
        : "First to " + ((world && world.target) || 10) + " kills";
      sub.hidden = false;
      const won = winner === me;
      $("over").hidden = false;
      renderAgain();
      $("banner").hidden = true;
      SFX.win();   // victory sound plays for every player when the match ends
    } else if ((phase === "play" || phase === "count") && overShown) {
      overShown = false;
      $("over").hidden = true;
    }
  }

  function fillBoard(ul, rows, big) {
    ul.textContent = "";
    if (!big && rows.length > 6) {
      const mineRow = rows.find((p) => p[0] === me);
      rows = rows.slice(0, 6);
      if (mineRow && !rows.includes(mineRow)) rows[5] = mineRow;
    }
    for (const p of rows) {
      const li = document.createElement("li");
      if (p[0] === me) li.className = "me";
      if (big && p[0] === winner) li.classList.add("win");
      if (big) { const rk = document.createElement("span"); rk.className = "rk"; rk.textContent = String(rows.indexOf(p) + 1); li.append(rk); }
      const dot = document.createElement("img");
      dot.className = "avatar";
      dot.alt = "";
      dot.src = "/static/img/avatars/a" + skinOf(p[0]) + ".jpg?v=1";
      dot.style.borderColor = colorOf(p[0]);
      dot.style.width = dot.style.height = big ? "30px" : "18px";
      const nm = document.createElement("span");
      nm.className = "nm";
      nm.textContent = nameOf(p[0]);
      const k = document.createElement("span");
      k.textContent = big ? p[9] + " kills \u00b7 " + p[12] + " deaths" : String(p[9]);
      li.append(dot, nm, k);
      ul.append(li);
    }
  }

  function feedRow(killer, victim, wpn) {
    const row = document.createElement("div");
    const a = document.createElement("span");
    a.style.color = colorOf(killer);
    a.textContent = nameOf(killer);
    const mid = document.createElement("span");
    if (killer === victim) {
      mid.textContent = " blew up";
      row.append(a, mid);
    } else {
      const b = document.createElement("span");
      b.style.color = colorOf(victim);
      b.textContent = nameOf(victim);
      mid.textContent = W_VERB[wpn] || " got ";
      row.append(a, mid, b);
    }
    const feed = $("feed");
    feed.append(row);
    while (feed.children.length > 4) feed.firstChild.remove();
    setTimeout(() => row.remove(), 4500);
  }

  // ------------------------------------------------------------ sound (WAV files in static/audio, synthesized fallback)
  try { muted = localStorage.getItem("ls_mute") === "1"; } catch (e) {}
  $("sndBtn").textContent = muted ? "Muted" : "Sound";
  try { const v = parseFloat(localStorage.getItem("ls_vol")); if (v >= 0 && v <= 1) volume = v; } catch (e) {}
  function ac() {
    if (!actx) {
      const C = window.AudioContext || window.webkitAudioContext;
      if (C) { try { actx = new C(); } catch (e) { actx = null; } }
    }
    return actx;
  }
  for (const ev of ["pointerdown", "keydown"]) {
    window.addEventListener(ev, () => {
      const a = ac();
      if (!a) return;
      loadSounds();
      if (a.state === "suspended") a.resume().then(syncAmbient, () => {}); else syncAmbient();
    }, { passive: true });
  }
  // menu clicks (any real <button>)
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest && e.target.closest("button");
    if (b && !b.disabled) play("button_click", 0.8);
  });

  // ---- WAV files (static/audio). If one is missing or still loading, the synthesized sound below plays instead.
  const SND = {};
  const SND_FILES = ["pistol_fire", "shotgun_fire", "rocket_launch", "rocket_explosion", "hit_marker", "player_hit",
    "player_death", "respawn", "kill_confirm", "weapon_pickup", "footstep_metal", "land", "button_click", "button_error",
    "room_created", "player_joined", "player_left", "match_start", "victory", "defeat", "menu_ambient",
    "smg_fire", "rifle_fire", "rifle_heavy_fire", "sniper_fire", "weapon_switch", "reload_pistol", "reload_shotgun", "reload_rocket",
    "reload_smg", "reload_rifle", "reload_lmg", "reload_sniper",
    "amb_lab", "amb_street", "amb_stairs", "jet_loop", "heartbeat", "hit_tick", "streak_1", "streak_2", "streak_3"];
  let sndLoading = false, ambient = null;
  function loadSounds() {
    const a = ac();
    if (!a || sndLoading) return;
    sndLoading = true;
    for (const n of SND_FILES) {
      fetch("/static/audio/" + n + ".wav?v=7")
        .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject()))
        .then((buf) => new Promise((res, rej) => a.decodeAudioData(buf, res, rej)))
        .then((b) => { SND[n] = b; if (n === "menu_ambient" || n.indexOf("amb_") === 0) syncAmbient(); })
        .catch(() => {});
    }
  }
  function play(name, vol, rate) {
    const a = actx, b = SND[name];
    if (!a || !b) return false;          // not ready: caller falls back to synth
    if (muted || a.state !== "running" || vol < 0.02) return true;
    const s = a.createBufferSource(); s.buffer = b;
    if (rate) s.playbackRate.value = rate;
    const g = a.createGain(); g.gain.value = vol * volume * sfxVol;
    s.connect(g); g.connect(a.destination); s.start();
    return true;
  }
  // ambience: menu loop on the landing page and lobby, a per-map bed (amb_lab / amb_street / amb_stairs) during a match
  function ambWant() {
    if (!(actx && actx.state === "running" && !muted)) return "";
    if ($("game").classList.contains("active")) {
      const n = "amb_" + ((world && world.map) || "lab");
      return SND[n] ? n : "";
    }
    return SND.menu_ambient ? "menu_ambient" : "";
  }
  function ambLevel() { return (ambKey === "menu_ambient" ? 1.8 : 1.3) * volume * musicVol; }
  function setAmbVol() { if (ambientG && actx) ambientG.gain.setTargetAtTime(ambLevel(), actx.currentTime, 0.05); }
  function syncAmbient() {
    const a = actx, want = ambWant();
    if (want === ambKey) return;
    if (ambient) { try { ambient.stop(); } catch (e) {} ambient = null; }
    ambKey = want;
    if (!want) return;
    const s = a.createBufferSource(); s.buffer = SND[want]; s.loop = true;
    const f = a.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 20000;
    const g = a.createGain(); g.gain.value = 0;
    s.connect(f); f.connect(g); g.connect(a.destination); s.start();
    g.gain.setTargetAtTime(ambLevel(), a.currentTime, 0.6);       // fade in
    ambientG = g; ambFilter = f; ambient = s;
  }
  // every frame: gunfire ducks the bed a little, and the Street goes muffled when you are down in the sewer
  function updateAmbience(dt, mine) {
    if (!ambient || ambKey === "menu_ambient" || !actx) return;
    duck *= Math.pow(0.35, dt);
    const t = actx.currentTime;
    ambientG.gain.setTargetAtTime(ambLevel() * (1 - 0.5 * Math.min(1, duck)), t, 0.08);
    if (world && world.street_row != null && mine) {
      const under = mine[2] + world.ph / 2 > world.street_row * world.tile + 8;
      ambFilter.frequency.setTargetAtTime(under ? 650 : 20000, t, 0.25);
    }
  }
  function noise(dur, f0, f1, vol, type) {
    const a = ac();
    if (!a || muted || vol < 0.02) return;
    if (!noiseBuf) {
      noiseBuf = a.createBuffer(1, a.sampleRate, a.sampleRate);
      const d = noiseBuf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    const s = a.createBufferSource(); s.buffer = noiseBuf; s.loop = true;
    const f = a.createBiquadFilter(); f.type = type || "lowpass";
    const t = a.currentTime;
    f.frequency.setValueAtTime(f0, t);
    f.frequency.exponentialRampToValueAtTime(Math.max(40, f1), t + dur);
    const g = a.createGain();
    g.gain.setValueAtTime(vol * volume * sfxVol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    s.connect(f); f.connect(g); g.connect(a.destination);
    s.start(t); s.stop(t + dur + 0.03);
  }
  function tone(f0, f1, dur, vol, type, delay) {
    const a = ac();
    if (!a || muted || vol < 0.02) return;
    const t = a.currentTime + (delay || 0);
    const o = a.createOscillator(); o.type = type || "square";
    o.frequency.setValueAtTime(f0, t);
    o.frequency.exponentialRampToValueAtTime(Math.max(30, f1), t + dur);
    const g = a.createGain();
    g.gain.setValueAtTime(vol * volume * sfxVol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g); g.connect(a.destination);
    o.start(t); o.stop(t + dur + 0.03);
  }
  const near = (x, y) => (x == null ? 1 : Math.max(0.1, 1 - Math.hypot(x - cam.x, y - cam.y) / 1400));
  const SFX = {
    shot: (w, x, y) => {
      const v = near(x, y);
      duck = Math.min(1, duck + 0.12 * v);
      const n = W_SND[w];
      if (n && play(n, 0.55 * v, 0.96 + Math.random() * 0.08)) return;
      if (w === 1) { noise(0.2, 3000, 300, 0.6 * v); tone(140, 45, 0.16, 0.25 * v, "sawtooth"); }
      else if (w === 2) { noise(0.35, 1200, 200, 0.5 * v); tone(200, 60, 0.3, 0.2 * v, "sawtooth"); }
      else { noise(0.09, 4500, 800, 0.35 * v, "highpass"); tone(380, 90, 0.08, 0.12 * v, "square"); }
    },
    reload: (w) => { play(W_RELOAD[w] || "reload_pistol", 0.7); },
    swap: () => { play("weapon_switch", 0.8); },
    boom: (x, y) => {
      const v = near(x, y);
      duck = Math.min(1, duck + 0.55 * v);
      if (play("rocket_explosion", 0.75 * v)) return;
      noise(0.9, 900, 60, 0.9 * v); tone(120, 28, 0.6, 0.4 * v, "sawtooth");
    },
    hit: (x, y) => noise(0.05, 2500, 600, 0.25 * near(x, y), "bandpass"),          // bullet hits a wall
    bleed: (x, y) => { if (!play("hit_marker", 0.9 * near(x, y))) SFX.hit(x, y); },  // bullet hits a player
    hurt: () => { if (!play("player_hit", 0.5)) tone(260, 110, 0.14, 0.22, "square"); },
    pickup: () => {
      if (play("weapon_pickup", 1)) return;
      tone(520, 520, 0.07, 0.18, "square"); tone(780, 780, 0.1, 0.18, "square", 0.07);
    },
    death: (mine) => { if (!play("player_death", mine ? 0.7 : 0.4)) tone(320, 50, 0.5, mine ? 0.25 : 0.12, "sawtooth"); },
    kill: () => { play("kill_confirm", 1); },
    respawn: () => { play("respawn", 1); },
    step: (x, y) => { play("footstep_metal", 0.6 * near(x, y), 0.92 + Math.random() * 0.16); },
    land: (x, y) => { play("land", 0.4 * near(x, y)); },
    win: () => { if (!play("victory", 0.9)) [523, 659, 784, 1046].forEach((f, i) => tone(f, f, 0.18, 0.22, "square", i * 0.14)); },
    lose: () => { if (!play("defeat", 0.9)) [392, 330, 262].forEach((f, i) => tone(f, f, 0.22, 0.2, "triangle", i * 0.18)); },
  };

  // ------------------------------------------------------------ input
  const kb = { l: false, r: false, u: false, d: false };
  const stick = { x: 0, y: 0 };
  const aimT = { active: false, ang: 0, fire: false };
  const mouse = { x: 0, y: 0, have: false, down: false };
  const KEYMAP = {
    ArrowLeft: "l", KeyA: "l", ArrowRight: "r", KeyD: "r",
    ArrowUp: "u", KeyW: "u", Space: "u", ArrowDown: "d", KeyS: "d",
  };
  function onKey(e, down) {
    if (!$("game").classList.contains("active")) return;
    if (down && !e.repeat && (e.code === "KeyQ" || e.code === "KeyR")) { socket.emit(e.code === "KeyQ" ? "swap" : "reload"); return; }
    const k = KEYMAP[e.code];
    if (!k) return;
    e.preventDefault();
    kb[k] = down;
  }
  window.addEventListener("keydown", (e) => onKey(e, true));
  window.addEventListener("keyup", (e) => onKey(e, false));
  window.addEventListener("blur", () => { kb.l = kb.r = kb.u = kb.d = false; mouse.down = false; });

  for (const [id, ev] of [["swapBtn", "swap"], ["reloadBtn", "reload"]]) {
    $(id).addEventListener("pointerdown", (e) => { e.preventDefault(); e.stopPropagation(); socket.emit(ev); });
  }

  const canvas = $("canvas");
  canvas.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse") return;
    mouse.have = true; mouse.x = e.clientX; mouse.y = e.clientY;
  });
  canvas.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse") return;
    mouse.have = true; mouse.x = e.clientX; mouse.y = e.clientY; mouse.down = true;
  });
  window.addEventListener("pointerup", (e) => { if (e.pointerType === "mouse") mouse.down = false; });
  document.addEventListener("contextmenu", (e) => e.preventDefault());

  // floating thumbsticks (left = fly, right = aim + auto-fire)
  function makePad(zoneId, baseId, knobId, R, home, onMove, onEnd) {
    const zone = $(zoneId), base = $(baseId), knob = $(knobId);
    let pid = null, ox = 0, oy = 0;
    const place = (x, y) => { base.style.left = x + "px"; base.style.top = y + "px"; };
    function reset() {
      pid = null; knob.style.transform = ""; base.classList.remove("on");
      const h = home(); place(h.x, h.y);
      onEnd();
    }
    function move(e) {
      let dx = e.clientX - ox, dy = e.clientY - oy;
      const len = Math.hypot(dx, dy), Rk = R * padK;      // stick size setting scales the travel too
      if (len > Rk) { dx = dx / len * Rk; dy = dy / len * Rk; }
      knob.style.transform = "translate(" + dx / padK + "px, " + dy / padK + "px)";
      onMove(dx / Rk, dy / Rk, len / padK);
    }
    zone.addEventListener("pointerdown", (e) => {
      if (pid !== null) return;
      pid = e.pointerId; zone.setPointerCapture(pid);
      ox = e.clientX; oy = e.clientY; place(ox, oy);
      base.classList.add("on"); move(e);
    });
    zone.addEventListener("pointermove", (e) => { if (e.pointerId === pid) move(e); });
    for (const ev of ["pointerup", "pointercancel"]) zone.addEventListener(ev, (e) => { if (e.pointerId === pid) reset(); });
    return reset;
  }
  const resetL = makePad("stickZone", "stickBase", "knob", 52,
    () => ({ x: document.body.classList.contains("lefty") ? window.innerWidth - 120 : 120, y: window.innerHeight - 100 }),
    (nx, ny) => { stick.x = Math.abs(nx) > 0.2 ? nx : 0; stick.y = Math.abs(ny) > 0.2 ? ny : 0; },
    () => { stick.x = stick.y = 0; });
  const resetR = makePad("aimZone", "aimBase", "aimKnob", 52,
    () => ({ x: document.body.classList.contains("lefty") ? 120 : window.innerWidth - 120, y: window.innerHeight - 100 }),
    (nx, ny, len) => { aimT.active = true; aimT.ang = Math.atan2(ny, nx); aimT.fire = len > fireThr; },
    () => { aimT.active = false; aimT.fire = false; });
  function resetPads() { resetL(); resetR(); }
  window.addEventListener("resize", () => { if ($("game").classList.contains("active")) resetPads(); });

  function computeInput() {
    const mx = (kb.r ? 1 : 0) - (kb.l ? 1 : 0) || stick.x;
    const my = (kb.d ? 1 : 0) - (kb.u ? 1 : 0) || stick.y;
    let fire = false;
    if (aimT.active) { localAim = aimT.ang; fire = aimT.fire; }
    else if (mouse.have && myPos) {
      const d = dprNow();
      const sx = (myPos.x - cam.x) * view.sc / d + window.innerWidth / 2;
      const sy = (myPos.y - cam.y) * view.sc / d + window.innerHeight / 2;
      localAim = Math.atan2(mouse.y - sy, mouse.x - sx);
      fire = mouse.down;
    } else if (Math.abs(mx) > 0.2 && Math.sign(Math.cos(localAim)) !== Math.sign(mx)) {
      localAim = mx < 0 ? Math.PI : 0;   // not aiming: face where you're flying
    }
    return { mx: Math.round(mx * 10) / 10, my: Math.round(my * 10) / 10, aim: Math.round(localAim * 50) / 50, fire };
  }
  let lastKey = "", lastSend = 0;
  setInterval(() => {
    if (!socket.connected || !$("game").classList.contains("active")) return;
    const i = computeInput();
    const key = i.mx + "," + i.my + "," + i.aim + "," + i.fire;
    const now = performance.now();
    if (key !== lastKey || now - lastSend > 250) {
      lastKey = key; lastSend = now;
      socket.emit("input", i);
    }
  }, 33);

  // ------------------------------------------------------------ images
  function loadImg(src) {
    return new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
  }
  const skinImgs = [];
  let explImg = null;
  const handImgs = [], flashImgs = [];
  const skinHand = {};          // skin id -> in-hand sprite (false = loading or missing); loaded the first time someone wears it
  function skinHandImg(k) {
    if (!(k in skinHand)) { skinHand[k] = false; loadImg("/static/img/wpn/skins/hand_" + k + ".png?v=1").then((im) => { skinHand[k] = im || false; }); }
    return skinHand[k] || null;
  }
  for (let i = 0; i < W_HAND.length; i++) loadImg("/static/img/wpn/hand_" + W_HAND[i] + ".png?v=1").then((im) => { handImgs[i] = im; });
  for (let i = 0; i < 3; i++) loadImg("/static/img/wpn/flash_" + i + ".png?v=1").then((im) => { flashImgs[i] = im; });
  for (let i = 0; i < SKIN_N; i++) loadImg("/static/img/skin" + i + ".png?v=4").then((im) => { skinImgs[i] = im; });
  loadImg("/static/img/explosion.png?v=3").then((im) => { explImg = im; });
  const SK = (window.SKINS && window.SKINS.counts) || {};

  // Laboratory art (static/img/lab). Anything that fails to load falls back to the drawn tiles / shapes.
  const LAB = {};
  const LAB_FILES = ["floor_plain", "floor_hazard", "wall_light", "wall_cable", "wall_warn", "plat_long", "door_open",
    "tank_green", "tank_blue", "tank_small", "term_rack", "term_desk", "term_kiosk", "term_arcade", "term_a",
    "light_cyan", "light_amber", "light_red", "pipe_long", "pipe_bundle", "pk_shotgun", "pk_rocket", "pk_health"];
  Promise.all(LAB_FILES.map((n) => loadImg("/static/img/lab/" + n + ".png?v=8").then((im) => { if (im) LAB[n] = im; })))
    .then(() => { if (tiles && !(world && (world.art === "street" || world.art === "stairs"))) useLabTiles(); });

  // Street art (static/img/street): only the sprites the map's props list asks for
  const ART = {}, artAsked = new Set();
  function loadArt(w) {
    if (!w || w.art !== "street") return;
    for (const pr of (w.props || [])) {
      const n = pr[0];
      if (artAsked.has(n)) continue;
      artAsked.add(n);
      loadImg("/static/img/street/" + n + ".png?v=3").then((im) => { if (im) ART[n] = im; });
    }
  }

  // ------------------------------------------------------------ map art (drawn in code, cached as tiles)
  const T = 40;
  let tiles = null;
  const hash = (c, r) => (((c * 73856093) ^ (r * 19349663)) >>> 0);
  function mk(fn) {
    const c = document.createElement("canvas"); c.width = c.height = T;
    const g = c.getContext("2d"); fn(g); return c;
  }
  function buildTiles() {
    const rivets = (g, col) => { g.fillStyle = col; for (const [x, y] of [[3, 3], [34, 3], [3, 34], [34, 34]]) g.fillRect(x, y, 3, 3); };
    tiles = { steel: [], top: null, mid: null, crate: null, grate: null, bg: [], pipe: null, lamp: null };
    for (let v = 0; v < 3; v++) {
      tiles.steel.push(mk((g) => {
        g.fillStyle = "#39445a"; g.fillRect(0, 0, T, T);
        g.fillStyle = "#4b586f"; g.fillRect(0, 0, T, 2); g.fillRect(0, 0, 2, T);
        g.fillStyle = "#262f40"; g.fillRect(0, T - 2, T, 2); g.fillRect(T - 2, 0, 2, T);
        rivets(g, "#6c7a92");
        g.fillStyle = "#2f394d";
        if (v === 1) g.fillRect(19, 6, 2, 28);
        if (v === 2) g.fillRect(6, 19, 28, 2);
      }));
    }
    const concrete = (g) => {
      g.fillStyle = "#505b6c"; g.fillRect(0, 0, T, T);
      g.fillStyle = "#434d5c"; g.fillRect(0, 19, T, 2);
      g.fillStyle = "#5d6a7d"; for (let i = 0; i < 6; i++) g.fillRect((i * 17 + 5) % 36, (i * 11 + 4) % 34, 3, 2);
      g.fillStyle = "#394252"; g.fillRect(0, T - 3, T, 3);
    };
    tiles.mid = mk(concrete);
    tiles.top = mk((g) => {
      concrete(g);
      g.fillStyle = "#1d2330"; g.fillRect(0, 0, T, 6);
      g.fillStyle = "#e0a526";
      for (let x = 0; x < T; x += 10) {
        g.beginPath(); g.moveTo(x, 0); g.lineTo(x + 5, 0); g.lineTo(x + 1, 6); g.lineTo(x - 4, 6); g.fill();
      }
      g.fillStyle = "#8794a8"; g.fillRect(0, 6, T, 2);
    });
    tiles.crate = mk((g) => {
      g.fillStyle = "#8a6a3b"; g.fillRect(0, 0, T, T);
      g.fillStyle = "#6d522b";
      for (let y = 0; y < T; y += 10) g.fillRect(0, y + 8, T, 2);
      g.strokeStyle = "#4a3718"; g.lineWidth = 3; g.strokeRect(1.5, 1.5, T - 3, T - 3);
      g.lineWidth = 2; g.beginPath(); g.moveTo(4, 4); g.lineTo(T - 4, T - 4); g.moveTo(T - 4, 4); g.lineTo(4, T - 4); g.stroke();
    });
    tiles.grate = mk((g) => {
      g.fillStyle = "#8fa0b8"; g.fillRect(0, 0, T, 3);
      g.fillStyle = "#5a6678"; g.fillRect(0, 3, T, 7);
      g.fillStyle = "#262f40"; for (let x = 3; x < T; x += 6) g.fillRect(x, 5, 3, 3);
    });
    for (let v = 0; v < 3; v++) {
      tiles.bg.push(mk((g) => {
        g.fillStyle = v === 0 ? "#1b2332" : v === 1 ? "#1e2736" : "#19202e"; g.fillRect(0, 0, T, T);
        g.fillStyle = "#232d40"; g.fillRect(0, 0, T, 1); g.fillRect(0, 0, 1, T);
        if (v === 2) { g.fillStyle = "#212b3d"; g.fillRect(8, 8, 24, 24); }
      }));
    }
    tiles.pipe = mk((g) => {
      g.fillStyle = "#1b2332"; g.fillRect(0, 0, T, T);
      g.fillStyle = "#34445e"; g.fillRect(0, 14, T, 12);
      g.fillStyle = "#4d6283"; g.fillRect(0, 15, T, 3);
      g.fillStyle = "#26334a"; g.fillRect(0, 24, T, 2);
      g.fillStyle = "#6d7f9c"; g.fillRect(18, 12, 4, 16);
    });
    tiles.lamp = mk((g) => {
      g.fillStyle = "#1b2332"; g.fillRect(0, 0, T, T);
      const gr = g.createRadialGradient(20, 6, 1, 20, 6, 30);
      gr.addColorStop(0, "rgba(255,212,121,.45)"); gr.addColorStop(1, "rgba(255,212,121,0)");
      g.fillStyle = gr; g.fillRect(0, 0, T, T);
      g.fillStyle = "#ffd479"; g.fillRect(14, 2, 12, 4);
      g.fillStyle = "#3a4458"; g.fillRect(12, 0, 16, 2);
    });
    if (world && world.art === "street") useStreetTiles(); else if (world && world.art === "stairs") useStairsTiles(); else useLabTiles();
  }

  // Street theme: asphalt road on top, wet brick sewer underneath (all drawn in code)
  function useStreetTiles() {
    const bricks = (g, base, line, hi) => {
      g.fillStyle = base; g.fillRect(0, 0, T, T);
      g.fillStyle = line;
      for (let y = 0; y < T; y += 10) g.fillRect(0, y, T, 1);
      for (let y = 0; y < T; y += 10) { const off = (y / 10) % 2 ? 0 : 10; for (let x = off; x < T; x += 20) g.fillRect(x, y, 1, 10); }
      if (hi) { g.fillStyle = hi; for (let i = 0; i < 5; i++) g.fillRect((i * 13 + 6) % 34, (i * 9 + 3) % 36, 4, 2); }
    };
    tiles.steel = [0, 1, 2].map((v) => mk((g) => {                         // boundary walls: concrete block
      bricks(g, v === 1 ? "#4a4a50" : "#44444b", "#2b2b31", "#5d5d65");
      g.fillStyle = "#585860"; g.fillRect(0, 0, 2, T);
    }));
    tiles.mid = mk((g) => bricks(g, "#3b4352", "#2a313e", "#4a5365"));      // sewer wall block
    tiles.top = mk((g) => { bricks(g, "#3b4352", "#2a313e", "#4a5365"); g.fillStyle = "#6a7488"; g.fillRect(0, 0, T, 3); g.fillStyle = "#2f7f8a"; g.fillRect(0, 3, T, 2); });
    tiles.roadMid = mk((g) => {                                              // under the road: packed earth + stone
      g.fillStyle = "#2c2a2e"; g.fillRect(0, 0, T, T);
      g.fillStyle = "#38353a"; for (let i = 0; i < 7; i++) g.fillRect((i * 17 + 3) % 34, (i * 11 + 5) % 34, 5, 3);
      g.fillStyle = "#222024"; g.fillRect(0, T - 3, T, 3);
    });
    tiles.road = [0, 1, 2, 3].map((v) => mk((g) => {                         // road surface, lane dashes every other tile
      g.fillStyle = "#2c2a2e"; g.fillRect(0, 0, T, T);
      g.fillStyle = "#b9b2a2"; g.fillRect(0, 0, T, 5);                       // pavement edge you stand on
      g.fillStyle = "#8d877a"; g.fillRect(0, 5, T, 2);
      g.fillStyle = "#3c3a40"; g.fillRect(0, 7, T, 12);
      g.fillStyle = "#47444b"; for (let i = 0; i < 4; i++) g.fillRect((i * 19 + v * 7) % 34, 9 + (i * 5) % 8, 5, 2);
      if (v < 2) { g.fillStyle = "#e6b52a"; g.fillRect(v ? 0 : 8, 25, v ? 32 : 32, 3); }
      g.fillStyle = "#38353a"; for (let i = 0; i < 5; i++) g.fillRect((i * 13 + 5) % 34, 30 + (i * 3) % 6, 5, 3);
    }));
    tiles.bg = [0, 1, 2].map((v) => mk((g) => bricks(g, v === 0 ? "#171e29" : v === 1 ? "#19212d" : "#151b26", "#1d2633", v === 2 ? "#202b3a" : null)));
  }

  // Staircase theme: plain concrete building (all drawn in code)
  function useStairsTiles() {
    const wall = (g, base, line) => {
      g.fillStyle = base; g.fillRect(0, 0, T, T);
      g.fillStyle = line; g.fillRect(0, 0, T, 1); g.fillRect(0, 0, 1, T);
    };
    tiles.steel = [0, 1, 2].map((v) => mk((g) => {                         // outer walls and roof: dark block
      wall(g, v === 1 ? "#3a3f4d" : "#353a48", "#2a2e3a");
      g.fillStyle = "#454b5c"; g.fillRect(0, T - 3, T, 3);
      if (v === 2) { g.fillStyle = "#2f3441"; g.fillRect(8, 8, 24, 24); }
    }));
    tiles.mid = mk((g) => { wall(g, "#59606f", "#4a505e"); g.fillStyle = "#4a505e"; g.fillRect(0, 19, T, 1); });
    tiles.top = mk((g) => {                                                // a surface you stand on: light lip on top
      wall(g, "#59606f", "#4a505e");
      g.fillStyle = "#a9b0bf"; g.fillRect(0, 0, T, 4);
      g.fillStyle = "#7f8696"; g.fillRect(0, 4, T, 2);
      g.fillStyle = "#4a505e"; g.fillRect(0, 22, T, 1);
    });
    for (let v = 0; v < 3; v++) {                                          // back wall: soft plaster, faint panel lines
      tiles.bg[v] = mk((g) => {
        g.fillStyle = v === 0 ? "#252b3a" : v === 1 ? "#272d3d" : "#232938"; g.fillRect(0, 0, T, T);
        g.fillStyle = "#2c3345"; g.fillRect(0, 0, T, 1); g.fillRect(0, 0, 1, T);
      });
    }
  }

  // swap the drawn tiles for the Laboratory sprites (only the ones that loaded)
  function useLabTiles() {
    const panel = (img, flipY) => mk((g) => {
      g.fillStyle = "#1b2332"; g.fillRect(0, 0, T, T);
      if (flipY) { g.translate(0, T); g.scale(1, -1); }
      g.drawImage(img, 0, 0, T, T);
    });
    if (LAB.wall_light && LAB.wall_cable) tiles.steel = [panel(LAB.wall_light), panel(LAB.wall_cable), panel(LAB.wall_cable)];
    if (LAB.floor_plain) tiles.mid = panel(LAB.floor_plain);
    if (LAB.floor_hazard) tiles.top = panel(LAB.floor_hazard, true);      // stripes on the walking surface
    if (LAB.wall_warn) tiles.crate = panel(LAB.wall_warn);
    if (LAB.plat_long) {                                                   // catwalk: one 2-tile segment = two halves
      const half = (k) => mk((g) => { g.drawImage(LAB.plat_long, 0, 0, LAB.plat_long.width, LAB.plat_long.height, -k * T, 0, 2 * T, 20); });
      tiles.grateSeg = [half(0), half(1)];
    }
  }

  // distant skyline (parallax)
  const skyline = [[], []];
  (function () {
    let s = 7;
    const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let layer = 0; layer < 2; layer++) {
      let x = -200;
      while (x < 3600) {
        const w = 60 + rnd() * 120, h = 60 + rnd() * (layer ? 170 : 120);
        skyline[layer].push([x, w, h, rnd() < 0.25 ? 1 : 0]);
        x += w + 10 + rnd() * 30;
      }
    }
  })();

  // ------------------------------------------------------------ drawing
  const ctx = canvas.getContext("2d");

  function drawSky(cw, ch, sc) {
    const g = ctx.createLinearGradient(0, 0, 0, ch);
    const sk = world.sky || ["#0b1226", "#2b2b4e", "#9a5646"];
    g.addColorStop(0, sk[0]); g.addColorStop(0.55, sk[1]); g.addColorStop(1, sk[2]);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch);
    const layers = world.skyline
      ? [[0.25, world.skyline[0], world.skyline_base[0]], [0.5, world.skyline[1], world.skyline_base[1]]]
      : [[0.25, "#1f2540", 520], [0.5, "#161b33", 470]];
    for (let l = 0; l < 2; l++) {
      const par = layers[l][0], col = layers[l][1], base = layers[l][2];
      ctx.setTransform(sc, 0, 0, sc, cw / 2 - cam.x * par * sc, ch / 2 - cam.y * par * sc);
      ctx.fillStyle = col;
      for (const b of skyline[l]) {
        ctx.fillRect(b[0], base - b[2], b[1], b[2] + 2000);
        if (b[3]) ctx.fillRect(b[0] + b[1] * 0.4, base - b[2] - 70, 14, 72);
      }
    }
  }

  // pass 0 = background wall, pass 1 = solid blocks and catwalks (props are drawn between the two)
  function drawTiles(x0, y0, x1, y1, pass) {
    const grid = world.grid, street = world.art === "street";
    const c0 = clamp(Math.floor(x0 / T), 0, world.cols - 1), c1 = clamp(Math.floor(x1 / T), 0, world.cols - 1);
    const r0 = clamp(Math.floor(y0 / T), 0, world.rows - 1), r1 = clamp(Math.floor(y1 / T), 0, world.rows - 1);
    for (let r = r0; r <= r1; r++) {
      const row = grid[r];
      for (let c = c0; c <= c1; c++) {
        const ch = row[c], x = c * T, y = r * T;
        const solidCh = ch === "#" || ch === "S" || ch === "C" || ch === "B";
        if (pass === 0) {
          if (street) {                                          // only the underground has a back wall; above the road is sky
            if (!solidCh && r >= world.street_row && c > 0 && c < world.cols - 1) ctx.drawImage(tiles.bg[hash(c, r) % 3], x, y);
            continue;
          }
          if (!solidCh && c > 0 && c < world.cols - 1 && r >= 1) {
            let t = tiles.bg[hash(c, r) % 3];
            if (world.art === "stairs") t = tiles.bg[hash(c, r) % 3];
            else if (r % 6 === 2) t = tiles.pipe;
            else if (c % 9 === 4 && r % 7 === 1) t = tiles.lamp;
            ctx.drawImage(t, x, y);
          }
          continue;
        }
        if (ch === "B" || ch === "-") continue;                  // building bodies and sprite platforms: the props are the art
        if (ch === "#") { if (!(street && r === 0)) ctx.drawImage(tiles.steel[hash(c, r) % 3], x, y); continue; }
        if (ch === "S") {
          const above = r > 0 ? grid[r - 1][c] : "#";
          const covered = above === "#" || above === "S" || above === "C" || above === "B";
          if (street && (r === world.street_row || r === world.street_row + 1)) {
            ctx.drawImage(covered ? tiles.roadMid : tiles.road[c % 4], x, y);
          } else ctx.drawImage(covered ? tiles.mid : tiles.top, x, y);
          continue;
        }
        if (ch === "C") { ctx.drawImage(tiles.crate, x, y); continue; }
        if (ch === "=") {
          if (tiles.grateSeg) {
            let k = 0;
            while (c - k - 1 >= 0 && row[c - k - 1] === "=") k++;
            ctx.drawImage(tiles.grateSeg[k % 2], x, y);
          } else ctx.drawImage(tiles.grate, x, y);
        }
      }
    }
  }

  // decoration: tanks, terminals, pipes, lights (no collision)
  function drawProps() {
    if (!world.props) return;
    const street = world.art === "street";
    ctx.globalAlpha = street ? 1 : 0.9;
    if (street) ctx.imageSmoothingEnabled = true;           // painted sprites look better smoothed
    for (const [name, col, row, sc, anchor] of world.props) {
      const im = street ? ART[name] : LAB[name];
      if (!im) continue;
      const w = im.width * sc, h = im.height * sc;
      ctx.drawImage(im, col * T + T / 2 - w / 2, anchor === "t" ? row * T : row * T - h, w, h);
    }
    ctx.imageSmoothingEnabled = false;
    ctx.globalAlpha = 1;
    for (const [c, r0, r1, w] of (world.ladders || [])) {      // ladders: two rails and rungs
      const x0 = c * T + 10, x1 = (c + w) * T - 10;
      ctx.fillStyle = "#8a6a3b"; ctx.fillRect(x0, r0 * T, 4, (r1 - r0) * T); ctx.fillRect(x1 - 4, r0 * T, 4, (r1 - r0) * T);
      ctx.fillStyle = "#b08a4e";
      for (let y = r0 * T + 6; y < r1 * T; y += 14) ctx.fillRect(x0, y, x1 - x0, 3);
    }
    for (const [c0, c1, row] of (world.rails || [])) {         // railing along the top corridor
      const y = row * T;
      ctx.fillStyle = "#8f98ab";
      for (let x = c0 * T; x <= (c1 + 1) * T; x += 28) ctx.fillRect(x, y - 26, 3, 26);
      ctx.fillRect(c0 * T, y - 28, (c1 + 1 - c0) * T, 3); ctx.fillRect(c0 * T, y - 14, (c1 + 1 - c0) * T, 2);
    }
    for (const [bx0, bx1, by0, by1] of (world.beams || [])) {  // daylight falling down the manholes
      const gr = ctx.createLinearGradient(0, by0, 0, by1);
      gr.addColorStop(0, "rgba(255,214,150,.32)"); gr.addColorStop(1, "rgba(255,214,150,0)");
      ctx.fillStyle = gr;
      ctx.beginPath(); ctx.moveTo(bx0, by0); ctx.lineTo(bx1, by0); ctx.lineTo(bx1 + 50, by1); ctx.lineTo(bx0 - 50, by1); ctx.closePath(); ctx.fill();
    }
  }

  function drawPickups(now) {
    if (!latest) return;
    world.pickups.forEach((pk, i) => {
      if (!latest.k[i]) return;
      const kind = pk[0], x = pk[1], y = pk[2] + Math.sin(now / 280 + i) * 3;
      const col = kind === "health" ? "#ff6b6b" : kind === 1 ? "#ffb347" : "#7ee081";
      const gr = ctx.createRadialGradient(x, y, 2, x, y, 30);
      gr.addColorStop(0, col + "88"); gr.addColorStop(1, col + "00");
      ctx.fillStyle = gr; ctx.fillRect(x - 30, y - 30, 60, 60);
      const spr = kind === "health" ? LAB.pk_health : kind === 1 ? LAB.pk_shotgun : LAB.pk_rocket;
      if (spr) {
        const sc = kind === "health" ? 0.6 : kind === 1 ? 0.27 : 0.24;
        ctx.drawImage(spr, x - spr.width * sc / 2, y - spr.height * sc / 2, spr.width * sc, spr.height * sc);
      } else if (kind === "health") {
        ctx.fillStyle = "#f3ecdc"; ctx.fillRect(x - 11, y - 11, 22, 22);
        ctx.fillStyle = "#d24a43"; ctx.fillRect(x - 3, y - 8, 6, 16); ctx.fillRect(x - 8, y - 3, 16, 6);
      } else if (kind === 1) {
        ctx.fillStyle = "#3a2a1a"; ctx.fillRect(x - 16, y - 3, 32, 6);
        ctx.fillStyle = "#8a5a2b"; ctx.fillRect(x - 16, y - 5, 12, 10);
        ctx.fillStyle = "#c9c9c9"; ctx.fillRect(x + 2, y - 4, 14, 3);
      } else {
        ctx.fillStyle = "#4b5f3a"; ctx.fillRect(x - 17, y - 5, 28, 10);
        ctx.fillStyle = "#d24a43"; ctx.beginPath(); ctx.moveTo(x + 11, y - 5); ctx.lineTo(x + 19, y); ctx.lineTo(x + 11, y + 5); ctx.fill();
        ctx.fillStyle = "#2c3a22"; ctx.fillRect(x - 17, y - 2, 6, 4);
      }
    });
  }

  // ---- jetpack thrust: one looping voice per flying player; the longer you hold thrust the higher it climbs
  function stopJet(id) {
    const j = jets.get(id); if (!j) return;
    try { j.s.stop(); j.g.disconnect(); } catch (e) {}
    jets.delete(id);
  }
  function stopJets() { for (const id of Array.from(jets.keys())) stopJet(id); }
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopJets(); });
  function updateJets(players, dt) {
    const a = actx;
    if (!a || a.state !== "running" || !SND.jet_loop) return;
    const t = a.currentTime, seen = new Set();
    for (const p of players) {
      const id = p[0], on = !!(p[8] & 2) && !(p[8] & 4);
      let j = jets.get(id);
      if (!j) {
        if (!on) continue;
        const s = a.createBufferSource(); s.buffer = SND.jet_loop; s.loop = true;
        const g = a.createGain(); g.gain.value = 0;
        s.connect(g); g.connect(a.destination); s.start();
        j = { s, g, heat: 0, idle: 0 }; jets.set(id, j);
      }
      seen.add(id);
      j.heat = on ? Math.min(1, j.heat + dt / 1.3) : Math.max(0, j.heat - dt * 1.6);
      j.idle = on ? 0 : j.idle + dt;
      const v = id === me ? 1 : near(p[1] + world.pw / 2, p[2]);
      const target = on && !muted ? (0.26 + 0.2 * j.heat) * v * volume * sfxVol : 0;
      j.g.gain.setTargetAtTime(target, t, on ? 0.04 : 0.12);
      j.s.playbackRate.setTargetAtTime(0.82 + 0.62 * j.heat, t, 0.08);
      if (j.idle > 1.2) stopJet(id);
    }
    for (const id of Array.from(jets.keys())) if (!seen.has(id)) stopJet(id);
  }

  // ---- jetpack visuals: embers, a lingering smoke trail, heat haze, and dust kicked up when thrusting off the ground
  function jetFx(p, st, facing, heat) {
    const cx = p[1] + world.pw / 2, feet = p[2] + world.ph;
    const nx = cx - facing * 19.5 * SPR, ny = feet - 27 * SPR;
    st.tTrail = (st.tTrail || 0) + fdtCur; st.tEmber = (st.tEmber || 0) + fdtCur; st.tHaze = (st.tHaze || 0) + fdtCur; st.tDust = (st.tDust || 0) + fdtCur;
    const r = () => Math.random() - 0.5;
    while (st.tTrail > 0.034) { st.tTrail -= 0.034; addPart(nx + r() * 5, ny + 12, -facing * 8 + r() * 26, 50 + Math.random() * 50, 1.1 + Math.random() * 0.5, 7, "#8d96a4", -55, false, 5); }
    while (st.tEmber > 0.045) { st.tEmber -= 0.045; addPart(nx + r() * 4, ny + 8, r() * 90, 110 + Math.random() * 120, 0.4 + Math.random() * 0.35, 2.4, "#ffb347", 720, false, 2); }
    while (st.tHaze > 0.07) { st.tHaze -= 0.07; addPart(nx + r() * 6, ny + 22, r() * 14, 10, 0.5, 15 + heat * 6, "#ffd9a0", -110, false, 4); }
    if (p[8] & 1) {
      while (st.tDust > 0.04) {
        st.tDust -= 0.04;
        for (const d of [-1, 1]) addPart(cx + d * 6, feet - 2, d * (70 + Math.random() * 130), -(6 + Math.random() * 26), 0.45 + Math.random() * 0.4, 8 + Math.random() * 6, "#b8a98f", 10, false, 3);
      }
    }
  }
  function landDust(x, y, vy) {
    const n = Math.min(14, 6 + Math.floor(vy / 90));
    for (let i = 0; i < n; i++) {
      const d = i % 2 ? 1 : -1;
      addPart(x + d * 4, y - 2, d * (40 + Math.random() * 130), -(8 + Math.random() * 30), 0.5 + Math.random() * 0.4, 8 + Math.random() * 6, "#b8a98f", 20, false, 3);
    }
  }

  function drawJetpack(thrust, heat) {
    // the jetpack body is hidden until there is a better sprite; only the thrust flame remains
    if (!thrust) return;
    const k = 0.8 + 0.45 * (heat || 0), l = (20 + Math.random() * 14) * k, j = (Math.random() - 0.5) * 3;
    const tri = (x0, x1, len, col) => { ctx.fillStyle = col; ctx.beginPath(); ctx.moveTo(x0, -27); ctx.lineTo(x1, -27); ctx.lineTo(-19.5 + j, -27 + len); ctx.fill(); };
    tri(-26.5, -12.5, l * 1.12, "#ff5a12");
    tri(-25, -14, l * 0.82, "#ff9a2a");
    tri(-23.2, -15.8, l * 0.55, "#ffe08a");
    tri(-21.6, -17.4, l * 0.3, "#fffbe8");
    ctx.fillStyle = "#8fc0ff"; ctx.beginPath(); ctx.moveTo(-22, -27); ctx.lineTo(-17, -27); ctx.lineTo(-19.5, -27 + l * 0.2); ctx.fill();
  }

  function drawSoldier(p, now) {
    const id = p[0], x = p[1], y = p[2], vx = p[3], flags = p[8];
    const st = pst.get(id) || { deadAt: 0, hurtAt: 0, hurtUntil: 0 };
    const dead = !!(flags & 4);
    if (dead && now - st.deadAt > 1900) return;
    const aim = id === me && !dead ? localAim : p[5];
    const facing = Math.cos(aim) >= 0 ? 1 : -1;
    const sid = skinOf(id);
    const cnt = SK[sid] || [1, 2, 2, 1, 4, 1];
    const img = skinImgs[sid];
    const ground = !!(flags & 1), thrust = !!(flags & 2), firing = !!(flags & 8);

    let row = 0, idx = 0, whole = false;
    if (dead) { row = 4; idx = Math.min(cnt[4] - 1, Math.floor((now - st.deadAt) / 110)); whole = true; }
    else if (now < st.hurtUntil) { row = 3; idx = Math.min(cnt[3] - 1, Math.floor((now - st.hurtAt) / 70)); whole = true; }
    else if (!ground) { row = 5; idx = 0; }
    else if (Math.abs(vx) > 20) { row = 1; idx = Math.floor(now / 140) % cnt[1]; }
    else { row = 0; idx = Math.floor(now / 140) % cnt[0]; }

    if (thrust && !dead) st.jt = Math.min(1.3, (st.jt || 0) + fdtCur); else st.jt = 0;
    const heat = Math.min(1, (st.jt || 0) / 1.3);
    ctx.save();
    if (flags & 16) ctx.globalAlpha = Math.floor(now / 90) % 2 ? 0.4 : 0.85;
    ctx.translate(Math.round(x + world.pw / 2), Math.round(y + world.ph));
    ctx.scale(facing * SPR, SPR);
    if (!dead) drawJetpack(thrust, heat);
    if (!img) {
      ctx.fillStyle = colorOf(id); ctx.fillRect(-16, -64, 32, 64);
    } else if (whole) {
      ctx.drawImage(img, idx * 128, row * 128, 128, 128, -64, -127, 128, 128);
    } else {
      let am = facing === 1 ? aim : Math.PI - aim;
      am = clamp(Math.atan2(Math.sin(am), Math.cos(am)), -AIM_LIMIT, AIM_LIMIT);
      ctx.drawImage(img, idx * 128, row * 128 + SPLIT, 128, 128 - SPLIT, -64, SPLIT - 127, 128, 128 - SPLIT);
      ctx.save();
      ctx.translate(0, PIV - 127);
      ctx.rotate(am + TIP);
      ctx.drawImage(img, idx * 128, row * 128, 128, SPLIT, -64, -PIV, 128, SPLIT);
      const sk = wskinOf(id, p[7]), hw = (sk && skinHandImg(sk)) || handImgs[p[7]], hd = HAND[p[7]];
      if (hw && hd) { const gh = hw.height * hd.len / hw.width; ctx.drawImage(hw, hd.x, hd.y - gh * 0.4, hd.len, gh); }
      ctx.restore();
    }
    ctx.restore();

    if (dead) return;
    if (thrust) {
      jetFx(p, st, facing, heat);
      // warm additive glow around the nozzle
      const gx = x + world.pw / 2 - facing * 19.5 * SPR, gy = y + world.ph - 27 * SPR + 12;
      ctx.save(); ctx.globalCompositeOperation = "lighter";
      const gr = ctx.createRadialGradient(gx, gy, 2, gx, gy, 44 + heat * 14);
      gr.addColorStop(0, "rgba(255,170,70," + (0.5 + 0.15 * heat) + ")"); gr.addColorStop(1, "rgba(255,90,20,0)");
      ctx.fillStyle = gr; ctx.fillRect(gx - 60, gy - 60, 120, 120);
      ctx.restore();
    }
    const cx = x + world.pw / 2;
    ctx.textAlign = "center";
    ctx.font = "700 14px 'Barlow Semi Condensed', sans-serif";
    ctx.lineWidth = 4; ctx.strokeStyle = "rgba(10,18,32,.85)";
    ctx.fillStyle = colorOf(id);
    const nm = nameOf(id);
    ctx.strokeText(nm, cx, y - 14); ctx.fillText(nm, cx, y - 14);
    ctx.fillStyle = "rgba(10,18,32,.8)"; ctx.fillRect(cx - 19, y - 10, 38, 5);
    const hp = p[6];
    ctx.fillStyle = hp > 55 ? "#5fc24a" : hp > 25 ? "#e8b02e" : "#d24a43";
    ctx.fillRect(cx - 18, y - 9, 36 * hp / 100, 3);
    if (id === me) {
      ctx.fillStyle = "#ff7a1a";
      ctx.beginPath(); ctx.moveTo(cx - 6, y - 36); ctx.lineTo(cx + 6, y - 36); ctx.lineTo(cx, y - 28); ctx.fill();
    }
  }

  // ------------------------------------------------------------ effects
  function addPart(x, y, vx, vy, life, size, color, g, smoke, kind) {
    if (parts.length > 650) parts.shift();
    parts.push({ x, y, vx, vy, life, max: life, size, color, g, smoke: !!smoke, kind: kind || 0 });
  }
  function sparks(x, y, n, color, spd) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, s = (0.3 + Math.random()) * spd;
      addPart(x, y, Math.cos(a) * s, Math.sin(a) * s, 0.25 + Math.random() * 0.25, 2 + Math.random() * 2, color, 600, false);
    }
  }

  // ---- final-kill finisher
  function startFinisher(winnerId) {
    if (!lastKill || lastKill.killer !== winnerId) return;   // joined mid-finisher: nothing to replay
    finisher = { r0: performance.now(), killer: lastKill.killer, victim: lastKill.victim };
    const b = $("finalBanner"), who = $("finalWho"), ic = $("finalIcon");
    who.textContent = nameOf(lastKill.killer);
    who.style.color = colorOf(lastKill.killer);
    ic.src = wIconSrc(lastKill.wpn, lastKill.killer);
    b.hidden = false;
    b.classList.remove("go"); void b.offsetWidth; b.classList.add("go");
  }

  function clearFinisher() {
    finisher = null; zoomCur = 1;
    const b = $("finalBanner");
    if (b) b.hidden = true;
  }

  // ---- hit feedback: damage numbers + hit markers (the server sends a "dm" event for every hit)
  function onDamage(victim, attacker, amt, x, y, killed) {
    const dealt = attacker === me && victim !== me, taken = victim === me;
    if (!dealt && !taken) return;
    const f = floaters.find((q) => q.me === taken && q.v === victim && fxMs - q.t0 < 260);   // shotgun pellets / splash merge into one number
    if (f) { f.amt += amt; f.pop = fxMs; f.kill = f.kill || !!killed; }
    else floaters.push({ v: victim, me: taken, amt, x, y, t0: fxMs, pop: fxMs, kill: !!killed, dx: (Math.random() - 0.5) * 36 });
    if (dealt) {
      marks.push({ x, y: y + 24, t0: fxMs, kill: !!killed });
      if (!play("hit_tick", killed ? 0.95 : 0.6, killed ? 0.8 : 0.95 + Math.random() * 0.1)) tone(2600, 2100, 0.04, 0.12, "square");
    }
  }
  function drawFeedback(now) {
    ctx.save();
    for (let i = marks.length - 1; i >= 0; i--) {
      const m = marks[i], age = now - m.t0;
      if (age > 260) { marks.splice(i, 1); continue; }
      const s = m.kill ? 12 : 7.5, g = 1 + (age / 260) * 0.7, r0 = s * 0.45 * g, r1 = s * g;
      ctx.globalAlpha = 1 - age / 260; ctx.lineWidth = m.kill ? 3.2 : 2.4; ctx.lineCap = "round";
      ctx.strokeStyle = m.kill ? "#ff3b30" : "#ffffff";
      ctx.beginPath();
      for (const sx of [-1, 1]) for (const sy of [-1, 1]) { ctx.moveTo(m.x + sx * r0, m.y + sy * r0); ctx.lineTo(m.x + sx * r1, m.y + sy * r1); }
      ctx.stroke();
    }
    ctx.textAlign = "center"; ctx.lineJoin = "round";
    for (let i = floaters.length - 1; i >= 0; i--) {
      const f = floaters[i], age = (now - f.t0) / 1000, life = f.kill ? 1.1 : 0.85;
      if (age > life) { floaters.splice(i, 1); continue; }
      const u = age / life, rise = 48 * (1 - (1 - u) * (1 - u)), pop = Math.max(0, 1 - (now - f.pop) / 150);
      const base = f.me ? 15 : 15 + Math.min(14, f.amt / 6), sz = (f.kill && !f.me ? base * 1.3 : base) * (1 + 0.35 * pop);
      ctx.globalAlpha = Math.min(1, (life - age) / 0.3);
      ctx.font = "800 " + sz.toFixed(1) + "px 'Barlow Semi Condensed', sans-serif";
      ctx.lineWidth = 4; ctx.strokeStyle = "rgba(10,14,24,.9)";
      ctx.fillStyle = f.me ? "#ff5a4f" : f.kill ? "#ffa31f" : "#ffffff";
      const tx = f.x + f.dx * u, ty = f.y - 18 - rise, txt = (f.me ? "-" : "") + Math.round(f.amt);
      ctx.strokeText(txt, tx, ty); ctx.fillText(txt, tx, ty);
    }
    ctx.restore();
  }

  // ---- kill streaks and multi-kills (tracked from the "k" events every player receives)
  const MULTI = { 2: ["DOUBLE STRIKE", 1], 3: ["TRIPLE STRIKE", 2], 4: ["QUAD STRIKE", 3], 5: ["MEGA STRIKE", 3] };
  const SPREE = { 3: ["ON FIRE", 1], 5: ["DOMINATING", 2], 7: ["UNSTOPPABLE", 3], 10: ["LEGENDARY", 3] };
  function feedNote(id, text) {
    const row = document.createElement("div"), a = document.createElement("span"), b = document.createElement("span");
    a.style.color = colorOf(id); a.textContent = nameOf(id); b.textContent = " is " + text;
    row.append(a, b);
    const feed = $("feed"); feed.append(row);
    while (feed.children.length > 4) feed.firstChild.remove();
    setTimeout(() => row.remove(), 4500);
  }
  function showStreak(title, sub, lvl) {
    let el = $("streakBanner");
    if (!el) {
      el = document.createElement("div"); el.id = "streakBanner"; el.className = "streak-banner"; el.hidden = true;
      el.innerHTML = "<b></b><small></small>"; $("game").append(el);
    }
    el.dataset.lvl = String(lvl);
    el.firstChild.textContent = title; el.lastChild.textContent = sub; el.lastChild.hidden = !sub;
    el.hidden = false; el.classList.remove("go"); void el.offsetWidth; el.classList.add("go");
    clearTimeout(streakTimer); streakTimer = setTimeout(() => { el.hidden = true; }, 2300);
    if (!play("streak_" + lvl, 0.85)) [523, 659, 784, 1046].slice(0, lvl + 1).forEach((f, i) => tone(f, f, 0.14, 0.2, "square", i * 0.09));
    if (shakeOn) shake = Math.min(16, shake + 2 + lvl * 2);
  }
  function onKillStreak(killer, victim) {
    const ended = streaks.get(victim) || 0;
    streaks.set(victim, 0);
    if (victim === me) multiN = 0;
    if (killer === victim) return;                             // blew yourself up: no credit
    const n = (streaks.get(killer) || 0) + 1;
    streaks.set(killer, n);
    const sp = SPREE[n] || (n > 10 && n % 5 === 0 ? ["LEGENDARY", 3] : null);
    if (killer !== me) { if (sp) feedNote(killer, sp[0]); return; }
    const now = performance.now();
    multiN = now - multiAt < 4000 ? multiN + 1 : 1; multiAt = now;
    const down = ended >= 3 ? "Ended " + nameOf(victim) + "'s " + ended + "-kill streak" : "";
    let title = "", sub = "", lvl = 0;
    if (multiN >= 2) { const m = MULTI[Math.min(multiN, 5)]; title = m[0]; lvl = m[1]; sub = down || (sp ? sp[0] + " \u00b7 " + n + " in a row" : ""); }
    else if (sp) { title = sp[0]; lvl = sp[1]; sub = down || n + " kills without dying"; }
    else if (down) { title = "SHUTDOWN"; lvl = 1; sub = down; }
    if (title) showStreak(title, sub, lvl);
  }

  function resetFx() {
    floaters.length = 0; marks.length = 0; streaks.clear(); multiN = 0; multiAt = 0;
    lowHp = 0; hbAt = 0; hbPulse = 0; duck = 0; stopJets();
    const el = $("streakBanner"); if (el) el.hidden = true;
  }

  function handleEvent(e) {
    const k = e[0];
    if (k === "sh") {
      flashes.push({ x: e[2], y: e[3], a: e[4], w: e[5], t0: fxMs });
      SFX.shot(e[5], e[2], e[3]);
      if (e[5] === 2) for (let i = 0; i < 4; i++) addPart(e[2], e[3], (Math.random() - 0.5) * 60, (Math.random() - 0.5) * 60, 0.6, 7, "#b8bfcc", -20, true);
    } else if (k === "hit") {
      sparks(e[1], e[2], 6, "#ffd479", 260); SFX.hit(e[1], e[2]);
    } else if (k === "bl") {
      sparks(e[1], e[2], 9, "#c0392b", 220); SFX.bleed(e[1], e[2]);
    } else if (k === "ex") {
      expls.push({ x: e[1], y: e[2], r: e[3], t0: fxMs });
      sparks(e[1], e[2], 18, "#ff9f43", 520);
      for (let i = 0; i < 10; i++) addPart(e[1], e[2], (Math.random() - 0.5) * 240, (Math.random() - 0.5) * 240 - 40, 0.9, 10 + Math.random() * 8, "#6b7280", -30, true);
      SFX.boom(e[1], e[2]);
      if (shakeOn) shake = Math.min(16, shake + Math.max(0, 16 - Math.hypot(e[1] - cam.x, e[2] - cam.y) / 60));
    } else if (k === "dm") {
      onDamage(e[1], e[2], e[3], e[4], e[5], e[6]);
    } else if (k === "k") {
      feedRow(e[1], e[2], e[3]);
      onKillStreak(e[1], e[2]);
      lastKill = { killer: e[1], victim: e[2], wpn: e[3] };
      SFX.death(e[2] === me);
      if (e[1] === me && e[2] !== me) SFX.kill();
    } else if (k === "fin") {
      startFinisher(e[1]);
    } else if (k === "pu") {
      if (e[2] === me) SFX.pickup();
    } else if (k === "sw") {
      if (e[1] === me) SFX.swap();
    } else if (k === "rl") {
      if (e[1] === me) SFX.reload(e[2]);
    }
  }

  function drawEffects(now, dt) {
    for (let i = expls.length - 1; i >= 0; i--) {
      const ex = expls[i], t = now - ex.t0;
      if (t > 520) { expls.splice(i, 1); continue; }
      if (t < 140) {
        const fl = 1 - t / 140, gr = ctx.createRadialGradient(ex.x, ex.y, 4, ex.x, ex.y, ex.r * 0.9);
        gr.addColorStop(0, "rgba(255,240,190," + (0.9 * fl) + ")");
        gr.addColorStop(0.5, "rgba(255,150,50," + (0.45 * fl) + ")");
        gr.addColorStop(1, "rgba(255,120,30,0)");
        ctx.fillStyle = gr; ctx.fillRect(ex.x - ex.r, ex.y - ex.r, ex.r * 2, ex.r * 2);
      }
      if (explImg) {   // frames 0-3 of the sheet are a grenade in flight; the blast is frames 4-8
        const f = 4 + Math.min(4, Math.floor(t / 520 * 5)), s = ex.r * 2.7;
        ctx.drawImage(explImg, f * 128, 0, 128, 128, ex.x - s / 2, ex.y + s * 0.3 - s, s, s);
      }
    }
    for (let i = flashes.length - 1; i >= 0; i--) {
      const f = flashes[i];
      if (now - f.t0 > 70) { flashes.splice(i, 1); continue; }
      const s = f.w === 1 ? 1.5 : f.w === 2 ? 1.9 : 1;
      ctx.save(); ctx.translate(f.x, f.y); ctx.rotate(f.a);
      const fi = flashImgs[W_FLASH[f.w]];
      if (fi) { const fw = FLASH_W[f.w], fh = fi.height * fw / fi.width; ctx.drawImage(fi, -fw * 0.15, -fh / 2, fw, fh); ctx.restore(); continue; }
      ctx.fillStyle = "#ffb12b";
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(12 * s, -7 * s); ctx.lineTo(30 * s, 0); ctx.lineTo(12 * s, 7 * s); ctx.fill();
      ctx.fillStyle = "#fff4c2";
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(8 * s, -3 * s); ctx.lineTo(17 * s, 0); ctx.lineTo(8 * s, 3 * s); ctx.fill();
      ctx.restore();
    }
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      p.life -= dt;
      if (p.life <= 0) { parts.splice(i, 1); continue; }
      if (p.kind >= 3) p.vx *= Math.pow(0.3, dt);          // dust, haze and trail smoke slow down in the air
      p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt;
      const a = p.life / p.max;
      if (p.kind === 2) {                                   // ember: additive glowing dot
        ctx.globalCompositeOperation = "lighter"; ctx.globalAlpha = a; ctx.fillStyle = p.color;
        ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
        ctx.globalCompositeOperation = "source-over";
      } else if (p.kind >= 3) {                             // soft round puffs
        const rr = p.kind === 3 ? p.size * (0.7 + (1 - a) * 1.3) : p.kind === 4 ? p.size * (1 + (1 - a) * 0.8) : p.size * (0.6 + (1 - a) * 2.4);
        ctx.globalAlpha = p.kind === 3 ? a * 0.45 : p.kind === 4 ? a * 0.07 : a * 0.34;
        if (p.kind === 4) ctx.globalCompositeOperation = "lighter";
        ctx.fillStyle = p.color; ctx.beginPath(); ctx.arc(p.x, p.y, rr, 0, 6.2832); ctx.fill();
        if (p.kind === 4) ctx.globalCompositeOperation = "source-over";
      } else {
        ctx.globalAlpha = p.smoke ? a * 0.55 : a;
        ctx.fillStyle = p.color;
        const s = p.smoke ? p.size * (2 - a) : p.size;
        ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
      }
    }
    ctx.globalAlpha = 1;
  }

  // players and bullets drawn INTERP_MS in the past so they line up and move smoothly
  function interpolated(now) {
    if (!snaps.length) return { players: [], bullets: [] };
    const rt = now - INTERP_MS;
    let a = null, b = null;
    for (let i = snaps.length - 1; i >= 0; i--) {
      if (snaps[i].at <= rt) { a = snaps[i]; b = snaps[i + 1] || null; break; }
    }
    if (!a) a = snaps[0];
    const dtS = Math.max(0, (rt - a.at) / 1000);
    const bullets = a.b.map((q) => {
      const sp = BULLET_SPEED[q[0]] || 1000;
      return [q[0], q[1] + Math.cos(q[3]) * sp * dtS, q[2] + Math.sin(q[3]) * sp * dtS, q[3]];
    });
    if (!b || a === b) return { players: a.p, bullets };
    const t = clamp((rt - a.at) / (b.at - a.at), 0, 1);
    const prev = new Map(a.p.map((p) => [p[0], p]));
    const players = b.p.map((q) => {
      const p = prev.get(q[0]);
      if (!p || Math.abs(q[1] - p[1]) > 250 || Math.abs(q[2] - p[2]) > 250) return q;
      const r = q.slice();
      r[1] = p[1] + (q[1] - p[1]) * t;
      r[2] = p[2] + (q[2] - p[2]) * t;
      let da = q[5] - p[5];
      da = Math.atan2(Math.sin(da), Math.cos(da));
      r[5] = p[5] + da * t;
      return r;
    });
    return { players, bullets };
  }

  function drawBullets(bullets) {
    for (const q of bullets) {
      const type = q[0], x = q[1], y = q[2], ang = q[3];
      if (type === 2) {
        ctx.save(); ctx.translate(x, y); ctx.rotate(ang);
        ctx.fillStyle = "#4b5f3a"; ctx.fillRect(-14, -4, 22, 8);
        ctx.fillStyle = "#d24a43"; ctx.beginPath(); ctx.moveTo(8, -4); ctx.lineTo(16, 0); ctx.lineTo(8, 4); ctx.fill();
        ctx.fillStyle = Math.random() < 0.5 ? "#ffd479" : "#ff7a1a";
        ctx.beginPath(); ctx.moveTo(-14, -3); ctx.lineTo(-26 - Math.random() * 8, 0); ctx.lineTo(-14, 3); ctx.fill();
        ctx.restore();
        if (Math.random() < 0.7) addPart(x - Math.cos(ang) * 16, y - Math.sin(ang) * 16, 0, 0, 0.5, 6, "#aeb6c4", -10, true);
      } else if (type === 1) {
        ctx.fillStyle = "#ffe08a"; ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
      } else {
        ctx.strokeStyle = "#ffe08a"; ctx.lineWidth = 3; ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - Math.cos(ang) * 22, y - Math.sin(ang) * 22); ctx.stroke();
        ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - Math.cos(ang) * 10, y - Math.sin(ang) * 10); ctx.stroke();
      }
    }
  }

  function frame(now) {
    rafId = requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - (lastFrame || now)) / 1000);
    lastFrame = now;
    const dpr = dprNow();
    const cw = Math.round(window.innerWidth * dpr), ch = Math.round(window.innerHeight * dpr);
    if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; }
    ctx.imageSmoothingEnabled = false;
    if (!world || !tiles) {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = "#0a1220"; ctx.fillRect(0, 0, cw, ch);
      return;
    }

    // playback clock: real time normally, slowed during the final-kill finisher
    if (finisher && (now - finisher.r0) / 1000 > FIN_MAX_S) clearFinisher();
    const slow = finisher ? FIN_SLOW : 1;
    pnow = finisher ? pnow + dt * 1000 * slow : now;
    fxMs += dt * 1000 * slow;
    const fdt = dt * slow;
    fdtCur = fdt;

    while (evq.length && evq[0].due <= pnow) handleEvent(evq.shift().e);

    const base = Math.min(window.innerWidth / 800, window.innerHeight / 440) * dpr;
    const cur = interpolated(pnow);
    const mine = cur.players.find((p) => p[0] === me);
    if (mine) myPos = { x: mine[1] + world.pw / 2, y: mine[2] + 31 };
    if (finisher) {
      // 0-1.3s: hold on the victim, 1.3-2.3s: swing across to the killer
      const e = (now - finisher.r0) / 1000;
      const vp = cur.players.find((p) => p[0] === finisher.victim);
      const kp = cur.players.find((p) => p[0] === finisher.killer) || vp;
      if (vp) {
        const t = clamp((e - 1.3) / 1.0, 0, 1), s = t * t * (3 - 2 * t);
        const tx = vp[1] + (kp[1] - vp[1]) * s + world.pw / 2, ty = vp[2] + (kp[2] - vp[2]) * s + world.ph / 2;
        const k = Math.min(1, dt * 6);
        cam.x += (tx - cam.x) * k; cam.y += (ty - cam.y) * k;
      }
      zoomCur += ((e < 1.3 ? 1.8 : 1.5) - zoomCur) * Math.min(1, dt * 4);
    } else if (mine) {
      const k = Math.min(1, dt * 9);
      cam.x += (mine[1] + world.pw / 2 - cam.x) * k;
      cam.y += (mine[2] + world.ph / 2 - cam.y) * k;
    }
    const sc = base * zoomCur;
    const halfW = cw / sc / 2, halfH = ch / sc / 2;
    const wW = world.cols * T, wH = world.rows * T;
    cam.x = wW <= halfW * 2 ? wW / 2 : clamp(cam.x, halfW, wW - halfW);
    cam.y = wH <= halfH * 2 ? wH / 2 : clamp(cam.y, halfH, wH - halfH);
    view.sc = sc;

    drawSky(cw, ch, sc);
    shake *= Math.pow(0.02, dt);
    const sx = (Math.random() - 0.5) * shake, sy = (Math.random() - 0.5) * shake;
    ctx.setTransform(sc, 0, 0, sc, cw / 2 - cam.x * sc + sx * sc, ch / 2 - cam.y * sc + sy * sc);
    const vx0 = cam.x - halfW - T, vy0 = cam.y - halfH - T, vx1 = cam.x + halfW + T, vy1 = cam.y + halfH + T;
    drawTiles(vx0, vy0, vx1, vy1, 0);
    drawProps();
    drawTiles(vx0, vy0, vx1, vy1, 1);
    drawPickups(pnow);
    drawBullets(cur.bullets);
    for (const p of cur.players) drawSoldier(p, pnow);
    drawEffects(fxMs, fdt);
    drawFeedback(fxMs);
    updateJets(cur.players, dt);
    updateAmbience(dt, mine);

    if (hurtFlash > 0.01) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const g = ctx.createRadialGradient(cw / 2, ch / 2, ch * 0.3, cw / 2, ch / 2, ch * 0.9);
      g.addColorStop(0, "rgba(210,40,40,0)"); g.addColorStop(1, "rgba(210,40,40," + (0.55 * hurtFlash) + ")");
      ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch);
      hurtFlash *= Math.pow(0.03, dt);
    }
    // low health: heartbeat that speeds up as you get weaker, with a vignette that pulses on each beat
    const hpNow = mine && !(mine[8] & 4) && phase === "play" ? mine[6] : 100;
    const weak = hpNow <= 30 ? 1 - hpNow / 30 : 0;
    lowHp += (weak - lowHp) * Math.min(1, dt * 4);
    if (weak > 0 && now >= hbAt) {
      if (!play("heartbeat", 0.5 + 0.4 * weak)) { tone(70, 45, 0.12, 0.25, "sine"); tone(62, 42, 0.12, 0.18, "sine", 0.27); }
      hbAt = now + 1050 - 480 * weak; hbPulse = 1;
    }
    hbPulse *= Math.pow(0.02, dt);
    if (lowHp > 0.02) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const g = ctx.createRadialGradient(cw / 2, ch / 2, ch * 0.28, cw / 2, ch / 2, ch * 0.95);
      g.addColorStop(0, "rgba(40,0,0,0)"); g.addColorStop(1, "rgba(70,0,0," + (lowHp * (0.3 + 0.5 * hbPulse)).toFixed(3) + ")");
      ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch);
    }
  }

  function startRender() {
    if (!rafId) { lastFrame = 0; rafId = requestAnimationFrame(frame); }
  }

  // ------------------------------------------------------------ Settings sheet (every option is saved on this device)
  const store = (k, v) => { try { localStorage.setItem(k, String(v)); } catch (e) {} };
  const load = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } };
  const loadNum = (k, d, lo, hi) => { const v = parseFloat(load(k, "")); return v >= lo && v <= hi ? v : d; };
  const FIRE_MODES = [["Light", 8], ["Normal", 14], ["Heavy", 30]];
  const HUD_MODES = ["Ping", "Ping + FPS", "Off"];
  let lefty = false, padO = 1, fireIdx = 1, hudMode = 0, fsCount = 0, fsT = performance.now();

  function applySettings() {
    document.body.classList.toggle("lefty", lefty);
    document.documentElement.style.setProperty("--padK", String(padK));
    document.documentElement.style.setProperty("--padO", String(padO));
    fireThr = FIRE_MODES[fireIdx][1];
    $("netChip").hidden = hudMode === 2;
    $("hudFps").hidden = hudMode !== 1;
    try { resetPads(); } catch (e) {}
  }
  function syncSettingsUi() {
    $("setSound").textContent = muted ? "Off" : "On";
    $("setVol").value = Math.round(volume * 100);
    $("setSfx").value = Math.round(sfxVol * 100);
    $("setMusic").value = Math.round(musicVol * 100);
    $("setLefty").textContent = lefty ? "On" : "Off";
    $("setStick").value = Math.round(padK * 100);
    $("setPadOp").value = Math.round(padO * 100);
    $("setFire").textContent = FIRE_MODES[fireIdx][0];
    $("setShake").textContent = shakeOn ? "On" : "Off";
    $("setFs").textContent = document.fullscreenElement ? "Exit" : "Enter";
    $("setHud").textContent = HUD_MODES[hudMode];
    $("setName").value = $("nameInput").value;
    $("setReset").textContent = "Reset";
    $("setLefty").classList.toggle("on", lefty);
  }
  function openSettings() {
    syncSettingsUi();
    $("setSheet").hidden = false;
  }

  // load saved values
  sfxVol = loadNum("ls_sfx", 1, 0, 1);
  musicVol = loadNum("ls_music", 1, 0, 1);
  lefty = load("ls_lefty", "0") === "1";
  padK = loadNum("ls_padk", 1, 0.7, 1.4);
  padO = loadNum("ls_pado", 1, 0.1, 1);
  fireIdx = clamp(parseInt(load("ls_fire", "1"), 10) || 0, 0, 2);
  shakeOn = load("ls_shake", "1") !== "0";
  hudMode = clamp(parseInt(load("ls_hud", "0"), 10) || 0, 0, 2);

  $("setSfx").oninput = (e) => { sfxVol = clamp(Number(e.target.value) / 100, 0, 1); store("ls_sfx", sfxVol); };
  $("setSfx").onchange = () => play("weapon_pickup", 0.8);   // preview
  $("setMusic").oninput = (e) => {
    musicVol = clamp(Number(e.target.value) / 100, 0, 1); store("ls_music", musicVol);
    setAmbVol();
  };
  $("setLefty").onclick = () => { lefty = !lefty; store("ls_lefty", lefty ? 1 : 0); applySettings(); syncSettingsUi(); };
  $("setStick").oninput = (e) => { padK = clamp(Number(e.target.value) / 100, 0.7, 1.4); store("ls_padk", padK); applySettings(); };
  $("setPadOp").oninput = (e) => { padO = clamp(Number(e.target.value) / 100, 0.1, 1); store("ls_pado", padO); applySettings(); };
  $("setFire").onclick = () => { fireIdx = (fireIdx + 1) % FIRE_MODES.length; store("ls_fire", fireIdx); applySettings(); syncSettingsUi(); };
  $("setShake").onclick = () => { shakeOn = !shakeOn; if (!shakeOn) shake = 0; store("ls_shake", shakeOn ? 1 : 0); syncSettingsUi(); };
  $("setFs").onclick = () => {
    if (document.fullscreenElement) { try { document.exitFullscreen(); } catch (e) {} }
    else enterFullscreen();
    setTimeout(syncSettingsUi, 300);
  };
  document.addEventListener("fullscreenchange", syncSettingsUi);
  $("setHud").onclick = () => { hudMode = (hudMode + 1) % HUD_MODES.length; store("ls_hud", hudMode); applySettings(); syncSettingsUi(); };
  $("setName").oninput = (e) => { $("nameInput").value = e.target.value; store("ls_name", e.target.value.trim()); };
  $("setLb").onclick = () => { closeSettings(); $("lbAll").click(); };
  $("setHelp").onclick = () => { closeSettings(); $("helpSheet").hidden = false; };
  $("pauseSet").onclick = () => { closePause(); openSettings(); };
  let resetArmed = 0;
  $("setReset").onclick = () => {
    if (!resetArmed) { resetArmed = setTimeout(() => { resetArmed = 0; $("setReset").textContent = "Reset"; }, 3000); $("setReset").textContent = "Sure?"; return; }
    clearTimeout(resetArmed); resetArmed = 0;
    for (const k of ["ls_skin", "ls_vol", "ls_mute", "ls_sfx", "ls_music", "ls_lefty", "ls_padk", "ls_pado", "ls_fire", "ls_shake", "ls_hud"]) {
      try { localStorage.removeItem(k); } catch (e) {}
    }
    muted = false; volume = 1; sfxVol = 1; musicVol = 1; lefty = false; padK = 1; padO = 1; fireIdx = 1; shakeOn = true; hudMode = 0;
    $("sndBtn").textContent = "Sound";
    setAmbVol();
    syncAmbient(); applySettings(); syncSettingsUi(); syncMenuFace(); renderAvatars();
    toast("Settings reset");
  };

  // FPS readout (only counted while it is shown)
  (function fpsLoop() {
    if (hudMode === 1) {
      fsCount++;
      const now = performance.now();
      if (now - fsT >= 1000) { $("hudFps").textContent = Math.round(fsCount * 1000 / (now - fsT)) + " fps"; fsCount = 0; fsT = now; }
    } else { fsCount = 0; fsT = performance.now(); }
    requestAnimationFrame(fpsLoop);
  })();
  applySettings();

}

(function boot() {
  const conn = document.getElementById("conn");
  function status(msg, cls) { conn.textContent = msg; conn.className = "conn " + (cls || ""); }
  let tries = 0;

  (function wait() {
    if (window.io) { status("Connecting..."); return start(); }
    if (++tries > 50) {
      return status("Could not load the game library. Check your internet connection and reload.", "bad");
    }
    setTimeout(wait, 200);
  })();
})();
