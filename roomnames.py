"""Link Strike - reserved room names.

A host can pick a room name (see app.py). The first device to use a name owns it for KEEP_DAYS
after its last use; only that device can open the room again once it empties.

Storage: Postgres (the same DATABASE_URL as the leaderboard) so names survive restarts and
sleeping free-tier servers. A small in-memory copy answers repeat lookups without touching the
database. Without DATABASE_URL, or if the database is unreachable, everything quietly falls
back to memory only (names then last until the server restarts) and the game keeps working.
"""
import time

import rankings

KEEP_DAYS = 30
KEEP_S = KEEP_DAYS * 24 * 3600
MISS_S = 30                 # remember "nobody owns this" briefly so typos don't hammer the database

_mem = {}                   # name -> (owner device, last used time)
_miss = {}                  # name -> time we found it unowned
_ready = False


# ---------------------------------------------------------------- database (all of it, in one place)
def _ensure(conn):
    global _ready
    if _ready:
        return
    conn.run(
        """CREATE TABLE IF NOT EXISTS room_names (
               name       TEXT PRIMARY KEY,
               device_id  TEXT NOT NULL,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )
    conn.run("CREATE INDEX IF NOT EXISTS room_names_device_idx ON room_names (device_id)")
    _ready = True


def _db_owner(name):
    """Owner device of a non-expired name, or None. Raises if the database fails."""
    conn = rankings._connect()
    try:
        _ensure(conn)
        rows = conn.run(
            f"SELECT device_id FROM room_names WHERE name = :n AND updated_at > now() - interval '{KEEP_DAYS} days'",
            n=name,
        )
        return rows[0][0] if rows else None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _db_claim(name, device):
    """Take the name if free (or already ours), refresh it, and drop this device's other names.
    Returns the device that owns the name afterwards. Raises if the database fails."""
    conn = rankings._connect()
    try:
        _ensure(conn)
        conn.run("BEGIN")
        try:
            conn.run(f"DELETE FROM room_names WHERE updated_at < now() - interval '{KEEP_DAYS} days'")
            conn.run(
                """INSERT INTO room_names (name, device_id) VALUES (:n, :d)
                   ON CONFLICT (name) DO UPDATE SET updated_at = now()
                   WHERE room_names.device_id = EXCLUDED.device_id""",
                n=name, d=device,
            )
            owner = conn.run("SELECT device_id FROM room_names WHERE name = :n", n=name)[0][0]
            if owner == device:
                conn.run("DELETE FROM room_names WHERE device_id = :d AND name <> :n", d=device, n=name)
            conn.run("COMMIT")
        except Exception:
            try:
                conn.run("ROLLBACK")
            except Exception:
                pass
            raise
        return owner
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------- public API (never raises)
def cached(name):
    """True if this name is known to be reserved right now (memory only, no database call)."""
    m = _mem.get(name)
    return bool(m and time.time() - m[1] <= KEEP_S)


def owner_of(name):
    """The device id that owns this room name, or None."""
    now = time.time()
    m = _mem.get(name)
    if m:
        if now - m[1] <= KEEP_S:
            return m[0]
        _mem.pop(name, None)
    if rankings.enabled():
        if now - _miss.get(name, -1e9) < MISS_S:
            return None
        try:
            owner = _db_owner(name)
        except Exception as exc:
            print("roomnames: could not read name:", exc)
            return None
        if owner:
            _mem[name] = (owner, now)
            _miss.pop(name, None)
        else:
            _miss[name] = now
        return owner
    return None


def claim(name, device):
    """Reserve (or refresh) name for device. Returns the owning device: `device` on success,
    someone else's id if they got it first. A device keeps only one name at a time."""
    now = time.time()
    owner = None
    if rankings.enabled():
        try:
            owner = _db_claim(name, device)
        except Exception as exc:
            print("roomnames: could not save name (kept in memory only):", exc)
    if owner is None:                                   # no database, or it failed: memory decides
        m = _mem.get(name)
        owner = m[0] if m and now - m[1] <= KEEP_S else device
    if owner == device:
        for k in [k for k, v in _mem.items() if v[0] == device and k != name]:
            del _mem[k]
    _mem[name] = (owner, now)
    _miss.pop(name, None)
    return owner
