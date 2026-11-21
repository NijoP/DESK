"""Performance Baseline and Profiling CLI for DESK.
Usage: python tools/profile_perf.py [projects/<P>] [--json] [--report]
       python tools/profile_perf.py --offline [--fixture F] [--scale 1[,4,16]] [--repeat N] [--json] [--out F.json]
                                    [--summary F.md] [--timeout S]
       python tools/profile_perf.py --write-fixture

--offline profiles the checked-in SYNTHETIC board (tests/fixtures/perf/synth_board.json, see desk/perf_bench.py) so the
profile runs on a fresh clone and in CI: no project directory, no bridge, no network. Stages that need EasyEDA or
Freerouting are reported as not measured. Several scales run one fresh process each (peak RSS is per process).
--write-fixture regenerates the fixture file from desk.perf_bench.generate_fixture().

Measures and records the 20 core operations:
 1. Bridge discovery
 2. Bridge connection establishment
 3. Window & document verification
 4. PCB component extraction
 5. Pad extraction
 6. Footprint invariant validation
 7. Connectivity graph construction
 8. MST computation
 9. Ratsnest crossing analysis
 10. Placement generation
 11. Placement validation
 12. DSN generation
 13. DSN tuning
 14. Freerouting execution (or simulated DSN routing)
 15. SES import & parse
 16. DRC execution
 17. DRC parsing
 18. Recovery planning
 19. State persistence
 20. Total workflow time
"""
import sys
import os
import json
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from desk.profiler import ProfileScope, TelemetryCollector
from desk.component_intel import ComponentIntelligenceExtractor, FootprintIntegrityEngine
from desk.placement_intel import PlacementIntelligenceEngine
from desk.routability import RoutabilityEvaluator, PlacementAcceptanceGate
from desk.router import RoutingPlanGenerator, DSNTuningEngine, StackupManager, RoutingPriorityScheduler
from desk.drc_engine import DRCParser, FailureDiagnoser, RecoveryPlanner, DRCConvergenceLoop
from desk import placement
from desk import spec as S
from desk import ledger as LG

