function start() {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const COLORS = ["#5fa83a", "#d94b45", "#3f8fe0", "#f0b429", "#9b59d0", "#e8eef2"];
  const TEAM_NAMES = { 1: "Survivors", 2: "Hunters" };
  const TEAM_COLORS = { 1: "#3f8fe0", 2: "#d94b45" };
  const INTERP_MS = 100;           // render this far in the past for smooth motion
  const SPR = 0.85;                // sprite scale (128px frames)
  const WAIST = 100;               // frame rows above this swing with the aim
  const TIP = 0.18;                // the baked-in rifle points slightly upward
  const AIM_LIMIT = 1.3;
  const BULLET_SPEED = [1500, 1300, 760];
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const dprNow = () => Math.min(window.devicePixelRatio || 1, 2);

  // ------------------------------------------------------------ state
  let me = null, code = null, world = null, isHost = false, lobby = null;
  let snaps = [], evq = [], rtt = null, rafId = 0, toastTimer = 0;
  let phase = "play", winner = -1, overShown = false;
  let mode = "solo", winTeam = -1;          // from the server snapshot: "solo" | "team"
  let latest = null;
  let localAim = 0, myPos = null;
  let shake = 0, hurtFlash = 0, lastFrame = 0, boardKey = "";
  let actx = null, noiseBuf = null, muted = false;
  const cam = { x: 1600, y: 1200 };
  const view = { sc: 1 };
  const pst = new Map();
  const parts = [], expls = [], flashes = [];

  const socket = io();
  let connectedOnce = false, creating = false;

  // ------------------------------------------------------------ ui helpers
  function show(name) {
    for (const id of ["home", "lobby", "game"]) $(id).classList.toggle("active", id === name);
    if (name === "game") { resetPads(); startRender(); }
    else { cancelAnimationFrame(rafId); rafId = 0; }
    syncAmbient();
    if (name === "home") loadBoard();
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
  // team of a player (explicit server data, never guessed from colour)
  const teamOf = (id) => {
    const p = latest && latest.p.find((q) => q[0] === id);
    return p ? p[12] : 0;
  };
  const colorOf = (id) => (mode === "team" && teamOf(id) ? TEAM_COLORS[teamOf(id)] : COLORS[id % COLORS.length]);
  const fmtTime = (s) => { s = Math.max(0, s | 0); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
  // one tinted copy of the base skin per team, so every member of a team looks the same colour
  const tintCache = {};
  function teamSkin(team) {
    const base = skinImgs[0];
    if (!base) return null;
    if (tintCache[team] && tintCache[team].src === base) return tintCache[team].cv;
    const cv = document.createElement("canvas");
    cv.width = base.width; cv.height = base.height;
    const g = cv.getContext("2d");
    g.drawImage(base, 0, 0);
    g.globalCompositeOperation = "color";
    g.fillStyle = TEAM_COLORS[team];
    g.fillRect(0, 0, cv.width, cv.height);
    g.globalCompositeOperation = "destination-in";
    g.drawImage(base, 0, 0);
    tintCache[team] = { src: base, cv };
    return cv;
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
  // top-left server pill on the landing page
    $("createBtn").onclick = () => {
    if (!online()) return;
    const rn = $("roomNameInput").value.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    if ($("roomNameInput").value.trim() && rn.length < 3) return toast("Room names need 3 to 12 letters or numbers.", true);
    try { localStorage.setItem("ls_room", rn); } catch (e) {}
    creating = true;
    socket.emit("create_room", { name: myName(), device: deviceId(), room_name: rn });
  };
  $("joinBtn").onclick = joinTyped;
  $("codeInput").addEventListener("keydown", (e) => { if (e.key === "Enter") joinTyped(); });
  $("acceptBtn").onclick = () => { if (online()) socket.emit("join", { code: window.ROOM_CODE, name: myName(), device: deviceId() }); };
  $("ownRoomBtn").onclick = () => {
    history.replaceState(null, "", "/");
    window.ROOM_CODE = "";
    $("inviteBlock").hidden = true;
    $("mainBlock").hidden = false;
  };
  function joinTyped() {
    const c = $("codeInput").value.trim().toUpperCase();
    if (c.length < 3) return toast("Enter the room code or name.", true);
    if (online()) socket.emit("join", { code: c, name: myName(), device: deviceId() });
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
  async function loadBoard() {
    const d = await fetchBoard(3);
    const mine = d.me ? d.me.rank : -1;
    $("lbTop").innerHTML = d.top.length
      ? d.top.map((r, i) => lbRow(r, d.me && r.rank === mine && r.name === d.me.name && r.kills === d.me.kills, "r" + Math.min(3, i + 1))).join("")
      : '<li class="lb-empty">No rankings yet</li>';
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
  loadBoard();

  // ------------------------------------------------------------ lobby
  $("codeBtn").onclick = () => copy(code, "Room code copied");
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
  for (const b of document.querySelectorAll("#modeBox .mode")) {
    b.onclick = () => { if (isHost) socket.emit("set_mode", { mode: b.dataset.mode }); };
  }
  for (const b of document.querySelectorAll("#mapBox .mode")) {
    b.onclick = () => { if (isHost) socket.emit("set_map", { map: b.dataset.map }); };
  }
  $("exitBtn").onclick = leaveRoom;
  $("overLeave").onclick = leaveRoom;
  $("againBtn").onclick = () => socket.emit("rematch");
  $("fsBtn").onclick = enterFullscreen;
  $("sndBtn").onclick = () => {
    muted = !muted;
    try { localStorage.setItem("ls_mute", muted ? "1" : "0"); } catch (e) {}
    $("sndBtn").textContent = muted ? "Muted" : "Sound";
    syncAmbient();
  };

  function copy(text, okMsg) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast(okMsg), () => toast(text));
    } else toast(text);
  }

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
    socket.emit("leave");
    code = null; world = null; lobby = null; snaps = []; evq = []; latest = null; me = null;
    pst.clear(); parts.length = 0; expls.length = 0; flashes.length = 0;
    $("teamBar").hidden = true; mode = "solo"; winTeam = -1; $("over").hidden = true; $("feed").textContent = "";
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    history.replaceState(null, "", "/");
    window.ROOM_CODE = "";
    $("inviteBlock").hidden = true;
    $("mainBlock").hidden = false;
    show("home");
  }

  function renderLobby() {
    if (!lobby) return;
    $("codeBtn").textContent = lobby.code;
    $("hudRoom").textContent = lobby.code;
    $("playerCount").textContent = lobby.players.length + " of " + lobby.max;
    isHost = lobby.host === me;
    const ul = $("playerList");
    ul.textContent = "";
    for (const p of lobby.players) {
      const li = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = COLORS[p.id % COLORS.length];
      const name = document.createElement("span");
      name.textContent = p.name;
      li.append(dot, name);
      const tags = [];
      if (p.id === lobby.host) tags.push("host");
      if (p.id === me) tags.push("you");
      if (tags.length) {
        const t = document.createElement("span");
        t.className = "tag";
        t.textContent = tags.join(", ");
        li.append(t);
      }
      ul.append(li);
    }
    const lm = lobby.mode || "solo";
    for (const b of document.querySelectorAll("#modeBox .mode")) b.classList.toggle("on", b.dataset.mode === lm);
    $("modeBox").classList.toggle("locked", !isHost);
    const lmap = lobby.map || "lab";
    for (const b of document.querySelectorAll("#mapBox .mode")) b.classList.toggle("on", b.dataset.map === lmap);
    $("mapBox").classList.toggle("locked", !isHost);
    const canStart = lobby.players.length >= lobby.min;
    $("startBtn").hidden = !isHost;
    $("startBtn").disabled = !canStart;
    $("startBtn").textContent = canStart ? "Start match" : "Need " + lobby.min + " players to start";
    $("waitMsg").hidden = isHost;
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
    if (connectedOnce && code) socket.emit("join", { code, name: myName(), device: deviceId() });
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
    lobby = d; renderLobby();
  });

  socket.on("start", (d) => {
    world = d.world;
    loadArt(world);
    snaps = []; evq = []; latest = null;
    pst.clear(); parts.length = 0; expls.length = 0; flashes.length = 0;
    $("over").hidden = true; $("feed").textContent = "";
    phase = "play"; overShown = false; mode = "solo"; winTeam = -1;
    $("teamBar").hidden = true;
    buildTiles();
    show("game");
    play("match_start", 0.9);
  });

  socket.on("state", (d) => {
    const at = performance.now();
    snaps.push({ at, p: d.p, b: d.b });
    if (snaps.length > 12) snaps.shift();
    for (const e of d.e) evq.push({ due: at + INTERP_MS, e });
    latest = d;
    trackPlayers(d, at);
    phase = d.m[0]; winner = d.m[1];
    mode = d.m[2] || "solo"; winTeam = d.m.length > 6 ? d.m[6] : -1;
    updateHud();
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
      $("hudPing").textContent = rtt + " ms";
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
        if (st.air && st.airVy > 160) SFX.land(p[1], p[2]);
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

  // ------------------------------------------------------------ HUD
  function updateHud() {
    if (!latest) return;
    const mine = latest.p.find((p) => p[0] === me);
    if (mine) {
      const hp = mine[6];
      $("hpFill").style.width = hp + "%";
      $("hpFill").style.background = hp > 55 ? "#5fc24a" : hp > 25 ? "#e8b02e" : "#d24a43";
      $("hpText").textContent = hp;
      const w = world && world.weapons[String(mine[7])];
      $("wpnText").textContent = (w ? w.name : "") + "  " + (mine[10] < 0 ? "\u221E" : mine[10]);
      const b = $("banner");
      if ((mine[8] & 4) && phase === "play") {
        b.hidden = false;
        const as = mode === "team" && mine[12] ? (mine[12] === 1 ? "as a Survivor " : "as a Hunter ") : "";
        b.textContent = "Respawning " + as + "in " + Math.max(1, Math.ceil(mine[11]));
      } else b.hidden = true;
    }
    const tb = $("teamBar");
    if (mode === "team") {
      const sv = latest.p.filter((p) => p[12] === 1).length, hn = latest.p.filter((p) => p[12] === 2).length;
      const m = latest.m, c1 = phase === "over" ? m[4] : sv, c2 = phase === "over" ? m[5] : hn;
      const left = m[3];
      const key2 = c1 + "|" + c2 + "|" + left + "|" + (mine ? mine[12] : 0);
      if (tb.dataset.k !== key2) {
        tb.dataset.k = key2;
        tb.textContent = "";
        const a = document.createElement("span"); a.className = "sv"; a.textContent = "Survivors: " + c1;
        const h = document.createElement("span"); h.className = "hn"; h.textContent = "Hunters: " + c2;
        const t = document.createElement("span"); t.className = "tm" + (left <= 30 && phase === "play" ? " low" : ""); t.textContent = fmtTime(left);
        tb.append(a, document.createTextNode("|"), h, document.createTextNode("|"), t);
        if (mine && mine[12]) {
          const y = document.createElement("span"); y.className = mine[12] === 1 ? "sv" : "hn"; y.textContent = "You: " + TEAM_NAMES[mine[12]];
          tb.append(document.createTextNode("|"), y);
        }
      }
      tb.hidden = false;
    } else tb.hidden = true;
    const rows = latest.p.slice().sort((a, b) => b[9] - a[9] || a[0] - b[0]);
    const key = rows.map((p) => p[0] + ":" + p[9] + ":" + p[12] + ":" + p[13]).join(",") + "|" + (lobby ? lobby.players.length : 0) + mode;
    if (key !== boardKey) {
      boardKey = key;
      fillBoard($("board"), rows, false);
      if (phase === "over") fillBoard($("overBoard"), rows, true);
    }
    if (phase === "over" && !overShown) {
      overShown = true;
      fillBoard($("overBoard"), rows, true);
      const sub = $("overSub");
      let won;
      if (mode === "team") {
        const m = latest.m;
        $("overTitle").textContent = winTeam === 0 ? "Draw!" : TEAM_NAMES[winTeam] + " win!";
        sub.hidden = false;
        sub.textContent = "Final: Survivors " + m[4] + " | Hunters " + m[5];
        const myTeam = mine ? mine[12] : 0;
        won = winTeam > 0 && winTeam === myTeam;
      } else {
        sub.hidden = true;
        $("overTitle").textContent = winner === me ? "You win!" : nameOf(winner) + " wins!";
        won = winner === me;
      }
      $("over").hidden = false;
      $("againBtn").hidden = !isHost;
      $("againWait").hidden = isHost;
      $("banner").hidden = true;
      if (won) SFX.win(); else SFX.lose();
    } else if (phase === "play" && overShown) {
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
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = mode === "team" && p[12] ? TEAM_COLORS[p[12]] : COLORS[p[0] % COLORS.length];
      if (!big) dot.style.width = dot.style.height = "12px";
      const nm = document.createElement("span");
      nm.className = "nm";
      nm.textContent = nameOf(p[0]);
      const k = document.createElement("span");
      k.textContent = big ? p[9] + " kills \u00b7 " + p[13] + " deaths" : String(p[9]);
      if (big && mode === "team" && p[12]) {
        const tg = document.createElement("span"); tg.className = "tg"; tg.textContent = TEAM_NAMES[p[12]];
        li.append(dot, nm, tg, k);
      } else li.append(dot, nm, k);
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
      mid.textContent = [" shot ", " shredded ", " rocketed "][wpn] || " got ";
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
    "room_created", "player_joined", "player_left", "match_start", "victory", "defeat", "menu_ambient"];
  let sndLoading = false, ambient = null;
  function loadSounds() {
    const a = ac();
    if (!a || sndLoading) return;
    sndLoading = true;
    for (const n of SND_FILES) {
      fetch("/static/audio/" + n + ".wav?v=6")
        .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject()))
        .then((buf) => new Promise((res, rej) => a.decodeAudioData(buf, res, rej)))
        .then((b) => { SND[n] = b; if (n === "menu_ambient") syncAmbient(); })
        .catch(() => {});
    }
  }
  function play(name, vol, rate) {
    const a = actx, b = SND[name];
    if (!a || !b) return false;          // not ready: caller falls back to synth
    if (muted || a.state !== "running" || vol < 0.02) return true;
    const s = a.createBufferSource(); s.buffer = b;
    if (rate) s.playbackRate.value = rate;
    const g = a.createGain(); g.gain.value = vol;
    s.connect(g); g.connect(a.destination); s.start();
    return true;
  }
  // menu ambient: plays on the landing page and lobby, stops during a match or when muted
  function syncAmbient() {
    const a = actx;
    const want = !!(a && a.state === "running" && !muted && SND.menu_ambient && !$("game").classList.contains("active"));
    if (want && !ambient) {
      const s = a.createBufferSource(); s.buffer = SND.menu_ambient; s.loop = true;
      const g = a.createGain(); g.gain.value = 1.8;
      s.connect(g); g.connect(a.destination); s.start();
      ambient = s;
    } else if (!want && ambient) {
      try { ambient.stop(); } catch (e) {}
      ambient = null;
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
    g.gain.setValueAtTime(vol, t);
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
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g); g.connect(a.destination);
    o.start(t); o.stop(t + dur + 0.03);
  }
  const near = (x, y) => (x == null ? 1 : Math.max(0.1, 1 - Math.hypot(x - cam.x, y - cam.y) / 1400));
  const SFX = {
    shot: (w, x, y) => {
      const v = near(x, y);
      const n = ["pistol_fire", "shotgun_fire", "rocket_launch"][w];
      if (n && play(n, 0.55 * v, 0.96 + Math.random() * 0.08)) return;
      if (w === 0) { noise(0.09, 4500, 800, 0.35 * v, "highpass"); tone(380, 90, 0.08, 0.12 * v, "square"); }
      else if (w === 1) { noise(0.2, 3000, 300, 0.6 * v); tone(140, 45, 0.16, 0.25 * v, "sawtooth"); }
      else { noise(0.35, 1200, 200, 0.5 * v); tone(200, 60, 0.3, 0.2 * v, "sawtooth"); }
    },
    boom: (x, y) => {
      const v = near(x, y);
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
    const k = KEYMAP[e.code];
    if (!k) return;
    e.preventDefault();
    kb[k] = down;
  }
  window.addEventListener("keydown", (e) => onKey(e, true));
  window.addEventListener("keyup", (e) => onKey(e, false));
  window.addEventListener("blur", () => { kb.l = kb.r = kb.u = kb.d = false; mouse.down = false; });

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
      const len = Math.hypot(dx, dy);
      if (len > R) { dx = dx / len * R; dy = dy / len * R; }
      knob.style.transform = "translate(" + dx + "px, " + dy + "px)";
      onMove(dx / R, dy / R, len);
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
    () => ({ x: 120, y: window.innerHeight - 100 }),
    (nx, ny) => { stick.x = Math.abs(nx) > 0.2 ? nx : 0; stick.y = Math.abs(ny) > 0.2 ? ny : 0; },
    () => { stick.x = stick.y = 0; });
  const resetR = makePad("aimZone", "aimBase", "aimKnob", 52,
    () => ({ x: window.innerWidth - 120, y: window.innerHeight - 100 }),
    (nx, ny, len) => { aimT.active = true; aimT.ang = Math.atan2(ny, nx); aimT.fire = len > 14; },
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
  for (let i = 0; i < 6; i++) loadImg("/static/img/skin" + i + ".png?v=3").then((im) => { skinImgs[i] = im; });
  loadImg("/static/img/explosion.png?v=3").then((im) => { explImg = im; });
  const SK = (window.SKINS && window.SKINS.counts) || {};

  // Laboratory art (static/img/lab). Anything that fails to load falls back to the drawn tiles / shapes.
  const LAB = {};
  const LAB_FILES = ["floor_plain", "floor_hazard", "wall_light", "wall_cable", "wall_warn", "plat_long", "door_open",
    "tank_green", "tank_blue", "tank_small", "term_rack", "term_desk", "term_kiosk", "term_arcade", "term_a",
    "light_cyan", "light_amber", "light_red", "pipe_long", "pipe_bundle", "pk_shotgun", "pk_rocket", "pk_health"];
  Promise.all(LAB_FILES.map((n) => loadImg("/static/img/lab/" + n + ".png?v=7").then((im) => { if (im) LAB[n] = im; })))
    .then(() => { if (tiles && !(world && world.art === "street")) useLabTiles(); });

  // Street art (static/img/street): only the sprites the map's props list asks for
  const ART = {}, artAsked = new Set();
  function loadArt(w) {
    if (!w || w.art !== "street") return;
    for (const pr of (w.props || [])) {
      const n = pr[0];
      if (artAsked.has(n)) continue;
      artAsked.add(n);
      loadImg("/static/img/street/" + n + ".png?v=1").then((im) => { if (im) ART[n] = im; });
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
    if (world && world.art === "street") useStreetTiles(); else useLabTiles();
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
            if (r % 6 === 2) t = tiles.pipe;
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

  function drawJetpack(thrust) {
    // the jetpack body is hidden until there is a better sprite; only the thrust flame remains
    if (thrust) {
      const l = 22 + Math.random() * 14;
      ctx.fillStyle = "#ff7a1a";
      ctx.beginPath(); ctx.moveTo(-25, -27); ctx.lineTo(-14, -27); ctx.lineTo(-19.5, -27 + l); ctx.fill();
      ctx.fillStyle = "#ffe08a";
      ctx.beginPath(); ctx.moveTo(-23, -27); ctx.lineTo(-16, -27); ctx.lineTo(-19.5, -27 + l * 0.55); ctx.fill();
    }
  }

  function drawSoldier(p, now) {
    const id = p[0], x = p[1], y = p[2], vx = p[3], flags = p[8];
    const st = pst.get(id) || { deadAt: 0, hurtAt: 0, hurtUntil: 0 };
    const dead = !!(flags & 4);
    if (dead && now - st.deadAt > 1900) return;
    const aim = id === me && !dead ? localAim : p[5];
    const facing = Math.cos(aim) >= 0 ? 1 : -1;
    const team = mode === "team" ? p[12] : 0;
    const sid = team ? 0 : id % 6;
    const cnt = SK[sid] || [7, 8, 4, 3, 4];
    const img = (team && teamSkin(team)) || skinImgs[sid];
    const ground = !!(flags & 1), thrust = !!(flags & 2), firing = !!(flags & 8);

    let row = 0, idx = 0, whole = false;
    if (dead) { row = 4; idx = Math.min(cnt[4] - 1, Math.floor((now - st.deadAt) / 110)); whole = true; }
    else if (now < st.hurtUntil) { row = 3; idx = Math.min(cnt[3] - 1, Math.floor((now - st.hurtAt) / 70)); whole = true; }
    else if (firing) { row = 2; idx = [0, 1, 3][Math.floor(now / 55) % 3]; }
    else if (ground && Math.abs(vx) > 20) { row = 1; idx = Math.floor(now / 85) % cnt[1]; }
    else { row = 0; idx = Math.floor(now / 140) % cnt[0]; }

    ctx.save();
    if (flags & 16) ctx.globalAlpha = Math.floor(now / 90) % 2 ? 0.4 : 0.85;
    ctx.translate(Math.round(x + world.pw / 2), Math.round(y + world.ph));
    ctx.scale(facing * SPR, SPR);
    if (!dead) drawJetpack(thrust);
    if (!img) {
      ctx.fillStyle = team ? TEAM_COLORS[team] : COLORS[id % 6]; ctx.fillRect(-16, -64, 32, 64);
    } else if (whole) {
      ctx.drawImage(img, idx * 128, row * 128, 128, 128, -64, -127, 128, 128);
    } else {
      let am = facing === 1 ? aim : Math.PI - aim;
      am = clamp(Math.atan2(Math.sin(am), Math.cos(am)), -AIM_LIMIT, AIM_LIMIT);
      ctx.drawImage(img, idx * 128, row * 128 + WAIST, 128, 128 - WAIST, -64, WAIST - 127, 128, 128 - WAIST);
      ctx.save();
      ctx.translate(0, WAIST - 127);
      ctx.rotate(am + TIP);
      ctx.drawImage(img, idx * 128, row * 128, 128, WAIST, -64, -WAIST, 128, WAIST);
      ctx.restore();
    }
    ctx.restore();

    if (dead) return;
    if (thrust && Math.random() < 0.5) {
      addPart(x + world.pw / 2 - facing * 14, y + 40, -facing * 20 + (Math.random() - 0.5) * 30, 80 + Math.random() * 60, 0.45, 5, "#9aa4b5", -40, true);
    }
    const cx = x + world.pw / 2;
    ctx.textAlign = "center";
    ctx.font = "700 14px 'Barlow Semi Condensed', sans-serif";
    ctx.lineWidth = 4; ctx.strokeStyle = "rgba(10,18,32,.85)";
    ctx.fillStyle = team ? TEAM_COLORS[team] : COLORS[id % 6];
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
  function addPart(x, y, vx, vy, life, size, color, g, smoke) {
    if (parts.length > 400) parts.shift();
    parts.push({ x, y, vx, vy, life, max: life, size, color, g, smoke: !!smoke });
  }
  function sparks(x, y, n, color, spd) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, s = (0.3 + Math.random()) * spd;
      addPart(x, y, Math.cos(a) * s, Math.sin(a) * s, 0.25 + Math.random() * 0.25, 2 + Math.random() * 2, color, 600, false);
    }
  }

  function handleEvent(e) {
    const k = e[0];
    if (k === "sh") {
      flashes.push({ x: e[2], y: e[3], a: e[4], w: e[5], t0: performance.now() });
      SFX.shot(e[5], e[2], e[3]);
      if (e[5] === 2) for (let i = 0; i < 4; i++) addPart(e[2], e[3], (Math.random() - 0.5) * 60, (Math.random() - 0.5) * 60, 0.6, 7, "#b8bfcc", -20, true);
    } else if (k === "hit") {
      sparks(e[1], e[2], 6, "#ffd479", 260); SFX.hit(e[1], e[2]);
    } else if (k === "bl") {
      sparks(e[1], e[2], 9, "#c0392b", 220); SFX.bleed(e[1], e[2]);
    } else if (k === "ex") {
      expls.push({ x: e[1], y: e[2], r: e[3], t0: performance.now() });
      sparks(e[1], e[2], 18, "#ff9f43", 520);
      for (let i = 0; i < 10; i++) addPart(e[1], e[2], (Math.random() - 0.5) * 240, (Math.random() - 0.5) * 240 - 40, 0.9, 10 + Math.random() * 8, "#6b7280", -30, true);
      SFX.boom(e[1], e[2]);
      shake = Math.min(16, shake + Math.max(0, 16 - Math.hypot(e[1] - cam.x, e[2] - cam.y) / 60));
    } else if (k === "k") {
      feedRow(e[1], e[2], e[3]);
      SFX.death(e[2] === me);
      if (e[1] === me && e[2] !== me) SFX.kill();
    } else if (k === "pu") {
      if (e[2] === me) SFX.pickup();
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
      const s = f.w === 0 ? 1 : f.w === 1 ? 1.5 : 1.9;
      ctx.save(); ctx.translate(f.x, f.y); ctx.rotate(f.a);
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
      p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt;
      const a = p.life / p.max;
      ctx.globalAlpha = p.smoke ? a * 0.55 : a;
      ctx.fillStyle = p.color;
      const s = p.smoke ? p.size * (2 - a) : p.size;
      ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
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

    while (evq.length && evq[0].due <= now) handleEvent(evq.shift().e);

    const sc = Math.min(window.innerWidth / 800, window.innerHeight / 440) * dpr;
    const cur = interpolated(now);
    const mine = cur.players.find((p) => p[0] === me);
    if (mine) {
      myPos = { x: mine[1] + world.pw / 2, y: mine[2] + 31 };
      const k = Math.min(1, dt * 9);
      cam.x += (mine[1] + world.pw / 2 - cam.x) * k;
      cam.y += (mine[2] + world.ph / 2 - cam.y) * k;
    }
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
    drawPickups(now);
    drawBullets(cur.bullets);
    for (const p of cur.players) drawSoldier(p, now);
    drawEffects(now, dt);

    if (hurtFlash > 0.01) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const g = ctx.createRadialGradient(cw / 2, ch / 2, ch * 0.3, cw / 2, ch / 2, ch * 0.9);
      g.addColorStop(0, "rgba(210,40,40,0)"); g.addColorStop(1, "rgba(210,40,40," + (0.55 * hurtFlash) + ")");
      ctx.fillStyle = g; ctx.fillRect(0, 0, cw, ch);
      hurtFlash *= Math.pow(0.03, dt);
    }
  }

  function startRender() {
    if (!rafId) { lastFrame = 0; rafId = requestAnimationFrame(frame); }
  }
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
