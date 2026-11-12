"""API-only copper planes (no GUI "Rebuild copper" click): computes plane copper with desk/copper_fill.py from live
readback and writes it as pcb_PrimitiveFill polygons on the plane net. Re-run after any routing change (it first
deletes the fills it created earlier, recorded in state/copper_fills.json).
Usage: python tools/copper_fill.py projects/<P> [--net GND] [--layers 1,2] [--clearance 0.3] [--dry] [--remove]
--remove: only delete the fills recorded in state/copper_fills.json (pour AFTER routing: EasyEDA exports
          existing fills into the DSN as pseudo-pins and Freerouting 2.1 cannot load them, UPS_1000 F-010).
Board polygon = placement.json board_mm rectangle; keep-outs = placement.json keepouts (antenna, holes) + copper_keepouts (copper-only, e.g. footprint slot regions
that pad readback does not expose)."""
import sys, os, json
from _common import ex, guard, load_project, check
from desk.copper_fill import compute_plane_fill, polygon_to_easyeda_complex

args = sys.argv[1:]
if not args or args[0].startswith("-"):
    raise SystemExit(__doc__)
proj = args[0]
net = args[args.index("--net") + 1] if "--net" in args else "GND"
layers = [int(x) for x in (args[args.index("--layers") + 1] if "--layers" in args else "1,2").split(",")]
clr = float(args[args.index("--clearance") + 1]) if "--clearance" in args else 0.3
dry = "--dry" in args
P = load_project(proj); W = P.get("window_id"); G = guard(P["pcb_uuid"])
plan = json.load(open(os.path.join(proj, "placement.json"), encoding="utf-8"))
bw, bh = plan.get("board_mm", [50, 50]); ox, oy = plan.get("origin_mm", [0, 0])
board = [(ox, oy), (ox + bw, oy), (ox + bw, oy + bh), (ox, oy + bh)]
kos = [k["rect_mm"] for k in plan.get("keepouts", []) + plan.get("copper_keepouts", []) if "rect_mm" in k]
state_f = os.path.join(proj, "state", "copper_fills.json")
old = json.load(open(state_f)) if os.path.exists(state_f) else {"ids": []}
if old["ids"] and not dry:
    check(ex(G + 'await eda.pcb_PrimitiveFill.delete(%s); return true;' % json.dumps(old["ids"]), window_id=W, timeout=120))
if "--remove" in args:
    if not dry:
        old["ids"] = []; old["layers"] = {}
        json.dump(old, open(state_f, "w"), indent=1)
    print(json.dumps({"removed": not dry, "state": state_f}))
    sys.exit(0)
pads = check(ex(G + '''const out=[]; const cs=await eda.pcb_PrimitiveComponent.getAll();
for(const c of cs){ const ps=await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId())||[];
 for(const p of ps){ out.push({ref:c.getState_Designator(),num:p.getState_PadNumber(),net:p.getState_Net(),x:p.getState_X(),y:p.getState_Y(),rot:p.getState_Rotation(),shape:p.getState_Pad(),layer:p.getState_Layer()}); } }
const seen=new Set(out.map(q=>q.x+','+q.y+','+q.num)); const fp=await eda.pcb_PrimitivePad.getAll(); for(const p of fp){ if(seen.has(p.getState_X()+','+p.getState_Y()+','+p.getState_PadNumber())) continue; out.push({ref:"FREE",num:p.getState_PadNumber(),net:p.getState_Net(),x:p.getState_X(),y:p.getState_Y(),rot:p.getState_Rotation(),shape:p.getState_Pad(),layer:p.getState_Layer()}); }
return out;''', window_id=W, timeout=300))
tracks = check(ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l=>({net:l.net,x1:l.startX,y1:l.startY,x2:l.endX,y2:l.endY,w:l.lineWidth,layer:l.layer}));', window_id=W, timeout=120))
vias = check(ex(G + 'return (await eda.pcb_PrimitiveVia.getAll()).map(v=>({net:v.net,x:v.x,y:v.y,d:v.diameter}));', window_id=W, timeout=120))
report = {"net": net, "clearance_mm": clr, "layers": {}, "ids": []}
for L in layers:
    r = compute_plane_fill(L, net, board, pads, tracks, vias, keepouts_mm=kos, clearance_mm=clr)
    srcs = [polygon_to_easyeda_complex(p) for p in r["polygons"]]
    report["layers"][L] = {"pieces": len(srcs), "area_mm2": r["area_mm2"], "removed_islands": r["removed_islands"],
                           "vertices": sum(sum(len(x) for x in s) for s in srcs)}
    print(f"layer {L}: {len(srcs)} piece(s), {r['area_mm2']} mm2, removed islands {r['removed_islands']}")
    if dry:
        continue
    for s in srcs:
        fid = check(ex(G + 'const pg=eda.pcb_MathPolygon.createComplexPolygon(%s); const f=await eda.pcb_PrimitiveFill.create(%d, pg, %s, undefined, 0); return f?[f.getState_PrimitiveId(), f.getState_LineWidth?f.getState_LineWidth():null]:null;'
                       % (json.dumps(s), L, json.dumps(net)), window_id=W, timeout=300))
        if not fid:
            raise SystemExit(f"STOP: fill creation returned nothing on layer {L}")
        # lineWidth 0: a stroked fill outline grows the copper by half the stroke on every edge (seen as 0-5 mil DRC errors)
        report.setdefault("line_widths", []).append(fid[1])
        report["ids"].append(fid[0])
if not dry:
    check(ex(G + 'return await eda.pcb_Document.save();', window_id=W, timeout=120))
    os.makedirs(os.path.dirname(state_f), exist_ok=True)
    json.dump(report, open(state_f, "w"), indent=1)
print(json.dumps({k: v for k, v in report.items() if k != "ids"}), "fills created:", len(report["ids"]))
