"""Run 2b Stage 5: place every top designator clear of pads, part bodies, holes, the board edge and other text.
Geometry comes from the LIVE text box (eda.pcb_Primitive.getPrimitivesBBox), not from a guessed font metric:
with alignMode 3 the anchor (x, y) is the box's min corner at rot 0 (box = [x, y, x+w, y+h]) and at rot -90 the
box is [x, y-w, x+h, y] (both measured on C1 / U3 in this session).
Height 36 mil = 0.91 mm (>= 0.8 mm), stroke 6 mil = 0.15 mm.
Usage: python silk_place.py [--dry]  -> pcb/silk/silk_place.json"""
import sys, json, os
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.bridge import ex, guard
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import box
from shapely.ops import unary_union
G = guard("bb03148ad5ac7687"); W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"
FS, LW, PADCLR = 36.0, 6.0, 0.15
dry = "--dry" in sys.argv
ROOT = r"C:\nemotron test\Plotus\run2\ESP32-S3-Development"
dump = json.load(open(ROOT + r"\schematic\desk\state\pcb_dump.json", encoding="utf-8")); dump = dump.get("parts", dump)
bw, bh = json.load(open(ROOT + r"\schematic\desk\placement.json", encoding="utf-8"))["board_mm"]
des = ex(G + r'''const a=(await eda.pcb_PrimitiveAttribute.getAll()).filter(x=>x.key=="Designator"&&x.valueVisible&&x.layer==3);
const o=[]; for(const d of a){ o.push([d.primitiveId,d.value,d.x,d.y,d.fontSize,d.rotation,await eda.pcb_Primitive.getPrimitivesBBox([d.primitiveId])]); } return o;''', window_id=W, timeout=120)
pads = []
for ref, c in dump.items():
    for p in c["pads"]:
        if p.get("layer") == 2: continue      # bottom-only pads are not under top silk; top SMD + THT pads are
        q = {"x": c["x"] + p["dx"], "y": c["y"] + p["dy"], "rot": p.get("rot", 0), "shape": p["shape"]}
        pads.append(pad_geometry(q).buffer(PADCLR))
pad_u = unary_union(pads)
bodies = {ref: box((c["x"] + c["bbox"][0]) / MIL, (c["y"] + c["bbox"][2]) / MIL, (c["x"] + c["bbox"][1]) / MIL, (c["y"] + c["bbox"][3]) / MIL) for ref, c in dump.items()}
board = box(0.4, 0.4, bw - 0.4, bh - 0.4)
holes = unary_union([box(x - 1.9, y - 1.9, x + 1.9, y + 1.9) for x, y in [(3.5, 3.5), (3.5, 40.5), (64.0, 3.5), (64.0, 40.5)]])
items = []
for pid, ref, x, y, fs, rot, bb in des:
    w, h = (bb["maxX"] - bb["minX"]) / MIL, (bb["maxY"] - bb["minY"]) / MIL
    if abs(abs(rot or 0) - 90) < 1: w, h = h, w
    k = FS / fs; items.append({"id": pid, "ref": ref, "w": w * k, "h": h * k})

def text_box(cx, cy, w, h, r):         # centre-based candidate -> (box, anchor)
    if r == 0:
        b = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2); return b, (cx - w / 2, cy - h / 2)
    b = box(cx - h / 2, cy - w / 2, cx + h / 2, cy + w / 2); return b, (cx - h / 2, cy + w / 2)

def candidates(it):
    bd = bodies.get(it["ref"]); x0, y0, x1, y1 = bd.bounds; mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for gap in (0.15, 0.4, 0.8, 1.3, 2.0):
        for r in (0, -90):
            tw, th = (it["w"], it["h"]) if r == 0 else (it["h"], it["w"])
            pos = [(mx, y1 + gap + th / 2), (mx, y0 - gap - th / 2), (x0 - gap - tw / 2, my), (x1 + gap + tw / 2, my),
                   (x0 + tw / 2, y1 + gap + th / 2), (x1 - tw / 2, y1 + gap + th / 2), (x0 + tw / 2, y0 - gap - th / 2), (x1 - tw / 2, y0 - gap - th / 2)]
            for i, (cx, cy) in enumerate(pos):
                out.append((gap * 10 + i + (0 if r == 0 else 3), cx, cy, r))
    if it["ref"] == "U3":   # the module's own body is a fine label spot (shield area, no pads)
        out.append((0.5, mx - 6, my, 0))
    return sorted(out)

placed = []      # (ref, box)
def ok(it, b):
    if not board.contains(b) or b.intersects(pad_u) or b.intersects(holes): return False
    if any(b.intersects(bb) for r, bb in bodies.items() if r != it["ref"]): return False
    if it["ref"] != "U3" and b.intersects(bodies[it["ref"]]): return False
    return not any(b.distance(pb) < 0.15 for _, pb in placed)

feas = {it["ref"]: sum(ok(it, text_box(cx, cy, it["w"], it["h"], r)[0]) for _, cx, cy, r in candidates(it)) for it in items}
res, fail = [], []
for it in sorted(items, key=lambda i: feas[i["ref"]]):
    pick = None
    for _, cx, cy, r in candidates(it):
        b, anc = text_box(cx, cy, it["w"], it["h"], r)
        if ok(it, b): pick = (b, anc, r); break
    if not pick: fail.append(it["ref"]); continue
    placed.append((it["ref"], pick[0]))
    res.append({"id": it["id"], "ref": it["ref"], "x": round(pick[1][0] * MIL, 2), "y": round(pick[1][1] * MIL, 2), "rot": pick[2],
                "box_mm": [round(v, 2) for v in pick[0].bounds]})
print(f"{len(items)} designators: placed {len(res)}, no spot: {fail}")
if dry: raise SystemExit(0)
r = ex(G + 'for(const p of %s){ await eda.pcb_PrimitiveAttribute.modify(p.id,{x:p.x,y:p.y,rotation:p.rot,fontSize:%s,lineWidth:%s,alignMode:3}); } return true;'
       % (json.dumps(res), FS, LW), window_id=W, timeout=300)
os.makedirs(ROOT + r"\pcb\silk", exist_ok=True)
json.dump({"font_mil": FS, "stroke_mil": LW, "pad_clearance_mm": PADCLR, "placed": res, "no_spot": fail}, open(ROOT + r"\pcb\silk\silk_place.json", "w"), indent=1)
print("modified", r)
