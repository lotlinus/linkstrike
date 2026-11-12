"""Link Strike store: Link Coins, weapon skins.

Link Coins are earned per kill (COINS_PER_KILL), capped at DAILY_CAP per day (the day rolls over at
midnight Nigeria time, WAT = UTC+1). Skins are cosmetic only. Coins, owned skins and equipped skins
live in Postgres (the same DATABASE_URL as the rankings), keyed by the anonymous device id; the
server is the only place that changes them. Without a database the store is switched off quietly.
The skins themselves are listed in skins.json (id, weapon, name, tier, price) and drawn from
static/img/wpn/skins/<id>.png (menu icon) and hand_<id>.png (in-hand sprite).
"""
import json
import os
from datetime import datetime, timedelta, timezone

import rankings

COINS_PER_KILL = 5
DAILY_CAP = 100
WAT = timezone(timedelta(hours=1))                    # Nigeria time, no daylight saving
WEAPON_ID = {"ak47": 3, "mp5": 6, "ump45": 7, "mac10": 8, "p90": 9}   # same ids as game.py WEAPONS
TIERS = ("common", "rare")

_ready = False


# ---------------------------------------------------------------- catalog
def load_catalog(path=None):
    """[{"id","weapon","wid","name","tier","price"}] from skins.json. Bad entries are skipped."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "skins.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        print("store: could not read skins.json:", exc)
        return []
    out, seen = [], set()
    for s in raw if isinstance(raw, list) else []:
        try:
            sid, wpn = str(s["id"]), str(s["weapon"])
            price = int(s["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if sid in seen or wpn not in WEAPON_ID or price <= 0 or s.get("tier") not in TIERS:
            continue
        seen.add(sid)
        out.append({"id": sid, "weapon": wpn, "wid": WEAPON_ID[wpn], "name": str(s.get("name") or sid),
                    "tier": s["tier"], "price": price})
    return out


CATALOG = load_catalog()
BY_ID = {s["id"]: s for s in CATALOG}


# ---------------------------------------------------------------- pure rules (tested)
def today(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(WAT).strftime("%Y-%m-%d")


def coins_for_kills(kills):
    try:
        return max(0, int(kills)) * COINS_PER_KILL
    except (TypeError, ValueError):
        return 0


def grant(earned_today, earned_day, day, want, cap=DAILY_CAP):
    """How many of `want` coins a player may still receive today. Returns (granted, new earned_today)."""
    have = earned_today if earned_day == day else 0
    granted = max(0, min(int(want), cap - have))
    return granted, have + granted


# ---------------------------------------------------------------- database
def enabled():
    return rankings.enabled() and bool(CATALOG)


def _ensure(conn):
    global _ready
    if _ready:
        return
    conn.run("""CREATE TABLE IF NOT EXISTS wallets (
                    device_id    TEXT PRIMARY KEY,
                    coins        INTEGER NOT NULL DEFAULT 0,
                    earned_today INTEGER NOT NULL DEFAULT 0,
                    earned_day   TEXT NOT NULL DEFAULT '',
                    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.run("""CREATE TABLE IF NOT EXISTS skins_owned (
                    device_id TEXT NOT NULL, skin_id TEXT NOT NULL,
                    bought_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (device_id, skin_id))""")
    conn.run("""CREATE TABLE IF NOT EXISTS skins_equipped (
                    device_id TEXT NOT NULL, weapon INTEGER NOT NULL, skin_id TEXT NOT NULL,
                    PRIMARY KEY (device_id, weapon))""")
    _ready = True


def _run(work, write=False):
    """Run work(conn) on a fresh connection (inside a transaction when write). None if the database fails."""
    conn = None
    try:
        conn = rankings._connect()
        _ensure(conn)
        if write:
            conn.run("BEGIN")
        result = work(conn)
        if write:
            conn.run("COMMIT")
        return result
    except Exception as exc:
        print("store: database error:", exc)
        try:
            conn and write and conn.run("ROLLBACK")
        except Exception:
            pass
        return None
    finally:
        try:
            conn and conn.close()
        except Exception:
            pass


def _lock_wallet(conn, device):
    conn.run("INSERT INTO wallets (device_id) VALUES (:d) ON CONFLICT DO NOTHING", d=device)
    return conn.run("SELECT coins, earned_today, earned_day FROM wallets WHERE device_id = :d FOR UPDATE", d=device)[0]


def _snapshot(conn, device, day):
    row = conn.run("SELECT coins, earned_today, earned_day FROM wallets WHERE device_id = :d", d=device)
    coins, earned, eday = (row[0] if row else (0, 0, ""))
    owned = [r[0] for r in conn.run("SELECT skin_id FROM skins_owned WHERE device_id = :d", d=device)]
    eq = {str(r[0]): r[1] for r in conn.run("SELECT weapon, skin_id FROM skins_equipped WHERE device_id = :d", d=device)}
    return {"coins": int(coins), "today": int(earned) if eday == day else 0, "cap": DAILY_CAP,
            "owned": [s for s in owned if s in BY_ID], "equipped": {w: s for w, s in eq.items() if s in BY_ID}}


def award(device, kills, now=None):
    """Pay coins for kills. Returns {"earned","wanted","coins","today","cap"} or None (nothing to pay / no database)."""
    want = coins_for_kills(kills)
    if not enabled() or not device or want <= 0:
        return None
    day = today(now)

    def work(conn):
        coins, earned, eday = _lock_wallet(conn, device)
        granted, new_earned = grant(earned, eday, day, want)
        conn.run("UPDATE wallets SET coins = :c, earned_today = :e, earned_day = :day, updated_at = now() WHERE device_id = :d",
                 c=coins + granted, e=new_earned, day=day, d=device)
        return {"earned": granted, "wanted": want, "coins": coins + granted, "today": new_earned, "cap": DAILY_CAP}

    return _run(work, write=True)


def state(device, now=None):
    """Wallet, owned skins and equipped skins for one device, or None."""
    if not enabled() or not device:
        return None
    return _run(lambda conn: _snapshot(conn, device, today(now)))


def equipped(device):
    st = state(device)
    return st["equipped"] if st else {}


def buy(device, skin_id, now=None):
    """Spend coins on a skin (and put it on). Returns {"ok": bool, "error": str|None, "state": {...}|None}."""
    skin = BY_ID.get(skin_id)
    if not enabled() or not device or not skin:
        return {"ok": False, "error": "unavailable", "state": None}
    day = today(now)

    def work(conn):
        coins, _e, _d = _lock_wallet(conn, device)
        if conn.run("SELECT 1 FROM skins_owned WHERE device_id = :d AND skin_id = :s", d=device, s=skin_id):
            return {"ok": False, "error": "owned", "state": _snapshot(conn, device, day)}
        if coins < skin["price"]:
            return {"ok": False, "error": "coins", "state": _snapshot(conn, device, day)}
        conn.run("UPDATE wallets SET coins = coins - :p, updated_at = now() WHERE device_id = :d", p=skin["price"], d=device)
        conn.run("INSERT INTO skins_owned (device_id, skin_id) VALUES (:d, :s)", d=device, s=skin_id)
        conn.run("""INSERT INTO skins_equipped (device_id, weapon, skin_id) VALUES (:d, :w, :s)
                    ON CONFLICT (device_id, weapon) DO UPDATE SET skin_id = EXCLUDED.skin_id""", d=device, w=skin["wid"], s=skin_id)
        return {"ok": True, "error": None, "state": _snapshot(conn, device, day)}

    return _run(work, write=True) or {"ok": False, "error": "unavailable", "state": None}


def equip(device, skin_id=None, weapon=None, now=None):
    """Put an owned skin on (skin_id), or take the skin off a weapon (weapon = its id). Same return as buy()."""
    day = today(now)
    if not enabled() or not device:
        return {"ok": False, "error": "unavailable", "state": None}
    if skin_id is not None and skin_id not in BY_ID:
        return {"ok": False, "error": "unavailable", "state": None}

    def work(conn):
        if skin_id is not None:
            if not conn.run("SELECT 1 FROM skins_owned WHERE device_id = :d AND skin_id = :s", d=device, s=skin_id):
                return {"ok": False, "error": "not_owned", "state": _snapshot(conn, device, day)}
            conn.run("""INSERT INTO skins_equipped (device_id, weapon, skin_id) VALUES (:d, :w, :s)
                        ON CONFLICT (device_id, weapon) DO UPDATE SET skin_id = EXCLUDED.skin_id""",
                     d=device, w=BY_ID[skin_id]["wid"], s=skin_id)
        elif isinstance(weapon, int) and weapon in WEAPON_ID.values():
            conn.run("DELETE FROM skins_equipped WHERE device_id = :d AND weapon = :w", d=device, w=weapon)
        return {"ok": True, "error": None, "state": _snapshot(conn, device, day)}

    return _run(work, write=True) or {"ok": False, "error": "unavailable", "state": None}


def view(device):
    """What the Store screen shows: wallet plus every skin with owned / equipped flags."""
    out = {"enabled": enabled(), "coins": 0, "today": 0, "cap": DAILY_CAP, "skins": []}
    st = state(device) if enabled() else None
    if enabled() and st is None:
        out["enabled"] = False                       # database unreachable right now
    if not out["enabled"]:
        return out
    owned, eq = set(st["owned"]), set(st["equipped"].values())
    out.update(coins=st["coins"], today=st["today"])
    out["skins"] = [dict(s, owned=s["id"] in owned, equipped=s["id"] in eq) for s in CATALOG]
    out["equipped"] = st["equipped"]
    return out
