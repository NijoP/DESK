"""Run 2b Stage 4: every GND fill piece that has no pad/track anchor and only ONE via gets a second GND via
(pour pieces must not depend on a single via). The candidate is inside the piece (0.45 mm inset), clear of other-net
copper on the other layer (>= 0.2 mm) and as far as possible from the existing via (>= 2 mm).
Usage: python stitch_second_via.py snapshot.json [--dry]   -> pcb/copper/second_vias.json"""
import sys, json
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.copper_fill import compute_plane_fill, pad_geometry, MIL
from desk.bridge import ex, guard
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"; G = guard("bb03148ad5ac7687")
s = json.load(open(sys.argv[1])); dry = "--dry" in sys.argv
p = json.load(open(r"..\schematic\desk\placement.json", encoding="utf-8"))
kos = [k["rect_mm"] for k in p["keepouts"] + p["copper_keepouts"]]; bw, bh = p["board_mm"]
board = [(0, 0), (bw, 0), (bw, bh), (0, bh)]
gp = [pad_geometry(q) for q in s["pads"] if q["net"] == "GND"]
gt = [LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)]).buffer(t["w"] / MIL / 2) for t in s["tracks"] if t["net"] == "GND"]
gv = [(v["x"] / MIL, v["y"] / MIL) for v in s["vias"] if v["net"] == "GND"]
def obst(layer):
    g = [pad_geometry(q) for q in s["pads"] if q["net"] != "GND" and q["layer"] in (layer, 12)]
    g += [LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)]).buffer(t["w"] / MIL / 2) for t in s["tracks"] if t["net"] != "GND" and t["layer"] == layer]
    g += [Point(v["x"] / MIL, v["y"] / MIL).buffer(v["d"] / MIL / 2) for v in s["vias"] if v["net"] != "GND"]
    g += [Point(q["x"] / MIL, q["y"] / MIL).buffer(1.9) for q in s["pads"] if q.get("ref", "").startswith("MH")]
    return unary_union(g)
fills = {L: compute_plane_fill(L, "GND", board, s["pads"], s["tracks"], s["vias"], keepouts_mm=kos, clearance_mm=0.3)["polygons"] for L in (1, 2)}
new = []
for L in (1, 2):
    other = obst(3 - L)
    for i, g in enumerate(fills[L]):
        if any(g.intersects(x) for x in gp + gt): continue
        vs = [v for v in gv if g.intersects(Point(v).buffer(0.3))]
        if len(vs) != 1: continue
        inner = g.buffer(-0.45); x0, y0, x1, y1 = g.bounds; best = None
        for k in range(int((x1 - x0) / 0.25) + 1):
            for j in range(int((y1 - y0) / 0.25) + 1):
                c = Point(x0 + k * 0.25, y0 + j * 0.25)
                if not inner.contains(c) or c.buffer(0.3).distance(other) < 0.2: continue
                # the via must also land inside the other layer's GND copper
                if not any(f.buffer(-0.35).contains(c) for f in fills[3 - L]): continue
                d = c.distance(Point(vs[0]))
                if d >= 2.0 and (best is None or d > best[0]): best = (d, round(c.x, 3), round(c.y, 3))
        print(f"layer {L} piece {i} area {g.area:.1f} mm2 via {vs[0]} ->", best)
        if best: new.append([best[1], best[2]])
if not dry and new:
    ids = ex(G + 'const out=[]; for(const [x,y] of %s){ const v=await eda.pcb_PrimitiveVia.create("GND", x, y, %.3f, %.3f); out.push(v?v.getState_PrimitiveId():null);} return out;'
             % (json.dumps([[x * MIL, y * MIL] for x, y in new]), 0.3 * MIL, 0.6 * MIL), window_id=W, timeout=300)
    json.dump({"why": "second via for single-via GND fill pieces", "locations_mm": new, "ids": ids},
              open(r"..\pcb\copper\second_vias.json", "w"), indent=1)
    print("created", sum(1 for i in ids if i))
