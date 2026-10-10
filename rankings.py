"""Link Strike v0.7.2 - global leaderboard.

Ranking: total kills, wins break ties. Only FINISHED matches with MIN_PLAYERS or more count.
Players are identified by an anonymous device id (kept in the browser); the name is only a label.
Storage is Postgres (Neon) via the DATABASE_URL env var. Without it, or if the database is
unreachable, every function degrades quietly so the game itself never breaks.
"""
import os
import re
import time
from urllib.parse import unquote, urlparse

MIN_PLAYERS = 3          # a match needs at least this many players to count
TOP_CARD = 3             # rows on the landing page card
TOP_ALL = 20             # rows behind "View all"
DEVICE_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
DB_TIMEOUT = 5           # seconds; Neon can take a moment to wake from idle
CACHE_S = 5              # top-list cache, protects the database from refresh spam

_ready = False           # table is known to exist
_cache = {}              # limit -> (time, rows)


# ---------------------------------------------------------------- pure rules (tested)
def clean_device(raw):
    d = str(raw or "").strip()
    return d if DEVICE_RE.match(d) else None


def build_results(entries, winner_id, min_players=MIN_PLAYERS, ranked_win=True):
    """entries: [{"id": slot, "device": str|None, "name": str, "kills": int}] for everyone in the
    finished match. Returns a list of {"device","name","kills","won"} to save, or [] if the match
    doesn't count (too few players, no winner). ranked_win=False (team matches): kills are saved,
    nobody is credited a win, and no single winner is needed."""
    if len(entries) < min_players:
        return []
    if ranked_win and (winner_id is None or winner_id < 0):
        return []
    out = []
    for e in entries:
        if not e.get("device"):
            continue
        out.append({
            "device": e["device"],
            "name": e["name"],
            "kills": max(0, int(e["kills"])),
            "won": ranked_win and e["id"] == winner_id,
        })
    return out


# ---------------------------------------------------------------- database
def enabled():
    return bool(os.environ.get("DATABASE_URL", "").strip())


def _connect():
    import pg8000.native

    u = urlparse(os.environ["DATABASE_URL"].strip())
    return pg8000.native.Connection(
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname,
        port=u.port or 5432,
        database=(u.path or "/").lstrip("/") or "postgres",
        ssl_context=True,
        timeout=DB_TIMEOUT,
    )


def _ensure(conn):
    global _ready
    if _ready:
        return
    conn.run(
        """CREATE TABLE IF NOT EXISTS players (
               device_id  TEXT PRIMARY KEY,
               name       TEXT NOT NULL,
               kills      INTEGER NOT NULL DEFAULT 0,
               wins       INTEGER NOT NULL DEFAULT 0,
               matches    INTEGER NOT NULL DEFAULT 0,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )
    conn.run("CREATE INDEX IF NOT EXISTS players_rank_idx ON players (kills DESC, wins DESC, created_at)")
    _ready = True


def record_match(results):
    """Save one finished match. Returns True on success. Never raises."""
    if not enabled() or not results:
        return False
    conn = None
    try:
        conn = _connect()
        _ensure(conn)
        conn.run("BEGIN")
        for r in results:
            conn.run(
                """INSERT INTO players (device_id, name, kills, wins, matches)
                   VALUES (:d, :n, :k, :w, 1)
                   ON CONFLICT (device_id) DO UPDATE SET
                       name = EXCLUDED.name,
                       kills = players.kills + EXCLUDED.kills,
                       wins = players.wins + EXCLUDED.wins,
                       matches = players.matches + 1,
                       updated_at = now()""",
                d=r["device"], n=r["name"], k=r["kills"], w=1 if r["won"] else 0,
            )
        conn.run("COMMIT")
        _cache.clear()
        return True
    except Exception as exc:  # database down, sleeping, bad URL... the game goes on
        print("rankings: could not save match:", exc)
        try:
            conn and conn.run("ROLLBACK")
        except Exception:
            pass
        return False
    finally:
        try:
            conn and conn.close()
        except Exception:
            pass


def _row(r):
    return {"rank": int(r[0]), "name": r[1], "kills": int(r[2]), "wins": int(r[3])}


def leaderboard(limit, device=None):
    """Returns {"enabled": bool, "top": [...], "me": {...}|None}. Never raises."""
    out = {"enabled": enabled(), "top": [], "me": None}
    if not out["enabled"]:
        return out
    limit = TOP_ALL if limit >= TOP_ALL else TOP_CARD
    conn = None
    try:
        hit = _cache.get(limit)
        conn = None
        if hit and time.time() - hit[0] < CACHE_S:
            out["top"] = hit[1]
        if not out["top"] or device:
            conn = _connect()
            _ensure(conn)
        if conn and not out["top"]:
            rows = conn.run(
                """SELECT RANK() OVER (ORDER BY kills DESC, wins DESC), name, kills, wins
                   FROM players ORDER BY kills DESC, wins DESC, created_at ASC LIMIT :n""",
                n=limit,
            )
            out["top"] = [_row(r) for r in rows]
            _cache[limit] = (time.time(), out["top"])
        if conn and device:
            rows = conn.run(
                """SELECT (SELECT COUNT(*) FROM players o
                           WHERE o.kills > p.kills OR (o.kills = p.kills AND o.wins > p.wins)) + 1,
                          name, kills, wins
                   FROM players p WHERE device_id = :d""",
                d=device,
            )
            out["me"] = _row(rows[0]) if rows else None
    except Exception as exc:
        print("rankings: could not read leaderboard:", exc)
        out["top"], out["me"] = [], None
    finally:
        try:
            conn and conn.close()
        except Exception:
            pass
    return out
