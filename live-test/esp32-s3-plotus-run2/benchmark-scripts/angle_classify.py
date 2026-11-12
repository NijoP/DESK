"""Classify the acute (< 90 deg) track corners from pcb/routing/angle_check.json: covered by a pad / via of the same net
(no exposed acute copper notch) or open. Usage: python angle_classify.py snapshot.json"""
import json, sys
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.copper_fill import pad_geometry, MIL
from shapely.geometry import Point
s = json.load(open(sys.argv[1])); f = r"..\pcb\routing\angle_check.json"; r = json.load(open(f))
out = []
for n, L, p, a in r["acute_lt_90"]:
    P = Point(p)
    on = ["%s.%s" % (q["ref"], q["num"]) for q in s["pads"] if q["net"] == n and pad_geometry(q).buffer(0.02).contains(P)]
    on += ["via" for v in s["vias"] if v["net"] == n and Point(v["x"] / MIL, v["y"] / MIL).distance(P) < v["d"] / MIL / 2]
    out.append({"net": n, "layer": L, "at_mm": p, "angle_deg": a, "covered_by": on})
    print(n, L, p, a, "covered by", on or "NONE")
r["classified"] = out; json.dump(r, open(f, "w"), indent=1)
