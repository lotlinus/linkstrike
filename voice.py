"""Link Strike - voice chat passes (stdlib only, tested).

Voice runs on LiveKit Cloud. The game server never touches audio; it only hands each player in a
room a short-lived pass (a signed token) that lets that one player join that one voice room.
Set LIVEKIT_URL (wss://...), LIVEKIT_API_KEY and LIVEKIT_API_SECRET to switch voice on.
"""
import base64
import hashlib
import hmac
import json
import os
import time

TTL_SECONDS = 6 * 3600


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def settings():
    """(url, key, secret) when voice is configured, else None."""
    url = os.environ.get("LIVEKIT_URL", "").strip()
    key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    return (url, key, secret) if url and key and secret else None


def make_token(key, secret, room, identity, name, now=None, ttl=TTL_SECONDS):
    now = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "iss": key, "sub": identity, "name": name, "nbf": now, "exp": now + ttl,
        "video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True,
                  "canPublishData": False, "canPublishSources": ["microphone"]},
    }
    body = _b64(json.dumps(header, separators=(",", ":")).encode()) + "." + _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return body + "." + _b64(sig)
