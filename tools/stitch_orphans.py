"""Connect orphaned plane-net copper with clearance-checked vias (companion of tools/copper_fill.py).
- every top/bottom plane fill piece (state/copper_fills.json readback) without a plane-net via gets one at its
  pole of inaccessibility (shapely polylabel) if the via fits inside the piece;
- every plane-net SMD pad on a layer whose fill does not reach it gets a via on the nearest free spot
  (ring search 0.6..2.0 mm, clear of other-net copper by --clearance) plus a straight track pad->via.
- every via made for an orphan PAD also gets an explicit bottom-layer track to the nearest existing plane-net via
  (straight, clearance-checked, <= 10 mm), because EasyEDA's DRC does not reliably join a via to a static
  pcb_PrimitiveFill (see desk.copper_fill.explicit_link). Disable with --no-link.
Then re-run tools/copper_fill.py so both planes absorb the new vias.
Usage: python tools/stitch_orphans.py projects/<P> [--net GND] [--clearance 0.2] [--force-pads R2.2,C8.2] [--no-link] [--dry]"""
import sys, os, json, math
from _common import ex, guard, load_project, check
from desk.copper_fill import compute_plane_fill, pad_geometry, explicit_link, MIL

args = sys.argv[1:]
proj = args[0]
net = args[args.index("--net") + 1] if "--net" in args else "GND"
clr = float(args[args.index("--clearance") + 1]) if "--clearance" in args else 0.2
dry = "--dry" in args
link = "--no-link" not in args
force = set(args[args.index("--force-pads") + 1].split(",")) if "--force-pads" in args else set()   # e.g. R2.2,C8.2 (DRC-reported opens)
VD, VH, TW = 0.6, 0.3, 0.25   # via pad / drill / track width (mm)
from shapely.geometry import Point, LineString, box, Polygon
from shapely.ops import unary_union, polylabel
P = load_project(proj); W = P.get("window_id"); G = guard(P["pcb_uuid"])
plan = json.load(open(os.path.join(proj, "placement.json"), encoding="utf-8"))
bw, bh = plan["board_mm"]; board = [(0, 0), (bw, 0), (bw, bh), (0, bh)]
kos = [k["rect_mm"] for k in plan.get("keepouts", []) + plan.get("copper_keepouts", []) if "rect_mm" in k]
pads = check(ex(G + '''const out=[]; const cs=await eda.pcb_PrimitiveComponent.getAll();
for(const c of cs){ const ps=await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId())||[];
 for(const p of ps){ out.push({ref:c.getState_Designator(),num:p.getState_PadNumber(),net:p.getState_Net(),x:p.getState_X(),y:p.getState_Y(),rot:p.getState_Rotation(),shape:p.getState_Pad(),layer:p.getState_Layer()}); } }
const seen=new Set(out.map(q=>q.x+','+q.y+','+q.num)); const fp=await eda.pcb_PrimitivePad.getAll(); for(const p of fp){ if(seen.has(p.getState_X()+','+p.getState_Y()+','+p.getState_PadNumber())) continue; out.push({ref:"FREE",num:p.getState_PadNumber(),net:p.getState_Net(),x:p.getState_X(),y:p.getState_Y(),rot:p.getState_Rotation(),shape:p.getState_Pad(),layer:p.getState_Layer()}); }
return out;''', window_id=W, timeout=300))
tracks = check(ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l=>({net:l.net,x1:l.startX,y1:l.startY,x2:l.endX,y2:l.endY,w:l.lineWidth,layer:l.layer}));', window_id=W, timeout=120))
vias = check(ex(G + 'return (await eda.pcb_PrimitiveVia.getAll()).map(v=>({net:v.net,x:v.x,y:v.y,d:v.diameter}));', window_id=W, timeout=120))
def other_copper(layer):
    g = []
    for p in pads:
        if p["net"] != net and p["layer"] in (layer, 12): g.append(pad_geometry(p))
    for t in tracks:
        if t["net"] != net and t["layer"] == layer:
            g.append(LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)]).buffer(t["w"] / MIL / 2))
    for v in vias:
        if v["net"] != net: g.append(Point(v["x"] / MIL, v["y"] / MIL).buffer(v["d"] / MIL / 2))
    for k in kos: g.append(box(*k))
    return unary_union(g)
oth = {1: other_copper(1), 2: other_copper(2)}
blocked_both = unary_union([oth[1], oth[2], Polygon(board).exterior.buffer(0.8)])   # via is on both layers
own_vias = [Point(v["x"] / MIL, v["y"] / MIL) for v in vias if v["net"] == net]
new_vias, new_tracks = [], []
fills = {L: compute_plane_fill(L, net, board, pads, tracks, vias, keepouts_mm=kos)["polygons"] for L in (1, 2)}
def via_ok(pt):
    return pt.buffer(VD / 2 + clr).intersection(blocked_both).is_empty and all(pt.distance(q) > VD + clr for q in own_vias + [Point(x, y) for x, y in new_vias])
