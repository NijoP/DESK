"""Priority-Based Autonomous PCB Routing & Recovery Engine V2.
Usage: python tools/route.py projects/<product> [--mode BALANCED] [--passes 30] [--recovery] [--dry] [--force]

--force   Launch the engine even when the pre-flight pin-escape congestion veto (> 1.0) trips.

Supported Modes:
  FAST      - Fast execution, 12 passes, bounded optimization
  BALANCED  - Production default, 30 passes, full escape and congestion planning
  PRECISION - Demanding boards, 60 passes, extensive optimization

Order of Execution:
1. Priority Scheduling: Stages 1 (GND) through 6 (Remaining) with dynamic constrainedness
2. Recovery Rip-up: If --recovery, selectively deletes conflicting primitives from state/recovery_plan.json
3. DSN Export & Tuning: AST-based tuning of boundaries, grid resolution, and fine-pitch clearances
4. Autorouting: Supervised Freerouting execution with headless watchdog and stagnation detection
5. SES Import: Imports routed copper tracks and vias back into EasyEDA Pro
6. Post-Routing Power Widening: Clearance-safe widening of heavy copper power trunks (VBAT, VSYS)
7. Physical Connectivity Verification: Pad-to-pad physical continuity check across all populated nets
8. Routing Audit: Logs attempt metrics to state/route/routing_attempt.json and LEDGER.jsonl
"""
import sys, os, json, time, subprocess, shutil, base64
from _common import ex, guard, load_project, check, S
from desk.bridge import fetch_file
from desk import ops
from desk import ledger as LG
from desk.routability import RoutabilityEvaluator
from desk.router import RoutingPlanGenerator, DSNTuningEngine
from desk.routing import (
    RoutingEngineOrchestrator,
    RoutingModeManager,
    RoutingProfiler,
    PhysicalConnectivityVerifier,
    TraceWidthManager,
    BoardIntelligenceEngine,
)

MIL = 39.37007874
args = sys.argv[1:]
if not args or args[0].startswith("-"):
    raise SystemExit(__doc__)

proj = args[0]
adaptive = "--adaptive" in args
recovery = "--recovery" in args
dry = "--dry" in args

# Mode Selection
mode_name = "BALANCED"
if "--mode" in args:
    mode_name = args[args.index("--mode") + 1].upper()
mode_cfg = RoutingModeManager.get_mode(mode_name)

# Pass budget (explicit flag overrides mode default)
if "--passes" in args:
    passes = int(args[args.index("--passes") + 1])
elif adaptive:
    passes = 20 if recovery else 12
else:
    passes = mode_cfg.max_passes

profiler = RoutingProfiler()

# Phase 1: Board snapshot acquisition
profiler.start_phase(1, category="IO")
P = load_project(proj)
dump_path = os.path.join(proj, "state", "pcb_dump.json")
dump = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
plan_path = os.path.join(proj, "placement.json")
plan = json.load(open(plan_path, encoding="utf-8")) if os.path.exists(plan_path) else {"board_mm": [50.0, 50.0]}
profiler.end_phase()

# Phase 2: Netlist and geometry extraction
profiler.start_phase(2, category="CPU")
net_graph = RoutabilityEvaluator.build_connectivity_graph(dump)
rules_dict = dict(plan)
if plan.get("rules"): rules_dict.update(plan["rules"])
profiler.end_phase()

# Phase 4: Constraint compilation
profiler.start_phase(4, category="CPU")
profile = None
profile_path = os.path.join(proj, "design_profile.json")
if os.path.exists(profile_path):
    try:
        from desk.profile import DesignProfile
        profile = DesignProfile.load(profile_path)
    except Exception as e:
        print(f"Warning: Failed to load design profile: {e}")

routing_plan = RoutingPlanGenerator.generate_plan(
    net_graph, dump, tuple(plan.get("board_mm", [50.0, 50.0])), rules=rules_dict, profile=profile
)
profiler.end_phase()

# Fail-closed electrical pre-flight (roadmap H-01/H-02): a power rail without a declared current or a
# high-voltage net without a declared voltage must not be sized by guesswork.
blocked_nets = set()
if routing_plan.blocking_issues:
    for _m in routing_plan.blocking_issues:
        print("ELECTRICAL UNKNOWN:", _m)
    blocked_nets = {_m.split(":", 1)[0] for _m in routing_plan.blocking_issues}
    if "--allow-unknown-electrical" not in args:
        raise SystemExit(
            f"STOP: {len(routing_plan.blocking_issues)} undeclared electrical input(s) listed above. "
            "Declare them in design_profile.json (current_limits_A / voltage_rails) or rerun with "
            "--allow-unknown-electrical to size them heuristically (not for manufacturing).")
    print("WARNING: continuing with heuristic sizing for undeclared nets (--allow-unknown-electrical).")
