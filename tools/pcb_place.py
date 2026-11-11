"""Apply an intelligent placement plan to the live PCB or auto-generate one.
Usage: python tools/pcb_place.py projects/<product> [--auto] [--dry]
Input: projects/<product>/placement.json
  {"origin_mm":[x,y], "parts":[["U1", x_mm, y_mm, rot_deg, "T"|"B", "reason"], ...],
   "passives":[["C1", "U1", "5", "why"], ...]}
--auto: Runs the Placement Intelligence Engine to generate a complete mechanical-first placement plan.
--dry: Validates and writes target coordinates without modifying EasyEDA.
"""
import sys, os, json, math
from _common import ex, guard, load_project, check, S
from desk.component_intel import ComponentIntelligenceExtractor, FootprintIntegrityEngine
from desk.placement_intel import PlacementIntelligenceEngine

MIL = 39.37007874
args = sys.argv[1:]
if not args or args[0].startswith("-"):
    raise SystemExit(__doc__)

proj = args[0]
dry = "--dry" in args
auto = "--auto" in args
P = load_project(proj)
dump_path = os.path.join(proj, "state", "pcb_dump.json")
if not os.path.exists(dump_path):
    raise SystemExit(f"STOP: {dump_path} missing. Run python tools/pcb_dump.py {proj} first.")

dump = json.load(open(dump_path, encoding="utf-8"))
blocks = S.load_blocks(proj)
plan_path = os.path.join(proj, "placement.json")
plan = json.load(open(plan_path, encoding="utf-8")) if os.path.exists(plan_path) else {"board_mm": [50.0, 50.0], "parts": [], "passives": []}

reqs = ComponentIntelligenceExtractor.extract_all(dump, blocks=blocks, roles=plan.get("roles", {}), heights=plan.get("heights", {}))

# If --auto is requested, run autonomous placement generator
if auto:
    engine = PlacementIntelligenceEngine(
        board_dims_mm=tuple(plan.get("board_mm", [50.0, 50.0])),
        origin_mm=tuple(plan.get("origin_mm", [0.0, 0.0]))
    )
    generated_plan = engine.generate_hierarchical_placement(reqs, blocks=blocks, keepouts=plan.get("keepouts"))
    plan["parts"] = [
        [intent.ref, intent.target_x_mm, intent.target_y_mm, intent.rotation, intent.side, intent.reason]
        for intent in generated_plan.intents.values()
    ]
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    print(f"Auto-generated placement for {len(plan['parts'])} components -> {plan_path}")

ox, oy = plan.get("origin_mm", [0, 0])
grid = plan.get("grid_mm", 0.05)
snap = lambda v: round(v / grid) * grid
target = {}

for ref, x, y, rot, side, why in plan.get("parts", []):
    if not why: raise SystemExit(f"{ref}: placement without reason")
    target[ref] = [snap(x), snap(y), rot, side]

gap = plan.get("passive_gap_mm", 0.4)
for ref, ic, pin, why in plan.get("passives", []):
    if ic not in target: raise SystemExit(f"{ref}: anchor {ic} must be placed in 'parts' first")
    pad = next((p for p in dump[ic]["pads"] if str(p["num"]) == str(pin)), None)
    if pad is None: raise SystemExit(f"{ref}: {ic} has no pad {pin}")
    x, y, rot, side = target[ic]
    # pad dx/dy are board-frame at the dump's current rotation: rotate by (planned - current) only (QA-03)
    a = math.radians(rot - (dump[ic].get("rot") or 0)); dx, dy = pad["dx"] / MIL, pad["dy"] / MIL
    px, py = x + dx * math.cos(a) - dy * math.sin(a), y + dx * math.sin(a) + dy * math.cos(a)
    bb = dump[ic]["bbox"]; half = max(abs(bb[0]), abs(bb[1]), abs(bb[2]), abs(bb[3])) / MIL
    ux, uy = px - x, py - y; n = math.hypot(ux, uy) or 1
    k = half + gap + 0.6
    tx, ty = x + ux / n * k, y + uy / n * k
    prot = 0 if abs(ux) >= abs(uy) else 90
    target[ref] = [snap(tx), snap(ty), prot, side]

# Validate footprint invariants before modifying PCB
for ref in target:
    if ref in reqs and reqs[ref].invariants:
        inv_errs = FootprintIntegrityEngine.verify(reqs[ref].invariants, dump[ref])
        if inv_errs:
            raise SystemExit(f"FOOTPRINT INVARIANT VIOLATION: {inv_errs}")

items = []
for ref, (x, y, rot, side) in target.items():
    if ref not in dump: raise SystemExit(f"{ref} not on PCB (import changes from schematic first)")
    items.append([dump[ref]["id"], (ox + x) * MIL, (oy + y) * MIL, rot, 1 if side == "T" else 2])

target_out_path = os.path.join(proj, "state", "placement_target.json")
json.dump(target, open(target_out_path, "w", encoding="utf-8"), indent=2)

if dry:
    print(f"Validated {len(target)} placements. Wrote {target_out_path}")
    sys.exit(0)

G = guard(P["pcb_uuid"]); n = 0
for i in range(0, len(items), 40):
    n += check(ex(G + 'let k=0; for(const [id,x,y,r,l] of %s){ await eda.pcb_PrimitiveComponent.modify(id,{layer:l}); '
                      'await eda.pcb_PrimitiveComponent.modify(id,{x:x,y:y,rotation:r}); k++; } return k;' % json.dumps(items[i:i + 40]),
                  retries=2, window_id=P.get("window_id")))
print("placed", n, "-> now: python tools/pcb_dump.py, then python tools/pcb_check.py --gate")
