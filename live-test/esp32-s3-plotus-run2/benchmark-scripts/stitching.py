"""GND stitching vias: DESK CopperPlaneEngine.synthesize_stitching_vias grid (5.08 mm) filtered against live tracks,
pads, vias, keep-outs and edge; vias 0.3 mm drill / 0.6 mm pad (frozen via geometry). Created with
pcb_PrimitiveVia.create(net, x, y, holeDiameter, diameter) (argument order verified in DESK INC-20261111-006).
Writes pcb/copper/stitching_vias.json."""
import sys, os, json, math
DESK = r"C:\nemotron test\Plotus\DESK"; sys.path.insert(0, DESK)
from desk.bridge import ex, guard
from desk.copper import CopperPlaneEngine
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"; G = guard("bb03148ad5ac7687"); M = 39.37007874
CLR = 8.0; VD = 0.6 * M; VH = 0.3 * M
tracks = ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l=>[l.net,l.startX,l.startY,l.endX,l.endY,l.lineWidth]);', window_id=W, timeout=120)
vias = ex(G + 'return (await eda.pcb_PrimitiveVia.getAll()).map(v=>[v.net,v.x,v.y,v.diameter]);', window_id=W, timeout=120)
dump = json.load(open(r"C:\nemotron test\Plotus\run2\ESP32-S3-Development\schematic\desk\state\pcb_dump.json", encoding="utf-8")); dump = dump.get("parts", dump)
plan = json.load(open(r"C:\nemotron test\Plotus\run2\ESP32-S3-Development\schematic\desk\placement.json", encoding="utf-8"))
obst = []  # component bodies (mm) as circles of their half-diagonal is too coarse; use pad-level checks below
for ref, c in dump.items():
    for p in c["pads"]:
        sh = p["shape"]; nums = [v for v in (sh or [])[1:3] if isinstance(v, (int, float))]
        r = (max(nums) / 2 if nums else 20) / M
        obst.append(((c["x"] + p["dx"]) / M, (c["y"] + p["dy"]) / M, r))
for h in [(3.5, 3.5), (3.5, 40.5), (64.0, 3.5), (64.0, 40.5)]: obst.append((h[0], h[1], 3.0))
cand = CopperPlaneEngine.synthesize_stitching_vias(tuple(plan["board_mm"]), obst, keepouts=plan["keepouts"] + plan.get("copper_keepouts", []), grid_spacing_mm=5.08, edge_setback_mm=1.6).via_locations
def seg_d(px, py, x1, y1, x2, y2):
    L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
    s = 0 if L2 == 0 else max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / L2))
    return math.hypot(px - (x1 + s * (x2 - x1)), py - (y1 + s * (y2 - y1)))
# component bodies: no via under parts (assembly / tented-via-under-part avoidance)
bodies = [((c["x"] + c["bbox"][0]) / M, (c["y"] + c["bbox"][2]) / M, (c["x"] + c["bbox"][1]) / M, (c["y"] + c["bbox"][3]) / M) for c in dump.values()]
ok = []
for (x, y) in cand:
    X, Y = x * M, y * M
    if any(seg_d(X, Y, t[1], t[2], t[3], t[4]) < VD / 2 + t[5] / 2 + CLR for t in tracks): continue
    if any(math.hypot(X - v[1], Y - v[2]) < VD / 2 + v[3] / 2 + CLR for v in vias): continue
    rot_bodies = False
    for (x0, y0, x1, y1) in bodies:
        if min(x0, x1) - 0.4 <= x <= max(x0, x1) + 0.4 and min(y0, y1) - 0.4 <= y <= max(y0, y1) + 0.4: rot_bodies = True; break
    if rot_bodies: continue
    ok.append((round(x, 2), round(y, 2)))
print("candidates", len(cand), "accepted", len(ok))
if "--dry" in sys.argv: print(ok); raise SystemExit(0)
ids = ex(G + 'const out=[]; for(const [x,y] of %s){ const v=await eda.pcb_PrimitiveVia.create("GND", x, y, %.3f, %.3f); out.push(v?v.getState_PrimitiveId():null);} return out;'
         % (json.dumps([[x * M, y * M] for x, y in ok]), VH, VD), window_id=W, timeout=600)
ex(G + 'return await eda.pcb_Document.save();', window_id=W, timeout=120)
os.makedirs(r"C:\nemotron test\Plotus\run2\ESP32-S3-Development\pcb\copper", exist_ok=True)
json.dump({"grid_mm": 5.08, "via_drill_mm": 0.3, "via_pad_mm": 0.6, "clearance_mil": CLR, "locations_mm": ok, "ids": ids},
          open(r"C:\nemotron test\Plotus\run2\ESP32-S3-Development\pcb\copper\stitching_vias.json", "w"), indent=1)
print("created", sum(1 for i in ids if i))
