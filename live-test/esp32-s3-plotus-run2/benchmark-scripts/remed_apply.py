"""Post-benchmark DRC remediation: apply a JSON plan of track deletions / new tracks / new vias after an offline
clearance check against the live snapshot (other-net copper). Records created ids for rollback.
Usage: python remed_apply.py plan.json snapshot.json [--dry]"""
import sys, json, os
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.bridge import ex, guard, check
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"; G = guard("bb03148ad5ac7687")
plan = json.load(open(sys.argv[1])); s = json.load(open(sys.argv[2])); dry = "--dry" in sys.argv
CLR = plan.get("min_clearance_mm", 0.16); dele = set(plan.get("delete_tracks", []))
def other(net, layer):
    g = [pad_geometry(p) for p in s["pads"] if p["net"] != net and p["layer"] in (layer, 12)]
    g += [LineString([(t["x1"]/MIL, t["y1"]/MIL), (t["x2"]/MIL, t["y2"]/MIL)]).buffer(t["w"]/MIL/2) for t in s["tracks"] if t["net"] != net and t["layer"] == layer and t["id"] not in dele]
    g += [Point(v["x"]/MIL, v["y"]/MIL).buffer(v["d"]/MIL/2) for v in s["vias"] if v["net"] != net]
    for t in plan.get("tracks", []):          # new copper of other nets in the same plan
        if t["net"] != net and t["layer"] == layer: g.append(LineString(t["pts"]).buffer(t["w"]/2))
    for v in plan.get("vias", []):
        if v["net"] != net: g.append(Point(v["xy"]).buffer(v.get("d", 0.6)/2))
    return unary_union(g)
ok = True
for t in plan.get("tracks", []):
    d = LineString(t["pts"]).buffer(t["w"]/2).distance(other(t["net"], t["layer"]))
    print("track", t["net"], t["layer"], t["pts"], "min clearance %.3f mm" % d, "OK" if d >= CLR else "FAIL"); ok &= d >= CLR
for v in plan.get("vias", []):
    geo = Point(v["xy"]).buffer(v.get("d", 0.6)/2)
    d = min(geo.distance(other(v["net"], 1)), geo.distance(other(v["net"], 2)))
    print("via", v["net"], v["xy"], "min clearance %.3f mm" % d, "OK" if d >= CLR else "FAIL"); ok &= d >= CLR
if not ok: raise SystemExit("STOP: clearance check failed, nothing applied")
if dry: raise SystemExit("dry run OK")
rec = {"plan": plan, "deleted": [], "track_ids": [], "via_ids": []}
if dele:
    back = [t for t in s["tracks"] if t["id"] in dele]
    check(ex(G + 'await eda.pcb_PrimitiveLine.delete(%s); return true;' % json.dumps(sorted(dele)), window_id=W, timeout=120))
    rec["deleted"] = back
for v in plan.get("vias", []):
    rec["via_ids"].append(check(ex(G + 'const v=await eda.pcb_PrimitiveVia.create(%s,%f,%f,%f,%f); return v?v.getState_PrimitiveId():null;'
        % (json.dumps(v["net"]), v["xy"][0]*MIL, v["xy"][1]*MIL, v.get("h", 0.3)*MIL, v.get("d", 0.6)*MIL), window_id=W, timeout=120)))
for t in plan.get("tracks", []):
    for a, b in zip(t["pts"], t["pts"][1:]):
        rec["track_ids"].append(check(ex(G + 'const l=await eda.pcb_PrimitiveLine.create(%s,%d,%f,%f,%f,%f,%f); return l?l.getState_PrimitiveId():null;'
            % (json.dumps(t["net"]), t["layer"], a[0]*MIL, a[1]*MIL, b[0]*MIL, b[1]*MIL, t["w"]*MIL), window_id=W, timeout=120)))
check(ex(G + 'return await eda.pcb_Document.save();', window_id=W, timeout=120))
out = os.path.splitext(sys.argv[1])[0] + "_applied.json"; json.dump(rec, open(out, "w"), indent=1)
print("applied:", len(rec["deleted"]), "deleted,", sum(1 for i in rec["via_ids"] if i), "vias,", sum(1 for i in rec["track_ids"] if i), "track segments ->", out)
if None in rec["via_ids"] + rec["track_ids"]: raise SystemExit("STOP: a create returned null")