if profile is None:
    print("NOTE: no design_profile.json; widths and clearances use built-in heuristics, not your rails.")

# Phase 7: Routing-plan generation
profiler.start_phase(7, category="CPU")
print(f"Routing Mode: {mode_cfg.mode_name} (Pass Budget: {passes}, Stackup: {routing_plan.board_stackup})")
for s_num in range(1, 7):
    s_nets = routing_plan.stage_nets.get(s_num, [])
    if s_nets:
        print(f"  Stage {s_num}: {len(s_nets)} nets ({', '.join(s_nets[:5])}{'...' if len(s_nets) > 5 else ''})")
profiler.end_phase()

G = guard(P["pcb_uuid"])
wd = os.path.join(proj, "state", "route")
os.makedirs(wd, exist_ok=True)

# Phase 2: Selective rip-up if in recovery mode
if recovery:
    rec_plan_path = os.path.join(proj, "state", "recovery_plan.json")
    if os.path.exists(rec_plan_path):
        rec_data = json.load(open(rec_plan_path, encoding="utf-8"))
        rip_ids = rec_data.get("conflicting_tracks_to_ripup", [])
        if rip_ids:
            print(f"Recovery: Selectively ripping up {len(rip_ids)} conflicting tracks...")
            check(ex(G + f'for(const id of {json.dumps(rip_ids)}){{ try{{ await eda.pcb_PrimitiveLine.modify(id, {{net:""}}); }}catch(e){{}} }} await eda.pcb_PrimitiveLine.delete({json.dumps(rip_ids)}); return true;',
                     timeout=60, window_id=P.get("window_id"), is_mutation=True))

# Phase 8: DSN export
profiler.start_phase(8, category="IPC")
dsn = os.path.join(wd, "desk_route")
if "--reuse-dsn" in args and os.path.exists(dsn):
    # Reuse the last raw DSN export (operator-approved; only valid while placement/outline are unchanged since it was written)
    print("DSN reuse: --reuse-dsn given, skipping EasyEDA export; using", dsn, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(dsn))))
else:
    dsn = fetch_file(G + 'const f=await eda.pcb_ManufactureData.getDsnFile("desk_route");', wd, window_id=P.get("window_id"))
print("DSN raw:", dsn, os.path.getsize(dsn), "B")
profiler.end_phase()

# Phase 9: DSN parsing and transformation (AST-based)
profiler.start_phase(9, category="CPU")
with open(dsn, "r", encoding="utf-8", errors="ignore") as f:
    dsn_content = f.read()

board_w_mil = plan.get("board_mm", [50.0, 50.0])[0] * MIL
board_h_mil = plan.get("board_mm", [50.0, 50.0])[1] * MIL
power_nets = set(routing_plan.stage_nets.get(1, []) + routing_plan.stage_nets.get(5, []))

# Fine-pitch escape compatible net widths (all <= 10.0 mil to clear 0.5mm QFN/ESP32 pads).
# Power trunks are widened post-import (phase 16) to the width the design profile derives from the
# declared rail current; the DSN width stays escape-compatible so the autorouter can reach fine pads.
ESCAPE_CAP_MIL = 10.0
custom_net_widths = {"3V3": 8.0, "GND": 8.0}
widen_targets = {}
if profile is not None:
    for _net in power_nets:
        if _net in blocked_nets:
            continue
        try:
            _w = profile.derive_trace_width_mil(_net)
        except ValueError:
            continue
        custom_net_widths[_net] = min(ESCAPE_CAP_MIL, _w)
        if _w > ESCAPE_CAP_MIL:
            widen_targets[_net] = min(_w, 120.0)
if not widen_targets and profile is None:
    # Legacy WATCH behaviour when no profile exists: VBAT/VSYS/VBUS trunks at 10 mil, widened later.
    custom_net_widths.update({"VBAT": 10.0, "VSYS": 10.0, "VBUS": 10.0, "VBUS_BOOST": 10.0})
    widen_targets = {"VBAT": 30.0, "VSYS": 25.0}
print("Power widening targets (mil):", {k: round(v, 1) for k, v in widen_targets.items()} or "none")

tuned_dsn = DSNTuningEngine.tune_dsn(
    dsn_content,
    (board_w_mil, board_h_mil),
    power_nets=power_nets,
    keepouts=plan.get("route_keepouts", plan.get("keepouts")),   # routing-only keepouts (placement keepouts may contain pads)
    net_widths=custom_net_widths,
    fine_pitch_width_mil=5.0,    # DRC rule set: min track 0.127 mm
    fine_pitch_clearance_mil=4.05  # DRC rule set: clearance 0.1016 mm (4.0 mil)
)

