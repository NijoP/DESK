"""Placement QA from live readback (run tools/pcb_dump.py first).
Usage: python tools/pcb_check.py projects/<product> [min_gap_mm=0.25]
Checks: pad-to-pad clearance between different parts on the same side, and decoupling distance
(every cap whose role mentions 'at pin N' must sit within 'decap_max_mm' of that pin)."""
import sys, os, json, math, re, itertools
from _common import S

MIL = 39.37007874
proj = sys.argv[1]; gap = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
D = json.load(open(os.path.join(proj, "state", "pcb_dump.json")))
plan = json.load(open(os.path.join(proj, "placement.json"))) if os.path.exists(os.path.join(proj, "placement.json")) else {}
E = []
boxes = {}
for r, c in D.items():
    b = c["bbox"]; boxes[r] = ((c["x"] + b[0]) / MIL, (c["x"] + b[1]) / MIL, (c["y"] + b[2]) / MIL, (c["y"] + b[3]) / MIL, c["layer"])
for (a, A), (b, B) in itertools.combinations(boxes.items(), 2):
    if A[4] != B[4]: continue
    dx = max(B[0] - A[1], A[0] - B[1]); dy = max(B[2] - A[3], A[2] - B[3])
    if max(dx, dy) < gap: E.append(f"{a} <-> {b}: body gap {max(dx, dy):.2f} mm < {gap}")
dmax = plan.get("decap_max_mm", 2.0)
for blk in S.load_blocks(proj):
    for p in blk["parts"]:
        m = re.search(r"(U\d+|IC\d+)\b.*?\bpin (\w+)", p.get("role", ""))
        if not m or p["ref"] not in D or m.group(1) not in D: continue
        ic = D[m.group(1)]; pad = next((q for q in ic["pads"] if q["num"] == m.group(2)), None)
        if not pad: continue
        c = D[p["ref"]]; d = math.hypot(c["x"] - (ic["x"] + pad["dx"]), c["y"] - (ic["y"] + pad["dy"])) / MIL
        if d > dmax: E.append(f"{p['ref']} is {d:.1f} mm from {m.group(1)} pin {m.group(2)} (max {dmax})")
for e in E: print("ERROR", e)
print("PLACEMENT OK" if not E else f"FAIL ({len(E)})")
sys.exit(1 if E else 0)
