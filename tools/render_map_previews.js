// Run it through tools/make_map_previews.py. Renders the real map (same tile / prop / sky code as static/game.js) to a full-size PNG for the lobby preview.
const fs = require("fs"), path = require("path");
const { createCanvas, loadImage } = require("canvas");
const REPO = process.argv[2], OUT = process.argv[3], WORLDS = process.argv[4] || OUT;
const src = fs.readFileSync(path.join(REPO, "static/game.js"), "utf8");
const a = src.indexOf("  const T = 40;");
const b = src.indexOf("  // ---- jetpack thrust");
if (a < 0 || b < 0) throw new Error("markers not found");
let region = src.slice(a, b);
// the region declares  const ctx = canvas.getContext("2d")  — expose what we need after it runs
const maker = new Function("canvas", "document", "world", "LAB", "ART", "cam", "clamp", "latest", "now",
  region + "\n return { buildTiles, drawSky, drawTiles, drawProps, drawPickups, ctx: ctx, getTiles: () => tiles };");

(async () => {
  const W = 3200, H = 1760;
  for (const id of ["lab", "street", "stairs"]) {
    const world = JSON.parse(fs.readFileSync(path.join(WORLDS, `world_${id}.json`)));
    const LAB = {}, ART = {};
    const load = async (dir, n, into) => { try { into[n] = await loadImage(path.join(REPO, "static/img", dir, n + ".png")); } catch (e) {} };
    const LAB_FILES = ["floor_plain","floor_hazard","wall_light","wall_cable","wall_warn","plat_long","door_open","tank_green","tank_blue","tank_small","term_rack","term_desk","term_kiosk","term_arcade","term_a","light_cyan","light_amber","light_red","pipe_long","pipe_bundle","pk_shotgun","pk_rocket","pk_health"];
    await Promise.all(LAB_FILES.map((n) => load("lab", n, LAB)));
    if (world.art === "street") await Promise.all([...new Set(world.props.map((p) => p[0]))].map((n) => load("street", n, ART)));
    const canvas = createCanvas(W, H);
    const cam = { x: W / 2, y: H / 2 };
    const latest = { k: world.pickups.map(() => 1) };
    const document = { createElement: () => createCanvas(1, 1) };
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const R = maker(canvas, document, world, LAB, ART, cam, clamp, latest, 0);
    R.buildTiles();
    const ctx = R.ctx;
    ctx.imageSmoothingEnabled = false;
    R.drawSky(W, H, 1);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    R.drawTiles(0, 0, W, H, 0);
    R.drawProps();
    R.drawTiles(0, 0, W, H, 1);
    R.drawPickups(0);
    fs.writeFileSync(path.join(OUT, `full_${id}.png`), canvas.toBuffer("image/png"));
    console.log("rendered", id, "props", (world.props || []).length, "art loaded", Object.keys(ART).length, "lab", Object.keys(LAB).length);
  }
})().catch((e) => { console.error(e); process.exit(1); });