# Phase 9b: declare copper planes that exist on the real board (placement.json "planes") so the router
# connects plane nets (GND / 3V3) with plane-access vias instead of routing every pin as a trace.
for pl in plan.get("planes", []):
    pts = " ".join(f"{x * MIL:.2f} {y * MIL:.2f}" for x, y in pl["polygon_mm"])
    block = "    (plane %s (polygon %s 0 %s))" % (pl["net"], pl["layer"], pts) + chr(10)
    marker = "\n  (placement"
    i = tuned_dsn.find(marker)
    j = tuned_dsn.rfind("\n  )", 0, i)  # closing paren of (structure ...)
    if i < 0 or j < 0: raise SystemExit("STOP: cannot locate (structure) end for plane injection")
    tuned_dsn = tuned_dsn[:j + 1] + block + tuned_dsn[j + 1:]
    print("DSN plane: %s on %s (%d vertices)" % (pl["net"], pl["layer"], len(pl["polygon_mm"])))

tuned_dsn_path = os.path.join(wd, "desk_route_tuned.dsn")
with open(tuned_dsn_path, "w", encoding="utf-8") as f:
    f.write(tuned_dsn)
print("DSN tuned ->", tuned_dsn_path)
profiler.end_phase()

# Phase 9c: pre-flight congestion veto. Pin-escape congestion is the ratio of perimeter needed
# to escape every signal pad versus perimeter available; above ~1.0 the autorouter cannot
# converge and will burn the whole pass/timeout budget. Fail fast here instead of in Java.
escape_congestion = RoutabilityEvaluator.evaluate_pin_escape_congestion(dump)
CONGESTION_VETO = 1.0
print(f"Pin escape congestion: {escape_congestion:.3f} (veto above {CONGESTION_VETO:.2f})")
if mode_cfg.run_congestion_analysis and escape_congestion > CONGESTION_VETO and "--force" not in args:
    raise SystemExit(
        f"STOP: pin escape congestion {escape_congestion:.3f} exceeds {CONGESTION_VETO:.2f}; "
        "the engine will stall. Fix placement (spread high-pin-count parts) or rerun with --force.")

if dry:
    print("Dry run completed. DSN prepared."); sys.exit(0)

# Phase 10-12: External engine execution via RoutingEngineOrchestrator
profiler.start_phase(10, category="PROCESS")
ses = os.path.join(wd, "desk_route.ses")
orchestrator = RoutingEngineOrchestrator()

exec_result = orchestrator.execute_routing(
    dsn_path=tuned_dsn_path,
    ses_path=ses,
    max_passes=passes,
    timeout_sec=mode_cfg.timeout_sec,
    working_dir=wd,
    stagnation_patience=mode_cfg.stagnation_patience
)
profiler.end_phase()

print(f"Routing Engine Result: {exec_result.status} in {exec_result.duration_sec:.1f}s ({exec_result.engine_version})")
if not exec_result.success and not (exec_result.ses_generated and exec_result.ses_size_bytes > 0):
    raise SystemExit(f"STOP: Routing failed ({exec_result.status}): {exec_result.error_message}")

# Phase 15: SES import into EasyEDA Pro
profiler.start_phase(15, category="IPC")
b64 = base64.b64encode(open(ses, "rb").read()).decode()
with ops.write_op(proj, "route_import", "PCB") as rec:
    rec["dirty"] = True
    import_js = (
        'const lines = await eda.pcb_PrimitiveLine.getAll();'
        'const lineIds = lines.map(l => l.primitiveId);'
        'if (lineIds.length > 0) await eda.pcb_PrimitiveLine.delete(lineIds);'
        'const vias = await eda.pcb_PrimitiveVia.getAll();'
        'const viaIds = vias.map(v => v.primitiveId);'
        'if (viaIds.length > 0) await eda.pcb_PrimitiveVia.delete(viaIds);'
        'const b=atob("%s"); const u=new Uint8Array(b.length); for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);'
        'const ok=await eda.pcb_Document.importAutoRouteSesFile(new File([u],"desk_route.ses")); await eda.pcb_Document.save(); return ok;' % b64
    )
    r = check(ex(G + import_js, timeout=600, window_id=P.get("window_id"), is_mutation=True))

print("SES import:", r)
if r is not True: raise SystemExit("STOP: EasyEDA rejected the SES import")
time.sleep(2.5)
profiler.end_phase()

