"""Comprehensive Benchmark Suite for DESK Performance Engineering.
Executes benchmarks across the 10 representative PCB scenarios from Part 11:
1. Small two-layer sensor PCB
2. Medium four-layer controller PCB (WATCH)
3. Fine-pitch FPC connector PCB
4. Screw-terminal power PCB
5. High-current power PCB
6. Mixed-signal board
7. Dense multi-terminal net board (100+ pins)
8. PCB with several DRC errors
9. PCB with orphan vias
10. PCB with routing congestion
"""
import sys
import os
import time
import math
import json
from typing import Dict, List, Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from desk.models import NetEndpoint, ComponentRequirement, DRCViolation
from desk.routability import _compute_fast_mst, RoutabilityEvaluator, PlacementAcceptanceGate
from desk.component_intel import ComponentIntelligenceExtractor, FootprintIntegrityEngine
from desk.router import DSNTuningEngine, RoutingPriorityScheduler
from desk.drc_engine import DRCParser, RecoveryPlanner, DRCConvergenceLoop
from desk import placement

MIL = 39.37007874

def run_benchmarks() -> Dict[str, Any]:
    results = {}

    # 1. Small two-layer sensor PCB
    dump_sensor = {
        f"C{i}": {"x": i * 100.0, "y": 50.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "3V3"}, {"num": "2", "net": "GND"}]}
        for i in range(1, 8)
    }
    dump_sensor["U1"] = {"x": 500.0, "y": 500.0, "rot": 0, "layer": 1, "pads": [{"num": str(p), "net": f"NET_{p}"} for p in range(1, 9)]}
    t0 = time.perf_counter()
    g1 = RoutabilityEvaluator.build_connectivity_graph(dump_sensor)
    results["01_small_sensor_pcb"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "nets": len(g1.nets)}

    # 2. Medium 4-layer controller PCB (WATCH)
    watch_path = os.path.join(ROOT, "projects", "WATCH", "state", "pcb_dump.json")
    if os.path.exists(watch_path):
        dump_watch = json.load(open(watch_path, encoding="utf-8"))
        t0 = time.perf_counter()
        g2 = RoutabilityEvaluator.build_connectivity_graph(dump_watch)
        results["02_medium_4layer_controller"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "nets": len(g2.nets)}

    # 3. Fine-pitch FPC connector PCB (16 pads, 0.5mm pitch)
    fpc_pads = [{"num": str(i), "dx": i * 0.5 * MIL, "dy": 0.0, "net": f"FPC_{i}", "shape": ["RECT", 10, 40]} for i in range(1, 17)]
    dump_fpc = {"J1": {"x": 500, "y": 100, "rot": 0, "layer": 1, "pads": fpc_pads}}
    t0 = time.perf_counter()
    inv = FootprintIntegrityEngine.extract_invariant("J1", dump_fpc["J1"])
    results["03_fine_pitch_fpc"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "pitch_mm": inv.pad_pitch_mm}

    # 4. Screw-terminal power PCB
    dump_tb = {
        "TB1": {"x": 500, "y": 200, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "VIN"}, {"num": "2", "net": "GND"}]}
    }
    t0 = time.perf_counter()
    reqs_tb = {"TB1": ComponentRequirement(ref="TB1", mpn="TB", width_mm=15.0, height_mm=10.0, electrical_role="screw_terminal")}
    errs_tb = RoutabilityEvaluator.verify_mechanical_access(dump_tb, {"TB1": [12.0, 5.0, 0, "T"]}, reqs_tb, (50.0, 50.0))
    results["04_screw_terminal_power"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "clear": len(errs_tb) == 0}

    # 5. High-current power PCB (tuning DSN with power rules)
    raw_dsn = "(boundary (path signal 0 0 0 0 1000 1000 1000 1000 0 0 0))\n(rule (width 10))\n(class VIN '1' (rule (width 10) (clearance 4.02)))"
    t0 = time.perf_counter()
    tuned = DSNTuningEngine.tune_dsn(raw_dsn, (2000.0, 2000.0), power_nets={"VIN"})
    results["05_high_current_power_dsn"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "tuned_len": len(tuned)}

    # 6. Mixed-signal board (scheduling stages)
    nets_mixed = {
        "USB_DP": [NetEndpoint("J1", "1", "USB_DP", 0, 0, 1), NetEndpoint("U1", "1", "USB_DP", 100, 0, 1)],
        "USB_DN": [NetEndpoint("J1", "2", "USB_DN", 0, 50, 1), NetEndpoint("U1", "2", "USB_DN", 100, 50, 1)],
        "GND": [NetEndpoint("J1", "3", "GND", 0, 100, 1), NetEndpoint("U1", "3", "GND", 100, 100, 1)],
        "ADC_IN": [NetEndpoint("S1", "1", "ADC_IN", 50, 50, 1), NetEndpoint("U1", "4", "ADC_IN", 100, 150, 1)]
    }
    t0 = time.perf_counter()
    stages = RoutingPriorityScheduler.schedule_nets(nets_mixed, diff_pairs={"USB": ("USB_DP", "USB_DN")})
    results["06_mixed_signal_scheduling"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "stage3_critical": len(stages[3])}

    # 7. Dense multi-terminal net board (120 pins)
    eps = [NetEndpoint(f"P{i}", "1", "GND_BIG", float(i % 12 * 100), float(i // 12 * 100), 1) for i in range(120)]
    t0 = time.perf_counter()
    edges, total_len = _compute_fast_mst(eps)
    results["07_dense_multi_terminal_120pins"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "edges": len(edges)}

    # 8. PCB with several DRC errors
    raw_drc = [{"ruleName": "Clearance", "errorType": "Short", "layer": "Top", "pos": [i * 10, i * 20], "obj1": {"net": f"NET_{i}"}} for i in range(25)]
    t0 = time.perf_counter()
    violations = DRCParser.parse(raw_drc)
    rec = RecoveryPlanner.plan_recovery(1, violations)
    results["08_drc_errors_recovery"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "violations": len(violations)}

    # 9. PCB with orphan vias
    v_orphan = [DRCViolation("V1", "ViaRule", "OrphanVia", "Top", obj1_type="VIA", obj1_id="V_ORPHAN")]
    t0 = time.perf_counter()
    readiness = DRCConvergenceLoop.evaluate_readiness("BENCH", v_orphan, [])
    results["09_orphan_vias_check"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "approved": readiness.approved}

    # 10. PCB with routing congestion
    qfn_pads = [{"num": str(i), "dx": (i % 8) * 20.0, "dy": (i // 8) * 20.0, "net": f"S{i}"} for i in range(64)]
    dump_qfn = {"U_QFN": {"bbox": [-100, 100, -100, 100], "pads": qfn_pads}}
    t0 = time.perf_counter()
    cg = RoutabilityEvaluator.evaluate_pin_escape_congestion(dump_qfn)
    results["10_routing_congestion_eval"] = {"time_ms": round((time.perf_counter() - t0) * 1000, 3), "congestion_score": cg}

    return results

if __name__ == "__main__":
    b_res = run_benchmarks()
    print("=" * 65)
    print("DESK PERFORMANCE BENCHMARKS (10 Representative Scenarios)")
    print("=" * 65)
    total_ms = sum(v["time_ms"] for v in b_res.values())
    for name, data in b_res.items():
        print(f"{name:<38} : {data['time_ms']:>8.3f} ms")
    print("-" * 65)
    print(f"Total Computation Time across 10 Scenarios: {total_ms:>8.3f} ms")
    print("=" * 65)
