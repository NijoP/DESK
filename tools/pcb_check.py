"""Placement QA from live readback against docs/04_PLACEMENT.md rules (run tools/pcb_dump.py first).
Usage: python tools/pcb_check.py projects/<product> [--json]
Checks: board containment + edge clearance, pad-to-pad + body-to-body by package class, connectors at edge with free
mating side + ESD close behind, sensors vs heat sources, heat spreading, RF at edge, keep-outs, height zones,
decoupling distance/side, orthogonal rotation, utilisation / hotspots / largest free region per side.
Rules and roles come from projects/<P>/placement.json (templates/placement.template.json). Exit 0 only without errors."""
import sys, os, json
from _common import S
from desk import placement

proj = sys.argv[1]
with open(os.path.join(proj, "state", "pcb_dump.json")) as f: dump = json.load(f)
with open(os.path.join(proj, "placement.json")) as f: plan = json.load(f)
E, W, M = placement.check(dump, plan, S.load_blocks(proj))
if "--json" in sys.argv:
    print(json.dumps({"errors": E, "warnings": W, "metrics": M}))
else:
    for side, m in M.items():
        if m["parts"]: print(f"side {side}: {m['parts']} parts, utilisation {m['utilisation']:.0%}, hotspots {m['hotspot_cells']}, "
                             f"largest free {m['largest_free_mm2']} mm2 at {m['largest_free_rect_mm']}, {m['pins_per_cm2']} pins/cm2")
    for w in W[:40]: print("WARN ", w)
    for e in E: print("ERROR", e)
    print("PLACEMENT OK" if not E else f"FAIL ({len(E)} errors, {len(W)} warnings)")
sys.exit(1 if E else 0)