# Phase 16: Geometry-aware power integrity trace widening with pad escape preservation (IPC-2152 compliant)
profiler.start_phase(16, category="IPC")
try:
    raw_lines = ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l => ({id:l.primitiveId, net:l.net, start_x:l.startX, start_y:l.startY, end_x:l.endX, end_y:l.endY, width:l.lineWidth, layer:l.layer}));',
                   timeout=60, window_id=P.get("window_id")) or []
    raw_pads = ex(G + 'return (await eda.pcb_PrimitivePad.getAll()).map(p => ({net:p.net, x:p.x, y:p.y, size:p.width||15.0}));',
                  timeout=60, window_id=P.get("window_id")) or []

    widen_nets = set(widen_targets)
    fine_pitch_pads = [(p["x"], p["y"], (p.get("size", 15.0) / 2.0)) for p in raw_pads if p.get("net") not in widen_nets]
    obstacles = [(l["start_x"], l["start_y"], l["end_x"], l["end_y"], int(l["layer"])) for l in raw_lines if l.get("net") not in widen_nets]

    widen_plans = {}
    for _net, _target in widen_targets.items():
        widen_plans[_net] = TraceWidthManager.plan_power_widening(
            net_name=_net,
            segments=[l for l in raw_lines if l.get("net") == _net],
            target_width_mil=_target,
            escape_width_mil=ESCAPE_CAP_MIL,
            fine_pitch_pads=fine_pitch_pads,
            obstacles=obstacles,
            min_clearance_mil=5.0,
            escape_radius_mil=35.0
        )

    modifications = []
    for _plan in widen_plans.values():
        for cand in _plan.candidates:
            if cand.is_widened and cand.approved_width_mil > cand.current_width_mil:
                modifications.append({"id": cand.segment_id, "lineWidth": cand.approved_width_mil})

    if modifications:
        mod_code = f'for(const m of {json.dumps(modifications)}){{ await eda.pcb_PrimitiveLine.modify(m.id, {{lineWidth: m.lineWidth}}); }}; await eda.pcb_Document.save(); return true;'
        check(ex(G + mod_code, timeout=60, window_id=P.get("window_id"), is_mutation=True))
        time.sleep(2.0)
    print("Power trace widening: " + (", ".join(
        f"{n} {p.widened_segments}/{p.total_segments} -> {widen_targets[n]:.0f} mil" for n, p in widen_plans.items()) or "no targets"))
except Exception as e:
    print("Warning: Power trace widening deferred:", e)

# Rebuild copper pours to refresh ground planes around newly routed tracks
try:
    rebuild_js = 'const pours = await eda.pcb_PrimitivePour.getAll(); for(const p of pours){ try{ if(p.rebuildCopperRegion) await p.rebuildCopperRegion(); }catch(e){} } await eda.pcb_Document.save(); return true;'
    check(ex(G + rebuild_js, timeout=60, window_id=P.get("window_id"), is_mutation=True))
    time.sleep(2.0)
except Exception as e:
    print("Warning: Copper pour rebuild deferred:", e)
profiler.end_phase()

# Phase 17: EasyEDA readback
profiler.start_phase(17, category="IPC")
readback_tracks = ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l=>({id:l.primitiveId,net:l.net,x1:l.startX,y1:l.startY,x2:l.endX,y2:l.endY,width:l.lineWidth,layer:l.layer}));',
                     timeout=60, window_id=P.get("window_id")) or []
readback_vias = ex(G + 'return (await eda.pcb_PrimitiveVia.getAll()).map(v=>({id:v.primitiveId,net:v.net,x:v.x,y:v.y,diameter:v.diameter,start_layer:v.startLayer,end_layer:v.endLayer}));',
                   timeout=60, window_id=P.get("window_id")) or []
profiler.end_phase()

# Phase 19: Physical connectivity verification
profiler.start_phase(19, category="CPU")
conn_result = PhysicalConnectivityVerifier.verify_board(
    pcb_dump=dump,
    tracks=readback_tracks,
    vias=readback_vias
)
print("Physical Connectivity:", conn_result.summary)
profiler.end_phase()

# Phase 20: Final report generation and logging
profiler.start_phase(20, category="IO")
profile_result = profiler.finish()
print("\n" + profile_result.summary_report)
attempt_record = {
    "timestamp": time.time(),
    "mode": mode_cfg.mode_name,
    "passes": passes,
    "duration_sec": profile_result.total_wall_clock_sec,
    "populated_nets": len(net_graph.nets),
    "import_success": (r is True),
    "fully_connected_nets": conn_result.fully_connected_nets,
    "completion_pct": conn_result.overall_completion_pct,
    "engine": f"{exec_result.engine_name} {exec_result.engine_version}"
}
with open(os.path.join(wd, "routing_attempt.json"), "w", encoding="utf-8") as f:
    json.dump(attempt_record, f, indent=2)

LG.add(proj, "routing_attempt",
       f"Autonomous routing executed in {profile_result.total_wall_clock_sec:.1f}s ({mode_cfg.mode_name} mode). "
       f"Connectivity: {conn_result.fully_connected_nets}/{conn_result.total_nets} ({conn_result.overall_completion_pct}%).",
       source="tools/route.py")
profiler.end_phase()

print("NEXT: python tools/drc.py", proj, "--converge")
