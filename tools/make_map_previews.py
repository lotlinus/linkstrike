"""Rebuild the lobby map previews (static/img/map_*.jpg) from the REAL maps.

It draws each map with the game's own tile / prop / sky code (copied straight out of static/game.js),
so the preview always matches what players fly through. Run it again whenever a map or its art changes.

One-time setup (in this tools/ folder):   npm i canvas        and        pip install pillow
Then, from the repo root:                 python tools/make_map_previews.py
"""
import json, os, subprocess, sys, tempfile
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
import game as G

OUT_W, OUT_H = 1100, 605          # same shape as the 3200x1760 world
tmp = tempfile.mkdtemp()
for mid in G.MAPS:
    with open(os.path.join(tmp, f"world_{mid}.json"), "w") as f:
        json.dump(G.world_payload(mid), f)
env = dict(os.environ, NODE_PATH=os.path.join(ROOT, "tools", "node_modules"))
subprocess.run(["node", os.path.join(ROOT, "tools", "render_map_previews.js"), ROOT, tmp, tmp], check=True, env=env)
for mid in G.MAPS:
    im = Image.open(os.path.join(tmp, f"full_{mid}.png")).convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS)
    dest = os.path.join(ROOT, "static", "img", f"map_{mid}.jpg")
    im.save(dest, quality=85, optimize=True)
    print("wrote", dest, os.path.getsize(dest) // 1024, "KB")
print("Now bump the ?v= number on the map images in static/game.js (MAP_UI) so browsers fetch the new files.")
