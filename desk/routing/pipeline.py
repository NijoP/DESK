"""Routing pipeline (the body of tools/route.py as an importable function).

`run(argv)` performs the 20-phase routing flow: snapshot, constraint compilation, dense-board analysis,
DSN export and tuning, pre-flight, supervised Freerouting (chunked), SES import, power widening,
read-back, physical connectivity verification and the audit record. `tools/route.py` is a thin
wrapper. Nothing runs at import time, so the module can be imported by tests and by the agent loop.

Live EasyEDA mutations inside this flow (recovery rip-up, SES import, power widening, pour rebuild)
all go through `ops.write_op`, so every one is journalled with its approval record.
"""
import sys, os, json, time, subprocess, shutil, base64
from desk.bridge import ex, guard, load_project, check
from desk import spec as S
from desk.bridge import fetch_file
from desk import ops
from desk import ledger as LG
from desk.routability import RoutabilityEvaluator
from desk.router import RoutingPlanGenerator, DSNTuningEngine
from desk.routing.orchestrator import RoutingEngineOrchestrator
from desk.routing.modes import RoutingModeManager
from desk.routing.profiling import RoutingProfiler
from desk.routing.connectivity import PhysicalConnectivityVerifier
from desk.routing.width import TraceWidthManager
from desk.errors import UsageError
MIL = 39.37007874

USAGE = """Priority-Based Autonomous PCB Routing & Recovery Engine V2.
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
8. Routing Audit: Logs attempt metrics to state/route/routing_attempt.json and LEDGER.jsonl"""