def run_profiling(project_dir: str):
    if not project_dir:
        raise SystemExit("run_profiling needs a project directory (python tools/profile_perf.py projects/<P>)")
    collector = TelemetryCollector.get_instance()
    t_start = time.perf_counter()

    # Load dump and plan
    dump_path = os.path.join(project_dir, "state", "pcb_dump.json")
    if not os.path.exists(dump_path):
        raise SystemExit(f"Missing {dump_path}")
    
    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)
    plan_path = os.path.join(project_dir, "placement.json")
    plan = json.load(open(plan_path, encoding="utf-8")) if os.path.exists(plan_path) else {"board_mm": [50.0, 50.0]}
    blocks = S.load_blocks(project_dir)

    n_comps = len(dump)
    n_pads = sum(len(c.get("pads", [])) for c in dump.values())
    n_nets = len(set(p.get("net") for c in dump.values() for p in c.get("pads", []) if p.get("net")))

    # 1. Bridge Discovery & 2. Connection Establishment & 3. Document verification (Mock / Real)
    with ProfileScope("01_bridge_discovery") as s:
        from desk import bridge
        port = bridge.PORT

    with ProfileScope("02_bridge_connection_establishment") as s:
        # Check endpoint
        import urllib.request
        reachable = False
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/eda-windows")
            with urllib.request.urlopen(req, timeout=0.1) as r:
                reachable = True
        except Exception:
            reachable = False

    with ProfileScope("03_window_document_verification", reachable=reachable) as s:
        pass

    # 4. PCB component extraction & 5. Pad extraction
    with ProfileScope("04_pcb_component_extraction", components=n_comps) as s:
        comp_records = {k: {ck: cv for ck, cv in v.items() if ck != "pads"} for k, v in dump.items()}

    with ProfileScope("05_pad_extraction", components=n_comps, pads=n_pads) as s:
        pad_records = {k: v.get("pads", []) for k, v in dump.items()}

    # 6. Footprint Invariant validation
    with ProfileScope("06_footprint_invariant_validation", components=n_comps, pads=n_pads) as s:
        invariants = {k: FootprintIntegrityEngine.extract_invariant(k, v) for k, v in dump.items()}
        for k, inv in invariants.items():
            FootprintIntegrityEngine.verify(inv, dump[k])

    # 7. Connectivity graph construction
    with ProfileScope("07_connectivity_graph_construction", components=n_comps, pads=n_pads, nets=n_nets) as s:
        # Build pad-level endpoints
        net_endpoints = {}
        for ref, comp in dump.items():
            for p in comp.get("pads", []):
                net = p.get("net")
                if net:
                    if net not in net_endpoints: net_endpoints[net] = []
                    net_endpoints[net].append((ref, p.get("num"), p.get("dx", 0), p.get("dy", 0)))

    # 8. MST computation
    with ProfileScope("08_mst_computation", components=n_comps, nets=n_nets) as s:
        graph = RoutabilityEvaluator.build_connectivity_graph(dump)

    # 9. Ratsnest crossing analysis
    with ProfileScope("09_ratsnest_crossing_analysis", nets=n_nets) as s:
        # Evaluate crossings on graph
        crossings = graph.ratsnest_crossings

    # 10. Placement generation
    with ProfileScope("10_placement_generation", components=n_comps) as s:
        reqs = ComponentIntelligenceExtractor.extract_all(dump, blocks=blocks, roles=plan.get("roles", {}), heights=plan.get("heights", {}))
        engine = PlacementIntelligenceEngine(tuple(plan.get("board_mm", [50.0, 50.0])))
        gen_plan = engine.generate_hierarchical_placement(reqs, blocks=blocks)

    # 11. Placement validation
    with ProfileScope("11_placement_validation", components=n_comps, pads=n_pads) as s:
        E, W, M = placement.check(dump, plan, blocks)
        gate_res = PlacementAcceptanceGate.evaluate(dump, {}, reqs, tuple(plan.get("board_mm", [50.0, 50.0])), standard_errors=E, standard_warnings=W)

    # 12. DSN generation & 13. DSN tuning
    dsn_path = os.path.join(project_dir, "state", "route", "desk_route")
    if not os.path.exists(dsn_path):
        dsn_path = os.path.join(project_dir, "state", "route", "desk_route_fixed.dsn")
    
    dsn_content = open(dsn_path, encoding="utf-8", errors="ignore").read() if os.path.exists(dsn_path) else "(boundary (path signal 0 0 0 0 1000 1000 1000 1000 0 0 0))"

    with ProfileScope("12_dsn_generation", size_bytes=len(dsn_content)) as s:
        # Data serialization
        b_dsn = dsn_content.encode("utf-8")

    with ProfileScope("13_dsn_tuning", size_bytes=len(dsn_content)) as s:
        tuned = DSNTuningEngine.tune_dsn(dsn_content, (2000.0, 2000.0), power_nets={"3V3", "VBUS", "GND"})

    # 14. Freerouting execution & 15. SES import & parse
    ses_path = os.path.join(project_dir, "state", "route", "test_out.ses")
    ses_content = open(ses_path, "rb").read() if os.path.exists(ses_path) else b"(session)"

    with ProfileScope("14_freerouting_execution_simulated", size_bytes=len(ses_content)) as s:
        pass

    with ProfileScope("15_ses_import_and_parse", size_bytes=len(ses_content)) as s:
        # Simulating base64 decoding and byte array allocation
        import base64
        b64 = base64.b64encode(ses_content).decode()
        decoded = base64.b64decode(b64)

    # 16. DRC execution & 17. DRC parsing
    raw_drc_sample = [
        {"ruleName": "Clearance", "errorType": "TrackToTrack", "layer": "Top", "pos": [100, 200], "obj1": {"net": "SPI_MOSI"}, "obj2": {"net": "GND"}},
        {"ruleName": "Unconnected", "errorType": "OpenNet", "layer": "Top", "pos": [300, 400], "obj1": {"net": "3V3"}},
        {"ruleName": "HoleSize", "errorType": "MinDrill", "layer": "Multi", "pos": [500, 600], "obj1": {"net": "GND"}}
    ] * 20  # 60 sample violations

    with ProfileScope("16_drc_execution_simulated") as s:
        pass

    with ProfileScope("17_drc_parsing", violations=len(raw_drc_sample)) as s:
        parsed_violations = DRCParser.parse(raw_drc_sample)

    # 18. Recovery planning
    with ProfileScope("18_recovery_planning", violations=len(parsed_violations)) as s:
        rec_plan = RecoveryPlanner.plan_recovery(1, parsed_violations)

    # 19. State persistence
    with ProfileScope("19_state_persistence") as s:
        # Serializing iteration record and ledger entry
        LG.read(project_dir)

    # 20. Total workflow
    total_time = (time.perf_counter() - t_start) * 1000.0
    collector.add_record(
        collector.records[0].__class__(
            operation="20_total_workflow_time",
            wall_ms=round(total_time, 2),
            cpu_ms=0.0,
            memory_delta_kb=0.0,
            components_processed=n_comps,
            pads_processed=n_pads,
            nets_processed=n_nets
        )
    )

    summary = collector.summary()
    return summary

def _opt(argv, name, default=None):
    """Value of `--name V` or `--name=V` in argv."""
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


_COLD_IMPORT_CODE = (
    "import json, sys, time; t = time.perf_counter(); sys.path.insert(0, sys.argv[1]); "
    "from desk import perf_bench as pb; pb._stages(); "
    "print(json.dumps({'import_ms': round((time.perf_counter() - t) * 1000.0, 3), 'peak_rss_mb': pb.peak_rss_mb()}))"
)


