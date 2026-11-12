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



def main(argv):
    """Run the DRC gate for one project; returns 0 when the board has no violations (importable for tests)."""
    from desk.errors import UsageError
    args = list(argv)
    if not args or args[0].startswith("-"):
        raise UsageError(__doc__)

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

    dump_path = os.path.join(proj, "state", "pcb_dump.json")
    dump = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
    plan_path = os.path.join(proj, "placement.json")
    plan = json.load(open(plan_path, encoding="utf-8")) if os.path.exists(plan_path) else {"board_mm": [50.0, 50.0]}
    board_bounds_mil = (plan.get("board_mm", [50.0, 50.0])[0] * 39.37, plan.get("board_mm", [50.0, 50.0])[1] * 39.37)
    obstacles = [(comp.get("x", 0.0), comp.get("y", 0.0), 30.0) for comp in dump.values()]

    iteration = 1
    violations = run_live_drc()
    cats = FailureDiagnoser.categorize_violations(violations)
    failed_nets = FailureDiagnoser.identify_failed_nets(violations)

    # Save verified recovery plan
    rec_plan = RecoveryPlanner.plan_recovery(iteration, violations, board_bounds_mil=board_bounds_mil, obstacles=obstacles)
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

    # If converge mode requested and errors exist, run progress-aware convergence loop
    if converge and violations:
        unchanged_streak = 0
        while iteration <= max_iter and violations:
            print(f"\n--- DRC Convergence Loop: Iteration {iteration}/{max_iter} ---")
            print(f"Current violations: {len(violations)} across {len(failed_nets)} nets")
            print(rec_plan.rationale)

            # Trigger recovery routing
            cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "route.py"), proj, "--recovery", "--passes", "15"]
            print("Executing targeted routing rework...")
            r_run = subprocess.run(cmd, capture_output=True, text=True)

            if r_run.returncode != 0:
                print(f"Routing subprocess error (rc {r_run.returncode}): {r_run.stderr.strip()[:200]}")
                history.append({
                    "iteration": iteration,
                    "status": "ROUTING_FAILED",
                    "error": r_run.stderr.strip()[:200],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                break

            # Re-run DRC
            prev_count = len(violations)
            violations = run_live_drc()
            cats = FailureDiagnoser.categorize_violations(violations)
            failed_nets = FailureDiagnoser.identify_failed_nets(violations)
            curr_count = len(violations)

            # Progress Classification
            if curr_count == 0:
                status = "CONVERGED"
            elif curr_count < prev_count:
                status = "IMPROVED"
                unchanged_streak = 0
            elif curr_count == prev_count:
                status = "UNCHANGED"
                unchanged_streak += 1
            else:
                status = "REGRESSED"
                unchanged_streak = 0

            print(f"Iteration {iteration} Result: {status} ({prev_count} -> {curr_count} violations)")

            history.append({
                "iteration": iteration,
                "status": status,
                "violations_count": curr_count,
                "failed_nets": sorted(list(failed_nets)),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            if status == "CONVERGED":
                break

            if unchanged_streak >= 2:
                print("Convergence halted: No progress across 2 consecutive iterations. Manual inspection required.")
                break

            iteration += 1
            rec_plan = RecoveryPlanner.plan_recovery(iteration, violations, board_bounds_mil=board_bounds_mil, obstacles=obstacles)
            with open(rec_plan_path, "w", encoding="utf-8") as f:
                json.dump({
                    "iteration": iteration,
                    "failed_nets": rec_plan.failed_nets,
                    "conflicting_tracks_to_ripup": rec_plan.conflicting_tracks_to_ripup,
                    "inserted_escape_vias": rec_plan.inserted_escape_vias,
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

    return 0 if len(violations) == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
