"""Placement QA and Routability Acceptance Gate (run tools/pcb_dump.py first).
Usage: python tools/pcb_check.py projects/<product> [--json] [--gate] [--freeze]
Checks:
- Mechanical integrity: board containment, edge clearances, mounting holes, keepouts, height zones.
- Mechanical access: screwdriver access corridors for screw terminals and plug mating envelopes for connectors.
- Footprint integrity: immutable pad counts, numbering, and pitch.
- Electrical placement: decoupling distances to IC pins, heat/sensor isolation, RF edge placement.
- Routability feasibility: ratsnest crossings, wire length estimation, and pin escape congestion.
--gate: Enforces acceptance criteria and computes routability score (0.0 to 1.0).
--freeze: If passed, creates an immutable placement freeze snapshot in state/placement_frozen.json and records to LEDGER.jsonl.
"""
import sys, os, json
from _common import S
from desk import placement
from desk.component_intel import ComponentIntelligenceExtractor
from desk.routability import PlacementAcceptanceGate
from desk.snapshot import PCBSnapshotCache
from desk import ledger as LG

args = sys.argv[1:]
if not args or args[0].startswith("-"):
    raise SystemExit(__doc__)

proj = args[0]
with open(os.path.join(proj, "state", "pcb_dump.json"), encoding="utf-8") as f: dump = json.load(f)
with open(os.path.join(proj, "placement.json"), encoding="utf-8") as f: plan = json.load(f)
blocks = S.load_blocks(proj)

# Fast indexed PCB snapshot
snapshot = PCBSnapshotCache.get_snapshot(proj, dump)

target_path = os.path.join(proj, "state", "placement_target.json")
target = json.load(open(target_path, encoding="utf-8")) if os.path.exists(target_path) else {}

# Standard placement rule checks
E, W, M = placement.check(dump, plan, blocks)

# Plan-vs-board sync (rework item F): the gate must not pass on geometry that differs from placement.json.
if "--gate" in args:
    sync_errs, sync_m = placement.plan_board_sync(dump, plan)
    M["plan_sync"] = sync_m
    if sync_errs:
        E = list(E) + [f"plan/board out of sync: {e}" for e in sync_errs]
        print(f"PLAN/BOARD SYNC: {len(sync_errs)} difference(s); run tools/pcb_place.py or tools/pcb_dump.py before gating")

# Component Intelligence extraction
reqs = ComponentIntelligenceExtractor.extract_all(
    dump, blocks=blocks, roles=plan.get("roles", {}), heights=plan.get("heights", {})
)

# Routability & Acceptance Gate Evaluation
board_dims = tuple(plan.get("board_mm", [50.0, 50.0]))
gate_result = PlacementAcceptanceGate.evaluate(
    dump, target, reqs, board_dims, standard_errors=E, standard_warnings=W,
    precomputed_graph=snapshot.connectivity_graph
)

if "--freeze" in args and gate_result.passed:
    frozen_record = PlacementAcceptanceGate.freeze_placement(target, gate_result)
    freeze_path = os.path.join(proj, "state", "placement_frozen.json")
    with open(freeze_path, "w", encoding="utf-8") as f:
        json.dump(frozen_record, f, indent=2)
    LG.add(proj, "placement_freeze",
           f"Placement frozen with SHA-1 {frozen_record['snapshot_hash']}. "
           f"Routability score: {gate_result.routability_score:.2f}, "
           f"crossings: {gate_result.ratsnest_crossings}, "
           f"wirelength: {gate_result.estimated_total_wirelength_mm:.1f} mm.",
           source="tools/pcb_check.py --freeze")
    print(f"Placement FROZEN -> {freeze_path} (hash: {frozen_record['snapshot_hash']})")

if "--json" in args:
    out = {
        "passed": gate_result.passed,
        "errors": gate_result.errors,
        "warnings": gate_result.warnings,
        "metrics": {**M, **gate_result.metrics},
        "routability_score": gate_result.routability_score
    }
    print(json.dumps(out))
else:
    for side, m in M.items():
        if m["parts"]:
            print(f"side {side}: {m['parts']} parts, utilisation {m['utilisation']:.0%}, hotspots {m['hotspot_cells']}, "
                  f"largest free {m['largest_free_mm2']} mm2 at {m['largest_free_rect_mm']}, {m['pins_per_cm2']} pins/cm2")
    print(f"Routability Score: {gate_result.routability_score:.2f} "
          f"(Ratsnest Crossings: {gate_result.ratsnest_crossings}, "
          f"MST Length: {gate_result.estimated_total_wirelength_mm:.1f} mm, "
          f"Escape Congestion: {gate_result.escape_congestion_score:.2f})")
    for w in gate_result.warnings[:40]: print("WARN ", w)
    for e in gate_result.errors: print("ERROR", e)
    print("PLACEMENT & ROUTABILITY OK" if gate_result.passed else f"FAIL ({len(gate_result.errors)} errors, {len(gate_result.warnings)} warnings)")

sys.exit(0 if gate_result.passed else 1)