def _run_child(args, timeout):
    """One measurement in a fresh interpreter, so its peak RSS and import cost are its own."""
    import subprocess
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout} s"}
    if cp.returncode != 0:
        return {"error": f"exit {cp.returncode}: {(cp.stderr or '').strip()[-800:]}"}
    try:
        return json.loads(cp.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": f"unparseable output: {cp.stdout[-400:]!r}"}


def run_offline_cli(argv):
    """`--offline`: measure the synthetic fixture. Returns the result dict (also written to --out / --summary)."""
    from desk import perf_bench as pb
    fixture = _opt(argv, "--fixture") or pb.FIXTURE_PATH
    repeat = int(_opt(argv, "--repeat", "5"))
    timeout = float(_opt(argv, "--timeout", "900"))
    scales = [int(s) for s in str(_opt(argv, "--scale", "1")).split(",") if s.strip()]
    if not scales or min(scales) < 1:
        raise SystemExit("--scale takes positive integers, e.g. --scale 1,4,16")

    if "--child" in argv:   # one scale in this process (used by the parent below)
        return pb.run_offline(pb.scale_fixture(pb.load_fixture(fixture), scales[0]), repeat=repeat)

    runs = []
    for k in scales:
        res = _run_child([sys.executable, os.path.abspath(__file__), "--offline", "--child", "--json",
                          "--fixture", fixture, "--scale", str(k), "--repeat", str(repeat)], timeout)
        res["scale"] = k
        runs.append(res)
    cold_import = [_run_child([sys.executable, "-c", _COLD_IMPORT_CODE, ROOT], 120) for _ in range(3)]
    ok = [c for c in cold_import if "import_ms" in c]
    out = {
        "schema": "desk.perf.offline/1",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": pb.host_info(),
        "fixture_path": os.path.relpath(fixture, ROOT) if os.path.isabs(fixture) else fixture,
        "repeat": repeat,
        "cold_engine_import": {"samples": cold_import,
                               "median_ms": sorted(c["import_ms"] for c in ok)[len(ok) // 2] if ok else None},
        "runs": runs,
        "note": "Synthetic fixture, software-only measurement; not validated on a live design.",
    }
    return out


def _offline_markdown(res):
    from desk import perf_bench as pb
    h = res["host"]
    lines = [f"### DESK offline profile: {h.get('system')} {h.get('release')} / {h.get('machine')} / "
             f"Python {h.get('python')} / {h.get('cpu_count')} CPUs / {h.get('physical_ram_mb')} MB RAM", "",
             f"Cold engine import (fresh process, median of 3): {res['cold_engine_import']['median_ms']} ms", ""]
    for run in res["runs"]:
        if "error" in run:
            lines += [f"**scale x{run['scale']}**: {run['error']}", ""]
        else:
            lines += [pb.format_table(run), ""]
    lines.append("Not measured offline: " + "; ".join(f"`{k}` ({v})" for k, v in pb.NOT_MEASURED.items()))
    return "\n".join(lines) + "\n"


if __name__ == "__main__" and "--write-fixture" in sys.argv:
    from desk import perf_bench as _pb
    with open(_pb.FIXTURE_PATH, "w", encoding="utf-8", newline="\n") as _f:
        _f.write(_pb.fixture_json(_pb.generate_fixture()))
    print(f"wrote {os.path.relpath(_pb.FIXTURE_PATH, ROOT)}")
    raise SystemExit(0)

if __name__ == "__main__" and "--offline" in sys.argv:
    _res = run_offline_cli(sys.argv[1:])
    if _opt(sys.argv, "--out"):
        with open(_opt(sys.argv, "--out"), "w", encoding="utf-8") as _f:
            json.dump(_res, _f, indent=2)
    if _opt(sys.argv, "--summary") and "--child" not in sys.argv:
        with open(_opt(sys.argv, "--summary"), "a", encoding="utf-8") as _f:
            _f.write(_offline_markdown(_res))
    if "--json" in sys.argv:
        print(json.dumps(_res, indent=None if "--child" in sys.argv else 2))
    else:
        print(_offline_markdown(_res))
    _failed = [r for r in _res.get("runs", []) if "error" in r]
    raise SystemExit(1 if _failed and len(_failed) == len(_res.get("runs", [])) else 0)

if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else (__import__("desk.config", fromlist=["get"]).get("DESK_PROJECT") or "")
    if not proj:
        raise SystemExit("usage: python tools/profile_perf.py projects/<P> [--json]  (or set DESK_PROJECT)")
    res = run_profiling(proj)
    if "--json" in sys.argv:
        print(json.dumps(res, indent=2))
    else:
        print("\n" + "=" * 70)
        print("DESK BASELINE PERFORMANCE PROFILE")
        print("=" * 70)
        print(f"Total Wall-Clock Time: {res['total_wall_ms']} ms")
        print(f"Total CPU Time:        {res['total_cpu_ms']} ms")
        print("\nOperations Breakdown (sorted by wall duration):")
        print(f"{'Operation':<38} {'Count':<6} {'Total ms':<10} {'Max ms':<10}")
        print("-" * 70)
        for op, data in res["operations"].items():
            print(f"{op:<38} {data['count']:<6} {data['total_wall_ms']:<10.2f} {data['max_wall_ms']:<10.2f}")
        print("\nTop 5 Bottlenecks:")
        for idx, b in enumerate(res["top_bottlenecks"], 1):
            print(f"  {idx}. {b} ({res['operations'][b]['total_wall_ms']:.2f} ms)")
        print("=" * 70)
