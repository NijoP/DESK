"""Run 2b Stage 5: silkscreen branding + function labels (eda.pcb_PrimitiveString.create / modify, both [live]).
- top (layer 3): brand line; a net-function label next to every test point (D+, D-, 3V3 ...)
- bottom (layer 4, mirrored so it reads from the bottom): brand line; pin labels for headers J2 / J3, one per pin,
  rot -90 on the inboard side of the row.
Each string is created at its rotation/mirror, its LIVE box is measured (getPrimitivesBBox) and it is then moved to the
first candidate box clear of pads (+0.15 mm), holes, vias (+0.1 mm), part bodies (top), other texts (+0.15 mm), and
>= 0.4 mm inside the board. Height >= 0.91 mm, stroke 0.15 mm.
Usage: python silk_labels.py snapshot.json [--dry]  -> pcb/silk/silk_labels.json"""
import sys, json, os, re
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.bridge import ex, guard
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import box, Point
from shapely.ops import unary_union
G = guard("bb03148ad5ac7687"); W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"
ROOT = r"C:\nemotron test\Plotus\run2\ESP32-S3-Development"
s = json.load(open(sys.argv[1])); dry = "--dry" in sys.argv
dump = json.load(open(ROOT + r"\schematic\desk\state\pcb_dump.json", encoding="utf-8")); dump = dump.get("parts", dump)
board = box(0.4, 0.4, 73.6, 43.6)
holes = unary_union([Point(x, y).buffer(2.0) for x, y in [(3.5, 3.5), (3.5, 40.5), (64.0, 3.5), (64.0, 40.5)]])
pads = {3: unary_union([pad_geometry(p).buffer(0.15) for p in s["pads"] if p["layer"] in (1, 12)]),
        4: unary_union([pad_geometry(p).buffer(0.15) for p in s["pads"] if p["layer"] in (2, 12)])}
vias = unary_union([Point(v["x"] / MIL, v["y"] / MIL).buffer(v["d"] / MIL / 2 + 0.1) for v in s["vias"]])
bodies = unary_union([box((c["x"] + c["bbox"][0]) / MIL, (c["y"] + c["bbox"][2]) / MIL, (c["x"] + c["bbox"][1]) / MIL, (c["y"] + c["bbox"][3]) / MIL) for c in dump.values()])
texts = {3: [], 4: []}
for kind, layer, bb in ex(G + r'''const o=[];
for(const a of (await eda.pcb_PrimitiveAttribute.getAll()).filter(a=>a.key=="Designator"&&a.valueVisible)) o.push(["d",a.layer,await eda.pcb_Primitive.getPrimitivesBBox([a.primitiveId])]);
for(const a of await eda.pcb_PrimitiveString.getAll()) o.push(["s",a.getState_Layer(),await eda.pcb_Primitive.getPrimitivesBBox([a.getState_PrimitiveId()])]);
return o;''', window_id=W, timeout=180):
    texts.setdefault(layer, []).append(box(bb["minX"] / MIL, bb["minY"] / MIL, bb["maxX"] / MIL, bb["maxY"] / MIL))

SHORT = {"USB_DP": "D+", "USB_DN": "D-", "U0RXD": "RX", "U0TXD": "TX"}
def short(n): return SHORT.get(n) or re.sub(r"^GPIO", "IO", n)
jobs = []   # (text, layer, fs, rot, mirror, [candidate centres mm], allow_bodies)
jobs.append(("PLOTUS ESP32-S3 DEV  REV A", 3, 50, 0, False, [(cx, cy) for cy in (12.0, 14.0, 16.0, 10.0, 18.0, 30.0, 32.0) for cx in (30.0, 28.0, 32.0, 26.0, 34.0, 24.0, 36.0)], False))
jobs.append(("PLOTUS ESP32-S3 DEVKIT  REV A  2026-11", 4, 50, 0, True, [(cx, cy) for cy in (22.0, 20.0, 24.0, 18.0, 26.0, 16.0, 28.0) for cx in (33.0, 31.0, 35.0, 29.0, 37.0)], True))
for p in s["pads"]:
    if p["ref"].startswith("TP"):
        x, y = p["x"] / MIL, p["y"] / MIL
        c = [(x + dx, y + dy) for d in (2.2, 2.8, 3.4, 4.0) for dx, dy in ((0, d), (0, -d), (d, 0), (-d, 0), (d, d), (-d, d), (d, -d), (-d, -d))]
        jobs.append((short(p["net"]), 3, 36, 0, False, c, False))
for p in s["pads"]:
    if p["ref"] in ("J2", "J3"):
        x, y = p["x"] / MIL, p["y"] / MIL; sgn = -1 if y > 22 else 1      # inboard direction
        jobs.append((short(p["net"]), 4, 36, -90, True, [(x, y + sgn * (1.25 + k * 0.25)) for k in range(0, 12)], True))   # centre shifted later by half length

def measure(batch):
    js = 'const o=[]; for(const j of %s){ const t=await eda.pcb_PrimitiveString.create(j[1],0,0,j[0],"default",j[2],6,3,j[3],false,0,j[4],false); const id=t.getState_PrimitiveId(); o.push([id, await eda.pcb_Primitive.getPrimitivesBBox([id])]); } return o;'
    return ex(G + js % json.dumps([[j[0], j[1], j[2], j[3], j[4]] for j in batch]), window_id=W, timeout=300)

if dry:
    print(len(jobs), "labels planned:", [j[0] for j in jobs]); raise SystemExit(0)
made = measure(jobs)
moves, report, fail = [], [], []
for j, (pid, bb) in zip(jobs, made):
    text, layer, fs, rot, mir, cands, allow_bodies = j
    w, h = (bb["maxX"] - bb["minX"]) / MIL, (bb["maxY"] - bb["minY"]) / MIL
    ox, oy = bb["minX"] / MIL, bb["minY"] / MIL       # anchor (0,0) -> box min corner offset
    pick = None
    header = layer == 4 and rot == -90
    for cx, cy in cands:
        if header:     # candidate y = the box edge nearest the pin; the box grows inboard (towards the board centre)
            b = box(cx - w / 2, cy, cx + w / 2, cy + h) if cy < 22 else box(cx - w / 2, cy - h, cx + w / 2, cy)
        else:
            b = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        if not board.contains(b) or b.intersects(pads[layer]) or b.intersects(holes) or b.intersects(vias): continue
        if not allow_bodies and b.intersects(bodies): continue
        if any(b.distance(t) < 0.15 for t in texts[layer]): continue
        pick = b; break
    if pick is None:
        fail.append(text); moves.append({"id": pid, "delete": True}); continue
    texts[layer].append(pick)
    x0, y0 = pick.bounds[0], pick.bounds[1]
    moves.append({"id": pid, "x": round((x0 - ox) * MIL, 2), "y": round((y0 - oy) * MIL, 2)})
    report.append({"text": text, "layer": layer, "height_mm": round(fs / MIL, 3), "rot": rot, "mirror": mir, "box_mm": [round(v, 2) for v in pick.bounds]})
ex(G + 'for(const m of %s){ if(m.delete){ await eda.pcb_PrimitiveString.delete([m.id]); } else { await eda.pcb_PrimitiveString.modify(m.id,{x:m.x,y:m.y}); } } return true;' % json.dumps(moves), window_id=W, timeout=300)
os.makedirs(ROOT + r"\pcb\silk", exist_ok=True)
json.dump({"placed": report, "no_spot_deleted": fail}, open(ROOT + r"\pcb\silk\silk_labels.json", "w"), indent=1)
print(f"{len(jobs)} labels: placed {len(report)}, no spot (deleted): {fail}")
