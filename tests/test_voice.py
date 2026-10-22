"""voice.py: tokens verify with the secret, carry the right room/identity, and expire."""
import base64, hashlib, hmac, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import voice

def dec(part):
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

tok = voice.make_token("KEY", "SECRET", "ls-ALCATRAZ", "p2", "Lynx", now=1000, ttl=60)
h, c, s = tok.split(".")
want = base64.urlsafe_b64encode(hmac.new(b"SECRET", (h + "." + c).encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
assert s == want
claims = dec(c)
assert claims["iss"] == "KEY" and claims["sub"] == "p2" and claims["name"] == "Lynx"
assert claims["nbf"] == 1000 and claims["exp"] == 1060
assert claims["video"]["room"] == "ls-ALCATRAZ" and claims["video"]["roomJoin"] is True
assert claims["video"]["canPublishData"] is False
assert dec(h) == {"alg": "HS256", "typ": "JWT"}
for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
    os.environ.pop(k, None)
assert voice.settings() is None
os.environ.update(LIVEKIT_URL="wss://x.livekit.cloud", LIVEKIT_API_KEY="k", LIVEKIT_API_SECRET="s")
assert voice.settings() == ("wss://x.livekit.cloud", "k", "s")
print("voice ok")