def run(argv) -> int:
    """Route one project. Returns the process exit code; raises DeskError subclasses on refusal."""
    args = list(argv)
    if not args or args[0].startswith("-"):
        raise UsageError(USAGE)

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
    approval_id = ops.cli_approval(proj, "route", "PCB", argv=["tools/route.py"] + args)   # one approval for the whole run
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
        # A profile that cannot be loaded is DESIGN_PROFILE_INVALID and stops the run here with the offending key
        # (UPS_1000 F-011); it is never downgraded to a warning followed by heuristic sizing.
        from desk.profile import DesignProfile
        profile = DesignProfile.load(profile_path)

    routing_plan = RoutingPlanGenerator.generate_plan(
        net_graph, dump, tuple(plan.get("board_mm", [50.0, 50.0])), rules=rules_dict, profile=profile
    )
    profiler.end_phase()

    # Fail-closed electrical pre-flight (roadmap H-01/H-02): a power rail without a declared current or a
    # high-voltage net without a declared voltage must not be sized by guesswork.
    blocked_nets = set()
    for _m in getattr(routing_plan, "assumptions", []):
        print("ASSUMED:", _m)
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

    # Dense-board intelligence (deterministic, ~50 ms): hotspot regions with causes, reserved corridors and a
    # net priority order that is handed to the engine as priority_net_classes (DSN classes are named per net).
    from desk.routing.density import DensePCBIntelligence
    from desk.routing.fixtures import plane_layers_from_planes
    _stack_names = list(routing_plan.board_stackup)
    dense = DensePCBIntelligence(dump, tuple(plan.get("board_mm", [50.0, 50.0])), tuple(plan.get("origin_mm", [0.0, 0.0])),
                                 stackup=_stack_names, plane_layers=plane_layers_from_planes(plan.get("planes", []), _stack_names),
                                 keepouts_mm=plan.get("route_keepouts") or plan.get("keepouts"), profile=profile)
    dense_report = dense.analyze()
    print(f"Dense-board analysis ({dense_report.analysis_ms:.0f} ms): congestion {dense_report.overall_congestion}, "
          f"{dense_report.overloaded_cells} overloaded cells, {len(dense_report.hotspots)} hotspot regions, "
          f"{dense_report.ratsnest_crossings} crossings, escape {dense_report.escape_summary}")
    for _h in dense_report.hotspots[:5]:
        print(f"  {_h.region_id} {_h.bbox_mm} mm score {_h.max_score}: {', '.join(_h.causes)} -> {_h.recommended_strategy}")
    priority_classes = dense_report.priority_net_order[:max(8, len(dense_report.priority_net_order) // 3)]
    plane_nets = dense_report.plane_nets
    try:
        from desk.fsutil import atomic_write_json
        atomic_write_json(os.path.join(proj, "state", "route", "dense_analysis.json"), dense_report.to_dict(include_cells=True), indent=1)
    except Exception as _e:
        print("Warning: could not save dense_analysis.json:", _e)

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
                with ops.write_op(proj, "route_ripup", "PCB", approval=approval_id) as rec:
                    rec["dirty"] = True
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
        # Per-net clearances from the routing plan (profile voltages / RF / fine pitch); previously discarded.
        net_clearances={n: c.clearance_mil for n, c in routing_plan.net_constraints.items() if c.clearance_mil > 4.05},
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
        print("Dry run completed. DSN prepared."); return 0

    # Phase 9d: fail-closed structural pre-flight (LSN-20261111-004): planes present in the DSN, exactly one closed
    # outline on the board, no pad inside a routing keep-out. Refuses to start the engine otherwise.
    from desk.routing.preflight import run_preflight
    from desk.fsutil import atomic_write_json
    try:
        outline_prims = ex(G + 'const pl=(await eda.pcb_PrimitivePolyline.getAll()||[]).filter(p=>p.layer==11).map(p=>({id:p.primitiveId,layer:p.layer,closed:true}));'
                               'const ln=(await eda.pcb_PrimitiveLine.getAll()||[]).filter(l=>l.layer==11).map(l=>({id:l.primitiveId,layer:l.layer,closed:false}));'
                               'return pl.concat(ln);', timeout=30, window_id=P.get("window_id")) or []
    except BaseException as _e:
        print("Warning: could not read outline primitives:", _e)
        outline_prims = None
    preflight = run_preflight(tuned_dsn, plan, dump, outline_prims)
    try:
        atomic_write_json(os.path.join(wd, "preflight.json"), preflight.to_dict(), indent=1)
    except Exception:
        pass
    for _w in preflight.warnings:
        print("PRE-FLIGHT WARNING:", _w)
    if not preflight.passed:
        for _e in preflight.errors:
            print("PRE-FLIGHT FAIL:", _e)
        raise SystemExit("STOP: routing pre-flight refused the board (see state/route/preflight.json). "
                         "Fix placement.json planes/route_keepouts or the outline; do not tune timeouts.")
    print(f"Pre-flight OK: planes {preflight.planes_in_dsn}/{preflight.planes_declared}, outline primitives {preflight.outline_primitives}, "
          f"pads in router keep-outs {len(preflight.pads_in_router_keepouts)}")

    # Phase 9e: routing feasibility (desk/routing/feasibility.py). Every pad is checked against the clearance rule of
    # ITS net (not the fabricator minimum). A rule that exceeds the pin-field gap of its own pads can never be met and
    # is an engineering decision for the Captain, not a reason to lower the rule or to launch a long engine run
    # (UPS_1000: 6 attempts against a board whose 1.25-1.30 mm rules sat on 1.27 mm-pitch pins).
    from desk.routing import feasibility as FZ
    _fab_min = float(getattr(getattr(profile, "manufacturing", None), "min_clearance_mil", 4.02) if profile else 4.02)
    feas = FZ.evaluate(dump, {n: c.clearance_mil for n, c in routing_plan.net_constraints.items()}, _fab_min,
                       stackup=_stack_names, plane_layers=plane_layers_from_planes(plan.get("planes", []), _stack_names),
                       route_keepouts=plan.get("route_keepouts") or [], origin_mm=tuple(plan.get("origin_mm", [0.0, 0.0])),
                       power_nets=power_nets)
    try:
        atomic_write_json(os.path.join(wd, "feasibility.json"), feas.to_dict(), indent=1)
    except Exception:
        pass
    print(f"Feasibility ({feas.analysis_ms:.0f} ms): {feas.summary}")
    for _w in feas.warnings:
        print("FEASIBILITY WARNING:", _w)
    for _b in feas.blocked[:10]:
        print(f"  {_b.classification}: {_b.pad_id} [{_b.net}] {_b.detail}")
    if feas.decisions:
        try:
            atomic_write_json(os.path.join(wd, "engineering_decisions.json"), [d.to_dict() for d in feas.decisions], indent=1)
        except Exception:
            pass
        for _d in feas.decisions:
            print(f"ENGINEERING DECISION {_d.decision_id} ({_d.status}): net {_d.net} rule {_d.rule_mm:.3f} mm > pin-field gap "
                  f"{_d.pin_field_mm:.3f} mm at {len(_d.pads)} pad(s); options:")
            for _o in _d.options:
                print("    -", _o)
    if not feas.feasible:
        if "--acknowledge-blocked" in args:
            ops.record_approval(proj, "route_blocked_feasibility", "PCB", granted_by="operator",
                                how="cli tools/route.py --acknowledge-blocked",
                                reason="; ".join(d.decision_id for d in feas.decisions) or feas.summary)
            print("WARNING: continuing although feasibility is blocked (--acknowledge-blocked recorded as an approval).")
        else:
            from desk.errors import EngineeringDecisionRequired
            raise EngineeringDecisionRequired(
                f"STOP: routing is blocked before the engine starts: {feas.summary}. See state/route/feasibility.json"
                + (" and state/route/engineering_decisions.json" if feas.decisions else "")
                + ". No spacing rule was changed; decide the options above (Captain sign-off) or fix placement, then rerun."
                + " --acknowledge-blocked launches the engine anyway and records that choice.",
                category="ROUTER_RULE_CONFLICT" if feas.decisions else "ROUTER_NO_LEGAL_ESCAPE", decisions=[d.decision_id for d in feas.decisions])

    # Phase 10-12: External engine execution via RoutingEngineOrchestrator
    profiler.start_phase(10, category="PROCESS")
    ses = os.path.join(wd, "desk_route.ses")
    orchestrator = RoutingEngineOrchestrator()

    # Engine smoke run (2 passes on a tiny fixture) proves this host's engine writes a SES before a long run.
    if "--skip-smoke" not in args:
        from desk.routing.dsn_fixture import tiny_board_dsn
        _smoke_dir = os.path.join(wd, "smoke")
        os.makedirs(_smoke_dir, exist_ok=True)
        with open(os.path.join(_smoke_dir, "smoke.dsn"), "w", encoding="utf-8") as _f:
            _f.write(tiny_board_dsn(nets=4))
        _smoke = orchestrator.smoke_test(os.path.join(_smoke_dir, "smoke.dsn"), _smoke_dir)
        print(f"Engine smoke run: {_smoke.engine_version} {_smoke.status} in {_smoke.duration_sec}s, SES {_smoke.ses_generated}")
        if not _smoke.success:
            raise SystemExit(f"STOP: {_smoke.error_message}")

    _prev_ses = os.path.join(wd, "desk_route_prev.ses") if "--continue" in args and os.path.exists(os.path.join(wd, "desk_route_prev.ses")) else None
    _via_costs = 80 if len(dense_report.routable_layers) <= 2 else None   # discourage via hopping when only 2 signal layers remain
    # Chunked execution: every chunk ends on its own so the engine writes its SES; the best SES is kept and
    # continued (-de dsn+ses). A plateau never terminates the JVM (on Windows that loses the board; INC-20261112-009).
    # Adaptive chunks (desk/routing/adaptive.py): the cap per chunk comes from the pass budget, the window from the
    # mode, the actual passes per chunk from measured pass durations. The checkpoint keeps the best valid SES.
    _chunk_cap = max(4, min(8, passes // 4))
    exec_result = orchestrator.execute_routing_chunked(
        dsn_path=tuned_dsn_path,
        ses_path=ses,
        working_dir=wd,
        chunk_passes=_chunk_cap,
        max_chunks=max(2, passes // 2 + 1),
        plateau_chunks=2,
        budget_sec=mode_cfg.timeout_sec,
        chunk_timeout_sec=max(300.0, mode_cfg.timeout_sec / 3.0),
        first_passes=2,
        priority_net_classes=priority_classes,
        plane_nets=plane_nets,
        via_costs=_via_costs,
        input_ses=_prev_ses,
    )
    profiler.end_phase()
    for _c in exec_result.engine_config.get("chunks", []):
        print(f"  chunk {_c['chunk']}: {_c['status']} [{_c.get('outcome', '')}] unrouted {_c['initial_unrouted']} -> {_c['final_unrouted']} "
              f"in {_c['seconds']}s ({_c['passes']}/{_c.get('planned_passes', '?')} passes, ses {_c.get('ses')}, accepted {_c.get('accepted')})")
    _ec = exec_result.engine_config
    print(f"Engine {exec_result.engine_version}: {exec_result.passes_completed} passes, checkpoint best {exec_result.final_unrouted} unrouted, "
          f"observed best {_ec.get('observed_best_unrouted')}, outcomes {_ec.get('chunk_outcomes')}, restores {exec_result.restores_seen}")
    if _ec.get("failure_category"):
        from desk.reliability.models import FailureRecord, FailureCategory
        _fr = FailureRecord.new(FailureCategory(_ec["failure_category"]), "desk.routing.orchestrator", "execute_routing_chunked",
                                exec_result.error_message or exec_result.status, project_id=os.path.basename(proj.rstrip("/\\")),
                                document_uuid=P["pcb_uuid"], window_id=str(P.get("window_id") or ""), engine_version=exec_result.engine_version,
                                command=list(exec_result.command), params={"chunks": _ec.get("chunks"), "plans": _ec.get("plans"),
                                                                            "outcomes": _ec.get("chunk_outcomes"), "mode": mode_cfg.mode_name},
                                stdout_tail=exec_result.stdout_summary[-2000:], stderr_tail=exec_result.stderr_summary[-2000:])
        _fr.add_evidence("file", os.path.join(wd, "progress_chunks.json"), "chunk history with plans and outcomes")
        _fr.add_evidence("file", os.path.join(wd, "freerouting.log"), "engine log of the last chunk")
        try:
            atomic_write_json(os.path.join(wd, "route_failure.json"), _fr.to_dict(), indent=1)
        except Exception:
            pass
        print(f"ROUTE FAILURE {_fr.failure_id}: {_fr.category.value} (state/route/route_failure.json)")
    if exec_result.ses_generated:
        try:
            shutil.copyfile(ses, os.path.join(wd, "desk_route_prev.ses"))   # kept for --continue (incremental re-route)
        except Exception:
            pass

    print(f"Routing Engine Result: {exec_result.status} in {exec_result.duration_sec:.1f}s ({exec_result.engine_version})")
    if not exec_result.success and not (exec_result.ses_generated and exec_result.ses_size_bytes > 0):
        raise SystemExit(f"STOP: Routing failed ({exec_result.status}): {exec_result.error_message}")

    # Phase 15: SES import into EasyEDA Pro
    profiler.start_phase(15, category="IPC")
    b64 = base64.b64encode(open(ses, "rb").read()).decode()
    with ops.write_op(proj, "route_import", "PCB", approval=approval_id) as rec:
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
            with ops.write_op(proj, "route_widen", "PCB", classification=ops.OP_IDEMPOTENT_MUTATION, approval=approval_id):
                check(ex(G + mod_code, timeout=60, window_id=P.get("window_id"), is_mutation=True))
            time.sleep(2.0)
        print("Power trace widening: " + (", ".join(
            f"{n} {p.widened_segments}/{p.total_segments} -> {widen_targets[n]:.0f} mil" for n, p in widen_plans.items()) or "no targets"))
    except Exception as e:
        print("Warning: Power trace widening deferred:", e)

    # Rebuild copper pours to refresh ground planes around newly routed tracks
    try:
        rebuild_js = 'const pours = await eda.pcb_PrimitivePour.getAll(); for(const p of pours){ try{ if(p.rebuildCopperRegion) await p.rebuildCopperRegion(); }catch(e){} } await eda.pcb_Document.save(); return true;'
        with ops.write_op(proj, "route_repour", "PCB", classification=ops.OP_IDEMPOTENT_MUTATION, approval=approval_id):
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
    # Declared planes count as conductors (pads/vias/tracks inside them on their layer). Until poured-copper
    # geometry is read back live, the declared polygon is the best available evidence and is labelled as such.
    _layer_ids = {"top": 1, "bottom": 2}
    _layer_ids.update({f"inner{i}": 14 + i for i in range(1, 33)})
    _ox, _oy = plan.get("origin_mm", [0.0, 0.0])
    declared_zones = [{"net": pl["net"], "layer": _layer_ids.get(str(pl["layer"]).lower().replace(" ", ""), 1),
                       "polygon": [[(x + _ox) * MIL, (y + _oy) * MIL] for x, y in pl["polygon_mm"]]}
                      for pl in plan.get("planes", []) if pl.get("polygon_mm")]
    conn_result = PhysicalConnectivityVerifier.verify_board(
        pcb_dump=dump,
        tracks=readback_tracks,
        vias=readback_vias,
        zones=declared_zones,
    )
    if declared_zones:
        print(f"Connectivity evidence: {len(declared_zones)} declared plane polygon(s) treated as conductors (not poured-copper readback)")
    print("Physical Connectivity:", conn_result.summary)
    _fully_routed = conn_result.total_nets > 0 and conn_result.fully_connected_nets == conn_result.total_nets
    print("ROUTING VERDICT:", "FULL (every populated net physically connected on readback)" if _fully_routed else
          f"PARTIAL ({conn_result.fully_connected_nets}/{conn_result.total_nets} nets; engine status {exec_result.status} is not a routing verdict)")
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
    return 0 if _fully_routed else 3
