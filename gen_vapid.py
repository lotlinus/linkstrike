"""Run once on your computer:  python gen_vapid.py
Prints the two keys for browser push. Put them in Render > Environment as VAPID_PUBLIC_KEY and
VAPID_PRIVATE_KEY (keep the private one secret), plus VAPID_SUBJECT = mailto:you@example.com
Needs:  pip install cryptography
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
key = ec.generate_private_key(ec.SECP256R1())
priv = key.private_numbers().private_value.to_bytes(32, "big")
pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print("VAPID_PUBLIC_KEY =", b64(pub))
print("VAPID_PRIVATE_KEY =", b64(priv))