# 1) fill pieces without a plane-net via
for L in (1, 2):
    for poly in fills[L]:
        if any(poly.contains(v) for v in own_vias + [Point(x, y) for x, y in new_vias]):
            continue
        c = polylabel(poly, tolerance=0.05)
        if poly.exterior.distance(c) >= VD / 2 + 0.05 and via_ok(c):
            new_vias.append((round(c.x, 3), round(c.y, 3)))
# 2) plane-net SMD pads not touched by a CONNECTED piece of their layer's fill (a piece is connected when it holds a
#    plane-net via or touches a plane-net through-hole pad); orphan slivers too thin for a via do not count.
th_gnd = [pad_geometry(q) for q in pads if q["net"] == net and q["layer"] == 12]
def connected(poly):
    vs = own_vias + [Point(x, y) for x, y in new_vias]
    return any(poly.contains(v) for v in vs) or any(poly.intersects(t) for t in th_gnd)
done = set()
own_tracks = {L: [LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)]).buffer(t["w"] / MIL / 2)
                  for t in tracks if t["net"] == net and t["layer"] == L] for L in (1, 2)}
for p in pads:
    if p["net"] != net or p["layer"] not in (1, 2): continue
    key = (round(p["x"], 1), round(p["y"], 1)); 
    if key in done: continue
    done.add(key)
    g = pad_geometry(p)
    if f'{p["ref"]}.{p["num"]}' not in force and any(f.intersects(g) and connected(f) for f in fills[p["layer"]]): continue
    if f'{p["ref"]}.{p["num"]}' not in force and any(t.intersects(g) for t in own_tracks[p["layer"]]): continue   # already tracked
    c = g.centroid; best = None
    for r in [0.6 + 0.1 * i for i in range(25)]:
        for k in range(24):
            a = 2 * math.pi * k / 24; pt = Point(c.x + r * math.cos(a), c.y + r * math.sin(a))
            if not via_ok(pt): continue
            tr = LineString([(c.x, c.y), (pt.x, pt.y)]).buffer(TW / 2)
            if not tr.buffer(clr).intersection(oth[p["layer"]]).is_empty: continue
            best = pt; break
        if best: break
    if best is None:
        print("NO SPOT for", p["ref"], p["num"]); continue
    new_vias.append((round(best.x, 3), round(best.y, 3))); new_tracks.append((p["layer"], c.x, c.y, best.x, best.y, f'{p["ref"]}.{p["num"]}'))
    if link:
        tgt = explicit_link((best.x, best.y), [(q.x, q.y) for q in own_vias], oth[2], clr, TW)
        if tgt is None:
            print("NO EXPLICIT LINK for", p["ref"], p["num"], "(relies on the via-to-fill join; check DRC)")
        else:
            new_tracks.append((2, best.x, best.y, tgt[0], tgt[1], f'{p["ref"]}.{p["num"]}:link'))
print("new vias", len(new_vias), "new tracks", len(new_tracks), [t[5] for t in new_tracks])
if not dry and new_vias:
    ids = check(ex(G + 'const o=[]; for(const [x,y] of %s){ const v=await eda.pcb_PrimitiveVia.create(%s,x,y,%.3f,%.3f); o.push(v?v.getState_PrimitiveId():null);} return o;'
                   % (json.dumps([[x * MIL, y * MIL] for x, y in new_vias]), json.dumps(net), VH * MIL, VD * MIL), window_id=W, timeout=300))
    tids = check(ex(G + 'const o=[]; for(const [l,x1,y1,x2,y2] of %s){ const t=await eda.pcb_PrimitiveLine.create(%s,l,x1,y1,x2,y2,%.3f); o.push(t?t.getState_PrimitiveId():null);} await eda.pcb_Document.save(); return o;'
                    % (json.dumps([[l, a * MIL, b * MIL, c * MIL, d * MIL] for l, a, b, c, d, _ in new_tracks]), json.dumps(net), TW * MIL), window_id=W, timeout=300))
    rec = os.path.join(proj, "state", "orphan_stitch.json")
    json.dump({"vias_mm": new_vias, "tracks": new_tracks, "via_ids": ids, "track_ids": tids}, open(rec, "w"), indent=1)
    print("created vias", sum(1 for i in ids if i), "tracks", sum(1 for i in tids if i))
