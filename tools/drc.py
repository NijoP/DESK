"""DRC Convergence, Failure Diagnosis, and Manufacturing Readiness Gate.
Usage: python tools/drc.py projects/<product> [--json] [--converge] [--max-iter 3] [--report]

Modes:
- Single Pass (default): Runs live EasyEDA DRC, parses structured violations, and generates state/recovery_plan.json
- --converge: Runs the closed-loop convergence cycle (DRC -> Rework Plan -> Selective Route -> DRC) until 0 errors
- --report: Generates Manufacturing Readiness Report (state/readiness_report.json)
"""
import sys, os, json, subprocess, collections, time
from _common import ex, guard, load_project, check
from desk.drc_engine import (
    DRCParser,
    FailureDiagnoser,
    RecoveryPlanner,
    DRCConvergenceLoop
)
from desk import ledger as LG

args = sys.argv[1:]
if not args or args[0].startswith("-"):
    raise SystemExit(__doc__)

proj = args[0]
P = load_project(proj)
converge = "--converge" in args
report_mode = "--report" in args
json_mode = "--json" in args
max_iter = int(args[args.index("--max-iter") + 1]) if "--max-iter" in args else 3

def run_live_drc():
    js = guard(P["pcb_uuid"]) + 'const r=await eda.pcb_Drc.check(true,false,true); return Array.isArray(r)?r:{raw:r};'
    raw = check(ex(js, timeout=600, window_id=P.get("window_id")))
    return DRCParser.parse(raw)

iteration = 1
violations = run_live_drc()
cats = FailureDiagnoser.categorize_violations(violations)
failed_nets = FailureDiagnoser.identify_failed_nets(violations)

# Save recovery plan
rec_plan = RecoveryPlanner.plan_recovery(iteration, violations)
os.makedirs(os.path.join(proj, "state"), exist_ok=True)
rec_plan_path = os.path.join(proj, "state", "recovery_plan.json")
with open(rec_plan_path, "w", encoding="utf-8") as f:
    json.dump({
        "iteration": iteration,
        "failed_nets": rec_plan.failed_nets,
        "conflicting_tracks_to_ripup": rec_plan.conflicting_tracks_to_ripup,
        "suggested_layer_shifts": rec_plan.suggested_layer_shifts,
        "inserted_escape_vias": rec_plan.inserted_escape_vias,
        "rationale": rec_plan.rationale
    }, f, indent=2)

# Iteration history
history_path = os.path.join(proj, "state", "pcb_iterations.json")
history = json.load(open(history_path, encoding="utf-8")) if os.path.exists(history_path) else []

# If converge mode requested and errors exist, run convergence loop
if converge and violations:
    while iteration <= max_iter and violations:
        print(f"\n--- DRC Convergence Loop: Iteration {iteration}/{max_iter} ---")
        print(f"Current violations: {len(violations)} across {len(failed_nets)} nets")
        print(rec_plan.rationale)

        # Trigger recovery routing
        cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "route.py"), proj, "--recovery", "--passes", "15"]
        print("Executing targeted routing rework...")
        r_run = subprocess.run(cmd, capture_output=True, text=True)

        # Re-run DRC
        prev_violations = violations
        violations = run_live_drc()
        cats = FailureDiagnoser.categorize_violations(violations)
        failed_nets = FailureDiagnoser.identify_failed_nets(violations)

        iter_rec = DRCConvergenceLoop.record_iteration(
            iteration=iteration,
            placement_rev="HEAD",
            routing_plan_rev=f"REV_{iteration}",
            attempt=None,
            violations=violations
        )
        history.append({
            "iteration": iteration,
            "violations_count": len(violations),
            "failed_nets": sorted(list(failed_nets)),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        iteration += 1
        rec_plan = RecoveryPlanner.plan_recovery(iteration, violations)
        with open(rec_plan_path, "w", encoding="utf-8") as f:
            json.dump({
                "iteration": iteration,
                "failed_nets": rec_plan.failed_nets,
                "conflicting_tracks_to_ripup": rec_plan.conflicting_tracks_to_ripup,
                "rationale": rec_plan.rationale
            }, f, indent=2)

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

# Save readiness report
readiness = DRCConvergenceLoop.evaluate_readiness(proj, violations, sorted(list(failed_nets)))
readiness_path = os.path.join(proj, "state", "readiness_report.json")
with open(readiness_path, "w", encoding="utf-8") as f:
    json.dump({
        "approved": readiness.approved,
        "violations_total": len(violations),
        "unconnected_smd_pads": readiness.unconnected_smd_pads,
        "clearance_violations": readiness.clearance_violations,
        "short_circuits": readiness.short_circuits,
        "unconnected_nets": readiness.unconnected_nets,
        "summary": readiness.summary
    }, f, indent=2)

if json_mode:
    print(json.dumps({
        "violations_count": len(violations),
        "unconnected": len(cats["unconnected_pads"]),
        "clearance": len(cats["clearance"]),
        "shorts": len(cats["shorts"]),
        "failed_nets": sorted(list(failed_nets)),
        "first_violations": [{"rule": v.rule_name, "error": v.error_type, "layer": v.layer, "net": v.obj1_net} for v in violations[:15]]
    }))
else:
    rule_counts = collections.Counter(v.rule_name for v in violations)
    for rule, count in rule_counts.most_common(20):
        print(f"{count:5d}x {rule}")
    print(f"\nDRC Total: {len(violations)} violations")
    print(f"  Unconnected SMD Pads: {len(cats['unconnected_pads'])}")
    print(f"  Clearance Violations: {len(cats['clearance'])}")
    print(f"  Short Circuits:       {len(cats['shorts'])}")
    if failed_nets:
        print(f"Failed Nets ({len(failed_nets)}): {', '.join(sorted(list(failed_nets))[:10])}")
    print(f"Recovery Plan: {rec_plan_path}")
    print(f"Readiness: {'APPROVED' if readiness.approved else 'REJECTED'}")

LG.add(proj, "drc_convergence",
       f"DRC run: {len(violations)} violations. "
       f"Unconnected: {len(cats['unconnected_pads'])}, Clearance: {len(cats['clearance'])}, Shorts: {len(cats['shorts'])}. "
       f"Failed nets: {len(failed_nets)}. Status: {'APPROVED' if readiness.approved else 'REWORK_REQUIRED'}.",
       source="tools/drc.py")

sys.exit(0 if len(violations) == 0 else 1)
