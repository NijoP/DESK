"""Run 2b Stage 5: silkscreen audit from LIVE readback (true text boxes from eda.pcb_Primitive.getPrimitivesBBox).
Every visible silkscreen text (designators + strings, top layer 3 / bottom layer 4) must be >= 0.8 mm tall, stay >= 0.4 mm
inside the board, keep >= 0.15 mm from every copper pad on its side and must not overlap another text on its side.
Usage: python silk_check.py snapshot.json [--json]   -> pcb/silk/silk_check.json"""
import sys, json, os
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.bridge import ex, guard
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import box
from shapely.ops import unary_union
G = guard("bb03148ad5ac7687"); W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"
s = json.load(open(sys.argv[1]))
rows = ex(G + r'''const o=[];
for(const a of (await eda.pcb_PrimitiveAttribute.getAll()).filter(a=>a.key=="Designator"&&a.valueVisible))
  o.push(["designator",a.primitiveId,a.value,a.layer,a.fontSize,a.lineWidth,await eda.pcb_Primitive.getPrimitivesBBox([a.primitiveId])]);
for(const a of await eda.pcb_PrimitiveString.getAll())
  o.push(["string",a.getState_PrimitiveId(),a.getState_Text(),a.getState_Layer(),a.getState_FontSize(),a.getState_LineWidth(),await eda.pcb_Primitive.getPrimitivesBBox([a.getState_PrimitiveId()])]);
return o;''', window_id=W, timeout=180)
pads = {3: unary_union([pad_geometry(p) for p in s["pads"] if p["layer"] in (1, 12)]),
        4: unary_union([pad_geometry(p) for p in s["pads"] if p["layer"] in (2, 12)])}
board = box(0.4, 0.4, 74.0 - 0.4, 44.0 - 0.4)
out = []
for kind, pid, text, layer, fs, lw, bb in rows:
    b = box(bb["minX"] / MIL, bb["minY"] / MIL, bb["maxX"] / MIL, bb["maxY"] / MIL)
    out.append({"kind": kind, "id": pid, "text": text, "layer": layer, "height_mm": round(fs / MIL, 3), "stroke_mm": round(lw / MIL, 3),
                "box_mm": [round(v, 2) for v in b.bounds], "pad_gap_mm": round(b.distance(pads[layer]), 3) if layer in pads else None,
                "on_board": board.contains(b), "_b": b})
for r in out:
    r["overlaps_text"] = [q["text"] for q in out if q is not r and q["layer"] == r["layer"] and q["_b"].intersects(r["_b"])]
bad = [r for r in out if r["height_mm"] < 0.8 or (r["pad_gap_mm"] is not None and r["pad_gap_mm"] < 0.15) or not r["on_board"] or r["overlaps_text"]]
for r in out: r.pop("_b")
print(f"{len(out)} visible silkscreen texts; min height {min(r['height_mm'] for r in out)} mm; min pad gap {min(r['pad_gap_mm'] for r in out if r['pad_gap_mm'] is not None)} mm; issues {len(bad)}")
for r in bad: print("  ", r)
if "--json" in sys.argv:
    os.makedirs(r"..\pcb\silk", exist_ok=True)
    json.dump({"rule": "height >= 0.8 mm, pad gap >= 0.15 mm, >= 0.4 mm inside board, no text overlap", "texts": out, "issues": bad},
              open(r"..\pcb\silk\silk_check.json", "w"), indent=1)
    print("PASS" if not bad else "FAIL")
