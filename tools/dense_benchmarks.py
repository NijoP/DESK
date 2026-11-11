"""Dense PCB benchmark suite: density analysis, escape, priority, placement refinement and power
distribution on ten synthetic fixtures plus the real WATCH dump when present.
Usage: python tools/dense_benchmarks.py [--json out.json] [--runs 3]
All results are offline (no Java, no EasyEDA). Synthetic rows are labelled SYNTHETIC; the WATCH row is
REAL-BOARD (geometry only; its routing outcome is not measured here).
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk.routing.density import DensePCBIntelligence
from desk.routing.fixtures import make_board, SCENARIOS, plane_layers_from_planes
from desk.placement_refine import PlacementRefiner
from desk.power_distribution import PowerDistributionPlanner
from desk.profile import DesignProfile

MIL = 39.37007874
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bench(name, dump, board_mm, origin_mm, stackup, planes, keepouts, runs=3, refine=True):
    times = []
    rep = None
    for _ in range(runs):
        t0 = time.perf_counter()
        eng = DensePCBIntelligence(dump, board_mm, origin_mm, stackup=stackup,
                                   plane_layers=plane_layers_from_planes(planes, stackup), keepouts_mm=keepouts)
        rep = eng.analyze()
        times.append((time.perf_counter() - t0) * 1000.0)
    row = {
        "board": name, "components": rep.total_components, "pads": rep.total_pads, "nets": rep.total_nets,
        "board_mm": board_mm, "routable_layers": len(rep.routable_layers), "crossings": rep.ratsnest_crossings,
        "mst_mm": rep.mst_wirelength_mm, "overall_congestion": rep.overall_congestion, "overloaded_cells": rep.overloaded_cells,
        "hotspot_regions": len(rep.hotspots), "escape": rep.escape_summary,
        "top_cause": rep.hotspots[0].causes[0] if rep.hotspots else "-",
        "analysis_ms_p50": round(statistics.median(times), 1), "analysis_ms_max": round(max(times), 1),
    }
    if refine:
        plan = {"board_mm": list(board_mm), "origin_mm": list(origin_mm), "layers": len(stackup), "keepouts": keepouts, "planes": planes, "parts": []}
        t0 = time.perf_counter()
        res = PlacementRefiner(dump, plan, stackup=stackup, plane_layers=plane_layers_from_planes(planes, stackup)).refine(max_moves=3)
        row.update({"refine_ms": round((time.perf_counter() - t0) * 1000.0, 1), "refine_moves": len(res.proposals),
                    "refine_objective": (res.objective_start, res.objective_end),
                    "refine_hotspot_cells": (res.proposals[0].hotspot_cells_before if res.proposals else rep.hotspot_cells,
                                             res.proposals[-1].hotspot_cells_after if res.proposals else rep.hotspot_cells)})
    return row


def main(argv):
    runs = int(argv[argv.index("--runs") + 1]) if "--runs" in argv else 3
    rows = []
    for sc in SCENARIOS:
        fx = make_board(sc)
        rows.append({"kind": "SYNTHETIC", **bench(sc, fx["dump"], fx["board_mm"], fx["origin_mm"], fx["stackup"], fx["planes"], fx["keepouts"], runs)})
    wpath = os.path.join(ROOT, "projects", "WATCH", "state", "pcb_dump.json")
    ppath = os.path.join(ROOT, "projects", "WATCH", "placement.json")
    if os.path.exists(wpath) and os.path.exists(ppath):
        dump = json.load(open(wpath, encoding="utf-8"))
        plan = json.load(open(ppath, encoding="utf-8"))
        stack = ["Top", "Inner1", "Inner2", "Bottom"] if plan.get("layers") == 4 else ["Top", "Bottom"]
        rows.append({"kind": "REAL-BOARD", **bench("WATCH (repo dump)", dump, tuple(plan["board_mm"]), tuple(plan.get("origin_mm", [0, 0])),
                                                   stack, plan.get("planes", []), plan.get("route_keepouts") or plan.get("keepouts", []), runs)})
    # power distribution on a fixture with declared currents
    fx = make_board("multi_rail_limited_layers")
    prof = DesignProfile(project_id="BENCH", layer_count=4)
    prof.current_limits_A.update({"VIN_12V": 1.0, "5V": 1.5, "3V3": 1.5, "1V8": 0.4, "1V2": 0.4})
    prof.voltage_rails.update({"VIN_12V": 12.0, "5V": 5.0, "3V3": 3.3, "1V8": 1.8, "1V2": 1.2})
    t0 = time.perf_counter()
    pdn = PowerDistributionPlanner(fx["dump"], prof, {"board_mm": list(fx["board_mm"]), "origin_mm": [0, 0], "planes": fx["planes"], "keepouts": fx["keepouts"]}).analyze()
    pdn_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    print(f"{'board':30s} {'kind':10s} {'parts':>5s} {'pads':>5s} {'nets':>4s} {'xing':>5s} {'cong':>6s} {'over':>4s} {'hot':>4s} {'ms':>6s} {'refine':>8s}  top cause")
    for r in rows:
        ref = f"{r.get('refine_moves', 0)}mv/{r.get('refine_ms', 0):.0f}ms"
        print(f"{r['board']:30s} {r['kind']:10s} {r['components']:5d} {r['pads']:5d} {r['nets']:4d} {r['crossings']:5d} {r['overall_congestion']:6.2f} "
              f"{r['overloaded_cells']:4d} {r['hotspot_regions']:4d} {r['analysis_ms_p50']:6.1f} {ref:>8s}  {r['top_cause']}")
    print(f"\npower distribution (multi_rail_limited_layers, declared currents): {pdn_ms} ms; "
          + "; ".join(f"{x.net}={x.strategy}" for x in pdn.rails))
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": runs, "rows": rows,
           "power_distribution": {"ms": pdn_ms, "rails": [{"net": x.net, "strategy": x.strategy, "width_mil": x.trace_width_mil,
                                                           "drop_mv": x.voltage_drop_mv_worst_path, "vias": x.vias_per_transition} for x in pdn.rails]}}
    if "--json" in argv:
        path = argv[argv.index("--json") + 1]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print("saved", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
