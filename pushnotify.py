"""Link Strike - browser push notifications (used to announce that ALCATRAZ is open).

Needs three env vars (make them with gen_vapid.py): VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT
(a mailto: address). Without the keys push is simply off and the game works as before.

Storage: Postgres (same DATABASE_URL as the leaderboard) so subscriptions survive restarts.
Without a database they live in memory until the server restarts. Nothing here ever raises.
"""
import json
import os

import rankings

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "").strip() or "mailto:admin@example.com"
MAX_SUBS = 5000

_subs = {}          # endpoint -> subscription dict (memory copy / fallback)
_days = set()       # nights already announced (memory fallback)
_ready = False


def enabled():
    return bool(VAPID_PUBLIC and VAPID_PRIVATE)


# ---------------------------------------------------------------- pure rules (tested)
def clean_sub(raw):
    """A browser PushSubscription.toJSON() -> {"endpoint", "keys": {"p256dh", "auth"}} or None."""
    if not isinstance(raw, dict):
        return None
    ep, keys = raw.get("endpoint"), raw.get("keys")
    if not isinstance(ep, str) or not ep.startswith("https://") or len(ep) > 600:
        return None
    if not isinstance(keys, dict):
        return None
    p, a = keys.get("p256dh"), keys.get("auth")
    if not (isinstance(p, str) and isinstance(a, str) and 0 < len(p) <= 200 and 0 < len(a) <= 100):
        return None
    return {"endpoint": ep, "keys": {"p256dh": p, "auth": a}}


# ---------------------------------------------------------------- database (all of it, in one place)
def _ensure(conn):
    global _ready
    if _ready:
        return
    conn.run("""CREATE TABLE IF NOT EXISTS push_subs (
                    endpoint   TEXT PRIMARY KEY,
                    sub        TEXT NOT NULL,
                    device_id  TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""")
    conn.run("""CREATE TABLE IF NOT EXISTS push_nights (
                    night TEXT PRIMARY KEY,
                    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )""")
    _ready = True


def _db(fn):
    conn = rankings._connect()
    try:
        _ensure(conn)
        return fn(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------- public API
def add(raw, device=None):
    """Save a subscription. Returns True if it is stored."""
    sub = clean_sub(raw)
    if not sub:
        return False
    if sub["endpoint"] not in _subs and len(_subs) >= MAX_SUBS:
        return False
    _subs[sub["endpoint"]] = sub
    if rankings.enabled():
        try:
            _db(lambda c: c.run(
                """INSERT INTO push_subs (endpoint, sub, device_id) VALUES (:e, :s, :d)
                   ON CONFLICT (endpoint) DO UPDATE SET sub = EXCLUDED.sub, device_id = EXCLUDED.device_id""",
                e=sub["endpoint"], s=json.dumps(sub), d=device))
        except Exception as exc:
            print("pushnotify: could not save subscription (kept in memory only):", exc)
    return True


def remove(endpoint):
    _subs.pop(endpoint, None)
    if rankings.enabled():
        try:
            _db(lambda c: c.run("DELETE FROM push_subs WHERE endpoint = :e", e=endpoint))
        except Exception as exc:
            print("pushnotify: could not delete subscription:", exc)


def all_subs():
    if rankings.enabled():
        try:
            rows = _db(lambda c: c.run("SELECT sub FROM push_subs"))
            return [json.loads(r[0]) for r in rows]
        except Exception as exc:
            print("pushnotify: could not read subscriptions (using memory):", exc)
    return list(_subs.values())


def claim_night(night):
    """True only the first time a night is claimed (survives restarts with a database), so a
    restart in the middle of the night can't send the announcement twice."""
    if rankings.enabled():
        try:
            rows = _db(lambda c: c.run(
                "INSERT INTO push_nights (night) VALUES (:n) ON CONFLICT DO NOTHING RETURNING night", n=night))
            return bool(rows)
        except Exception as exc:
            print("pushnotify: could not claim night (using memory):", exc)
    if night in _days:
        return False
    _days.add(night)
    return True


def send_all(title, body, url="/"):
    """Send one notification to every subscriber. Dead subscriptions (404/410) are deleted. Returns how many went out."""
    if not enabled():
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except Exception as exc:
        print("pushnotify: pywebpush is not installed:", exc)
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    for sub in all_subs():
        try:
            webpush(subscription_info=sub, data=payload, vapid_private_key=VAPID_PRIVATE,
                    vapid_claims={"sub": VAPID_SUBJECT}, ttl=3600)
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                remove(sub["endpoint"])
            else:
                print("pushnotify: send failed:", exc)
        except Exception as exc:
            print("pushnotify: send failed:", exc)
    return sent
