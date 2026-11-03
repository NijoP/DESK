"""Apply a placement plan to the live PCB.
Usage: python tools/pcb_place.py projects/<product> [--dry]
Input: projects/<product>/placement.json  (see templates/placement.template.json)
  {"origin_mm":[x,y], "parts":[["U1", x_mm, y_mm, rot_deg, "T"|"B", "reason"], ...],
   "passives":[["C1", "U1", "5", "why"], ...]}            # passive snapped next to pin 5 of U1 (needs state/pcb_dump.json)
Every placement line carries a REASON. No reason -> not allowed (docs/04_PLACEMENT.md)."""
import sys, os, json, math
from _common import ex, guard, load_project, check

MIL = 39.37007874
proj = sys.argv[1]; dry = "--dry" in sys.argv
P = load_project(proj)
plan = json.load(open(os.path.join(proj, "placement.json")))
dump = json.load(open(os.path.join(proj, "state", "pcb_dump.json")))
ox, oy = plan.get("origin_mm", [0, 0])
grid = plan.get("grid_mm", 0.05)
snap = lambda v: round(v / grid) * grid
target = {}
for ref, x, y, rot, side, why in plan["parts"]:
    if not why: raise SystemExit(f"{ref}: placement without reason")
    target[ref] = [snap(x), snap(y), rot, side]
gap = plan.get("passive_gap_mm", 0.4)
for ref, ic, pin, why in plan.get("passives", []):
    if ic not in target: raise SystemExit(f"{ref}: anchor {ic} must be placed in 'parts' first")
    pad = next((p for p in dump[ic]["pads"] if p["num"] == pin), None)
    if pad is None: raise SystemExit(f"{ref}: {ic} has no pad {pin}")
    x, y, rot, side = target[ic]
    a = math.radians(rot); dx, dy = pad["dx"] / MIL, pad["dy"] / MIL
    px, py = x + dx * math.cos(a) - dy * math.sin(a), y + dx * math.sin(a) + dy * math.cos(a)
    bb = dump[ic]["bbox"]; half = max(abs(bb[0]), abs(bb[1]), abs(bb[2]), abs(bb[3])) / MIL
    ux, uy = px - x, py - y; n = math.hypot(ux, uy) or 1
    k = half + gap + 0.6                                    # just outside the IC body, on the escape side of the pin
    tx, ty = x + ux / n * k, y + uy / n * k
    prot = 0 if abs(ux) >= abs(uy) else 90                   # passive axis along the escape direction
    target[ref] = [snap(tx), snap(ty), prot, side]
items = []
for ref, (x, y, rot, side) in target.items():
    if ref not in dump: raise SystemExit(f"{ref} not on PCB (import changes from schematic first)")
    items.append([dump[ref]["id"], (ox + x) * MIL, (oy + y) * MIL, rot, 1 if side == "T" else 2])
json.dump(target, open(os.path.join(proj, "state", "placement_target.json"), "w"), indent=0)
if dry: print(json.dumps(target, indent=0)); sys.exit(0)
G = guard(P["pcb_uuid"]); n = 0
for i in range(0, len(items), 40):
    n += check(ex(G + 'let k=0; for(const [id,x,y,r,l] of %s){ await eda.pcb_PrimitiveComponent.modify(id,{layer:l}); '
                      'await eda.pcb_PrimitiveComponent.modify(id,{x:x,y:y,rotation:r}); k++; } return k;' % json.dumps(items[i:i + 40]), retries=2))
print("placed", n, "-> now: python tools/pcb_dump.py, then python tools/pcb_check.py")
