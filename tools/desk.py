"""DESK entry point for agents: discover tools cheaply and recover from interrupted live writes.
  python tools/desk.py tools                         one line per tool (what it does) - read this, not the tool sources
  python tools/desk.py dashboard                     launch local Mission Control dashboard and open in browser
  python tools/desk.py serve [--port <P>]            start local Mission Control HTTP & SSE server
  python tools/desk.py status [--json]               display live engineering pipeline progress & status
  python tools/desk.py rework [start|status|audit|plan|issues|approve|execute|report] rework existing PCB
  python tools/desk.py auth [configure|status|test]  secure credential vault management
  python tools/desk.py settings                      ecosystem provider health and readiness dashboard
  python tools/desk.py doctor [--project <P>] [--json] check prerequisites (bridge, Java, Freerouting, CLIs, project binding) with fixes
  python tools/desk.py agent projects/<P> "<task>" [--model <id>] [--allow-mutation] [--max-turns N] [--json]
                                                     tool-calling agent on NVIDIA NIM (Nemotron 3 Ultra by default): reads the sheet, plans wires, mutates only with --allow-mutation
  python tools/desk.py recover projects/<P>          list unfinished/dirty live operations and how to resolve each
  python tools/desk.py recover projects/<P> --clear  resolve dirty builds by running tools/clear_block.py for them (live)
  python tools/desk.py recover projects/<P> --mark-resolved <op_id> --reason "checked by hand"
"""
import ast
import glob
import json
import os
import subprocess
import sys
import time
import webbrowser

from _common import S  # noqa: F401
from desk import ops

a = sys.argv[1:]
if not a or a[0] == "tools":
    here = os.path.dirname(os.path.abspath(__file__))
    for f in sorted(glob.glob(os.path.join(here, "*.py"))):
        n = os.path.basename(f)
        if n.startswith("_"):
            continue
        with open(f, encoding="utf-8") as h:
            doc = ast.get_docstring(ast.parse(h.read())) or ""
        print(f"{n:16s} {doc.splitlines()[0] if doc else ''}"[:150])
    sys.exit(0)

if a[0] == "dashboard":
    port = int(a[a.index("--port") + 1]) if "--port" in a else 49630
    proj = a[a.index("--project") + 1] if "--project" in a else "projects/WATCH"
    if not os.path.exists(proj) and os.path.exists(os.path.join(S.ROOT, proj)):
        proj = os.path.join(S.ROOT, proj)
    from desk.runtime.projection import get_execution_projection
    from desk.runtime.server import DeskServer

    get_execution_projection(proj)
    server = DeskServer(port=port)
    url, p = server.start(background=True)
    print(f"\n==================================================================")
    print(f"             DESK LOCAL MISSION CONTROL RUNNING                   ")
    print(f"==================================================================")
    print(f"URL:     {url}")
    print(f"Project: {proj}")
    print(f"Mode:    Read-Only Event-Driven Monitoring (SSE)")
    print(f"[DESK] Mission Control live at {url}")
    print(f"Press Ctrl+C to stop dashboard server.\n")

    if "--open" in a or "--no-open" not in a:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Mission Control server...")
        server.stop()
        sys.exit(0)

if a[0] == "serve":
    port = int(a[a.index("--port") + 1]) if "--port" in a else 49630
    proj = a[a.index("--project") + 1] if "--project" in a else "projects/WATCH"
    if not os.path.exists(proj) and os.path.exists(os.path.join(S.ROOT, proj)):
        proj = os.path.join(S.ROOT, proj)
    from desk.runtime.projection import get_execution_projection
    from desk.runtime.server import DeskServer

    get_execution_projection(proj)
    server = DeskServer(port=port)
    url, p = server.start(background=False)
    sys.exit(0)

if a[0] == "status":
    proj = a[a.index("--project") + 1] if "--project" in a else "projects/WATCH"
    if not os.path.exists(proj) and os.path.exists(os.path.join(S.ROOT, proj)):
        proj = os.path.join(S.ROOT, proj)
    from desk.runtime.projection import CANONICAL_STAGES, STAGE_NAMES, get_execution_projection
    projection = get_execution_projection(proj)
    summary = projection.get_summary()

    if "--json" in a:
        print(json.dumps(summary, indent=2))
        sys.exit(0)

    # Pretty terminal rendering
    cols = 78
    print("=" * cols)
    print("                 DESK LOCAL MISSION CONTROL STATUS                ".center(cols))
    print("=" * cols)
    print(f"Project:    {summary['project_id']}")
    print(f"Execution:  {summary['execution_id']} [{summary['status']}]")
    prog = summary['overall_progress']
    bars = int(prog / 100.0 * 30)
    bar_str = "[" + "#" * bars + "." * (30 - bars) + "]"
    print(f"Progress:   {bar_str} {prog:.1f}%")
    print(f"Stage:      {summary['current_stage_name']}")
    print(f"Activity:   {summary['current_activity']}")
    print(f"Duration:   {summary['duration_s']:.1f}s | Warnings: {summary['warning_count']}")

    print("\nENGINEERING STAGES (M1-M6 WORKFLOW):")
    for s in CANONICAL_STAGES:
        st = summary["stages"][s]
        stat = st["status"]
        stat_fmt = f"[{stat:^9}]"
        name = st["display_name"]
        dur = f"({st['duration_s']:.1f}s)" if st["duration_s"] else ""
        prog_txt = f"{st['progress']:.0f}%" if st["progress"] is not None else ""
        print(f"  {stat_fmt} {name:48s} {prog_txt:>4s} {dur}")

    res = summary["engineering_results"]
    hw = summary["metrics"]
    print("\nENGINEERING ARTIFACTS & ACCEPTANCE:")
    print(f"  Tracks: {res['tracks_generated']} | Vias: {res['vias_generated']} | Zones: {res['copper_zones_processed']} | DRC Errors: {res['drc_violations']}")
    print(f"  Acceptance State: {res['final_acceptance_state']} | Evidence: {res['evidence_status']}")
    print(f"  Host Resources:   RAM: {hw['process_ram_mb']} MB (Avail: {hw['available_ram_mb']} MB) | Cores: {hw['logical_cores']} | Tier: {hw['resource_tier']}")
    print("=" * cols)
    sys.exit(0)

if a[0] == "rework":
    from desk.rework import (
        ReworkSessionLifecycle,
        ReworkExecutionPolicy,
        create_rework_session,
        get_or_create_rework_session,
        get_latest_rework_session,
        load_rework_session,
        ECADConnectionManager,
        BaselineCaptureEngine,
        ReworkAuditEngine,
        RepairPlanner,
        RepairExecutor,
        ManufacturingReadinessEngine,
        Issue,
        ApprovalToken,
        ProjectBinding,
    )
    from desk.snapshot import IndexedPCBSnapshot

    sub = a[1] if len(a) > 1 and not a[1].startswith("-") else "status"
    proj_arg = [arg for arg in a[1:] if arg.startswith("projects/") or (os.path.isdir(arg) and not arg.startswith("-"))]
    proj = proj_arg[0] if proj_arg else (os.environ.get("DESK_PROJECT") or "projects/WATCH")
    norm_proj = os.path.abspath(proj)

    if sub == "start":
        pol = a[a.index("--policy") + 1].upper() if "--policy" in a else "AUDIT_ONLY"
        session = create_rework_session(norm_proj, policy=pol)
        print(f"\n==================================================================")
        print(f"               DESK REWORK MODE ACTIVATED                         ")
        print(f"==================================================================")
        print(f"Session ID:  {session.session_id}")
        print(f"Project:     {proj}")
        print(f"Policy:      {session.policy}")
        print(f"Status:      {session.state}")
        print(f"Mode:        Preserve Existing Engineering Decisions")
        print(f"[DESK] Mission Control live at http://127.0.0.1:49630\n")

        # Step 1: Connect & Bind
        print("Checking EasyEDA Pro connection...")
        try:
            _pj = os.path.join(norm_proj, "project.json")
            _pref = json.load(open(_pj, encoding="utf-8")).get("window_id") if os.path.exists(_pj) else None
            binding = ECADConnectionManager.discover_project_identity(norm_proj, preferred_window_id=_pref)
            session.window_id = binding.window_id
            session.pcb_uuid = binding.pcb_uuid
            session.sheet_uuid = binding.sheet_uuid
            session.is_identity_confirmed = True
            session.transition_to(ReworkSessionLifecycle.IDENTITY_CONFIRMATION, "ECAD window identified")
            print(f"[OK] Application: {binding.app_version}")
            print(f"[OK] Window ID:   {binding.window_id}")
            print(f"[OK] Project:     {binding.project_name} ({binding.project_uuid})")
        except Exception as e:
            print(f"[NOTE] Live ECAD connection offline: {e}")
            session.transition_to(ReworkSessionLifecycle.INTAKE, "Operating in offline inspection mode")

        # Step 2: Baseline Capture
        print("\nCapturing existing project state...")
        dump_path = os.path.join(norm_proj, "state", "pcb_dump.json")
        comps = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
        baseline = BaselineCaptureEngine.capture_from_data(
            session_id=session.session_id,
            project_path=norm_proj,
            components_dump=comps,
        )
        BaselineCaptureEngine.save_baseline(baseline)
        session.baseline_revision = baseline.composite_fingerprint
        session.current_revision = baseline.composite_fingerprint
        session.transition_to(ReworkSessionLifecycle.BASELINE_CAPTURE, "Baseline fingerprint generated")
        print(f"[OK] Baseline Fingerprint: {baseline.composite_fingerprint}")
        print(f"[OK] Components Indexed:  {baseline.components_count}")
        print(f"[OK] Immutable baseline saved to state/rework/{session.session_id}/baseline.json\n")
        sys.exit(0)

    session = get_latest_rework_session(norm_proj)
    if not session:
        print(f"No active rework session found for {proj}. Start one with: python tools/desk.py rework start {proj}")
        sys.exit(0)

    if sub == "status":
        print(f"\n==================================================================")
        print(f"               DESK REWORK SESSION STATUS                         ")
        print(f"==================================================================")
        print(f"Session ID:  {session.session_id}")
        print(f"Project:     {proj}")
        print(f"Lifecycle:   {session.state}")
        print(f"Policy:      {session.policy}")
        print(f"Baseline:    {session.baseline_revision or 'NOT_CAPTURED'}")
        print(f"Current:     {session.current_revision or 'NOT_CAPTURED'}")
        print(f"Issues:      {session.detected_issues_count} detected")
        print(f"Repairs:     {session.completed_repairs_count} completed / {session.approved_repairs_count} approved")
        print(f"==================================================================\n")
        sys.exit(0)

    if sub == "audit":
        print(f"Executing 8-domain engineering audit for {proj}...")
        dump_path = os.path.join(norm_proj, "state", "pcb_dump.json")
        comps = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
        snap = IndexedPCBSnapshot(raw_dump=comps, project_id=os.path.basename(norm_proj))
        auditor = ReworkAuditEngine(session.session_id, norm_proj, session.baseline_revision or "")
        issues = auditor.run_full_audit(snap)
        session.detected_issues_count = len(issues)
        session.transition_to(ReworkSessionLifecycle.ISSUE_REVIEW, f"Audit discovered {len(issues)} issues")
        print(f"\nAudit complete! Discovered {len(issues)} issues across 8 domains:")
        for iss in issues:
            print(f"  [{iss.severity:<8}] {iss.issue_id}: {iss.title}")
        print(f"\nSaved inventory to state/rework/{session.session_id}/issue_inventory.json")
        sys.exit(0)

    if sub == "plan":
        plan = RepairPlanner.load_plan(norm_proj, session.session_id)
        if not plan:
            inv_path = os.path.join(norm_proj, "state", "rework", session.session_id, "issue_inventory.json")
            if not os.path.exists(inv_path):
                print(f"No issue inventory found. Run audit first: python tools/desk.py rework audit {proj}")
                sys.exit(0)
            with open(inv_path, "r", encoding="utf-8") as f:
                issues = [Issue.from_dict(d) for d in json.load(f)]
            dump_path = os.path.join(norm_proj, "state", "pcb_dump.json")
            comps = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
            plan = RepairPlanner.create_plan(
                session_id=session.session_id,
                project_path=norm_proj,
                baseline_revision=session.baseline_revision or "",
                issues=issues,
                existing_components_count=len(comps),
            )
            session.transition_to(ReworkSessionLifecycle.REPAIR_PLANNING, f"Generated repair plan with {len(plan.repairs)} actions")

        print(f"\n==================================================================")
        print(f"               DESK SURGICAL REPAIR PLAN                          ")
        print(f"==================================================================")
        print(f"Session: {session.session_id} | Planned Repairs: {len(plan.repairs)}")
        for r in plan.repairs:
            stat = f"[{r.approval_status}]"
            deps = f"(deps: {', '.join(r.dependencies)})" if r.dependencies else ""
            print(f"  {r.sequence_number}. {r.repair_id}: {r.action_type:<20} {stat:<10} {deps}")
            print(f"     -> {r.description}")
        print(f"\nProtected original design: {plan.protected_summary}")
        print(f"==================================================================\n")
        sys.exit(0)

    if sub == "issues":
        inv_path = os.path.join(norm_proj, "state", "rework", session.session_id, "issue_inventory.json")
        if not os.path.exists(inv_path):
            print(f"No issue inventory found. Run: python tools/desk.py rework audit {proj}")
            sys.exit(0)
        with open(inv_path, "r", encoding="utf-8") as f:
            issues = json.load(f)
        print(f"\nIssue Inventory ({len(issues)} issues):")
        for i in issues:
            print(f"  {i['issue_id']} [{i['severity']}]: {i['title']} ({i['category']})")
        sys.exit(0)

    if sub == "approve":
        r_id = next((arg for arg in a if arg.startswith("RP-")), None)
        if not r_id:
            raise SystemExit("Usage: python tools/desk.py rework approve [projects/<P>] <RP-XXXX>")
        plan = RepairPlanner.load_plan(norm_proj, session.session_id)
        if not plan:
            raise SystemExit("No repair plan found.")
        target_repair = next((r for r in plan.repairs if r.repair_id == r_id), None)
        if not target_repair:
            raise SystemExit(f"Repair ID '{r_id}' not found in plan.")
        token = RepairPlanner.generate_approval_token(
            repair=target_repair,
            session_id=session.session_id,
            project_id=session.project_id,
            revision_hash=session.current_revision or "",
            actor="CAPTAIN",
        )
        target_repair.approval_status = "APPROVED"
        target_repair.approval_token = token.token
        RepairPlanner.save_approval(norm_proj, session.session_id, token)
        session.approved_repairs_count += 1
        session.transition_to(ReworkSessionLifecycle.AWAITING_APPROVAL, f"Approved {r_id}")
        plan_path = os.path.join(norm_proj, "state", "rework", session.session_id, "repair_plan.json")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, indent=2)
        print(f"[OK] Approved {r_id}. Generated token: {token.token}")
        sys.exit(0)

    if sub == "execute":
        r_id = next((arg for arg in a if arg.startswith("RP-")), None)
        if not r_id:
            raise SystemExit("Usage: python tools/desk.py rework execute [projects/<P>] <RP-XXXX>")
        plan = RepairPlanner.load_plan(norm_proj, session.session_id)
        if not plan:
            raise SystemExit("No repair plan found.")
        target_repair = next((r for r in plan.repairs if r.repair_id == r_id), None)
        if not target_repair:
            raise SystemExit(f"Repair ID '{r_id}' not found in plan.")
        if target_repair.approval_status != "APPROVED":
            raise SystemExit(f"STOP: Repair '{r_id}' requires explicit approval before execution.")
        
        app_path = os.path.join(norm_proj, "state", "rework", session.session_id, "approvals.json")
        token = None
        if os.path.exists(app_path):
            with open(app_path, "r", encoding="utf-8") as f:
                apps = json.load(f)
            tok_dict = next((t for t in apps if t["repair_id"] == r_id), None)
            if tok_dict:
                token = ApprovalToken.from_dict(tok_dict)
        if not token:
            raise SystemExit(f"Valid approval token not found for {r_id}.")

        dump_path = os.path.join(norm_proj, "state", "pcb_dump.json")
        comps = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
        snap = IndexedPCBSnapshot(raw_dump=comps, project_id=session.project_id)
        binding = ProjectBinding(
            project_name=session.project_id,
            project_path=norm_proj,
            project_uuid=f"uuid_{session.project_id.lower()}",
            window_id=session.window_id or "offline",
            eda_port=session.eda_port,
        )

        session.transition_to(ReworkSessionLifecycle.REPAIR_EXECUTION, f"Executing {r_id}")
        res = RepairExecutor.execute_surgical_repair(
            repair=target_repair,
            snapshot=snap,
            binding=binding,
            approval_token=token,
            project_path=norm_proj,
            session_id=session.session_id,
        )
        print(f"Execution Result for {r_id}:")
        print(f"  Status:       {res.status}")
        print(f"  Duration:     {res.duration_ms} ms")
        print(f"  Readback:     {res.readback_data}")
        print(f"  Verification: {res.verification_details}")
        if res.verification_passed:
            session.completed_repairs_count += 1
            session.current_revision = res.after_fingerprint
            session.transition_to(ReworkSessionLifecycle.VERIFICATION, f"Verified {r_id}")
            print(f"[OK] Repair {r_id} VERIFIED and committed to repair history.")
        else:
            session.failed_repairs_count += 1
            session.transition_to(ReworkSessionLifecycle.NEEDS_REVIEW, f"Verification failed on {r_id}")
            print(f"[FAIL] Repair {r_id} FAILED verification: {res.error_message}")
        sys.exit(0)

    if sub == "report":
        dump_path = os.path.join(norm_proj, "state", "pcb_dump.json")
        comps = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
        snap = IndexedPCBSnapshot(raw_dump=comps, project_id=session.project_id)
        assessment = ManufacturingReadinessEngine.evaluate(
            session_id=session.session_id,
            project_path=norm_proj,
            snapshot=snap,
            issues_count=session.detected_issues_count,
            resolved_count=session.completed_repairs_count,
        )
        session.transition_to(ReworkSessionLifecycle.RELEASE_ASSESSMENT, f"Readiness outcome: {assessment.outcome}")
        print(f"\n==================================================================")
        print(f"         DESK REWORK MANUFACTURING READINESS REPORT               ")
        print(f"==================================================================")
        print(f"Project:     {assessment.project_id}")
        print(f"Session:     {assessment.session_id}")
        print(f"Revision:    {assessment.final_revision}")
        print(f"Outcome:     {assessment.outcome}")
        print(f"Score:       {assessment.total_score:.1f} / 100")
        print(f"Hard Gates:  {'ALL PASSED' if assessment.hard_gates_passed else 'FAILED/INCOMPLETE'}")
        print(f"Issues:      {assessment.issues_resolved}/{assessment.issues_total} resolved ({assessment.issues_outstanding} outstanding)")
        print(f"Report Path: {assessment.report_path}")
        print(f"==================================================================\n")
        sys.exit(0)

if a[0] == "auth":
    from desk.auth.cli import run_auth_cli
    run_auth_cli(a[1:])
    sys.exit(0)

if a[0] == "settings":
    from desk.ui.settings import run_settings_cli
    run_settings_cli()
    sys.exit(0)

if a[0] == "doctor":
    from desk.doctor import main as doctor_main
    sys.exit(doctor_main(a[1:]))

if a[0] == "agent":
    from desk.orchestrator.agent_loop import run_agent
    opt = a[1:]
    skip = set()
    for flag in ("--model", "--max-turns", "--window"):
        if flag in opt:
            skip.add(opt.index(flag) + 1)
    pos = [x for i, x in enumerate(opt) if not x.startswith("--") and i not in skip]
    if len(pos) < 2:
        raise SystemExit('usage: desk.py agent projects/<P> "<task>" [--model <id>] [--allow-mutation] [--max-turns N] [--json]')
    proj, task = pos[0], " ".join(pos[1:])
    run = run_agent(task, project=proj,
                    model=opt[opt.index("--model") + 1] if "--model" in opt else None,
                    allow_mutation="--allow-mutation" in opt,
                    max_turns=int(opt[opt.index("--max-turns") + 1]) if "--max-turns" in opt else 12,
                    window_id=opt[opt.index("--window") + 1] if "--window" in opt else None)
    if "--json" in opt:
        print(json.dumps(run.to_dict(), indent=1, ensure_ascii=False))
    else:
        print(run.final_text or f"(no final text; stopped: {run.stopped_reason})")
        print(f"-- {run.model}: {run.turns} turns, {run.tool_calls} tool calls, {run.elapsed_s}s, stopped={run.stopped_reason}, trace={run.trace_path}")
    sys.exit(0 if run.stopped_reason == "final" else 1)

if a[0] == "recover":
    proj = a[1]
    pend = ops.pending(proj)
    if not pend:
        print("no pending operations")
        sys.exit(0)
    if "--mark-resolved" in a:
        i = a.index("--mark-resolved")
        oid = a[i + 1]
        reason = a[a.index("--reason") + 1] if "--reason" in a else ""
        if not reason:
            raise SystemExit("--reason is required")
        ops.resolve_pending(proj, oid, reason)
        print("resolved", oid)
        sys.exit(0)
    for p in pend:
        hint = (f"python tools/clear_block.py {proj} {p['target']}  then rebuild" if p["op"] == "build" else
                "inspect PCB, restore EasyEDA revision if needed" if p["op"] == "route_import" else "inspect, then --mark-resolved")
        print(f"{p['id']} {p['op']} {p['target']} {'DIRTY' if p.get('dirty') else 'interrupted'} -> {hint}")
        if "--clear" in a and p["op"] == "build":
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "clear_block.py"), proj, p["target"]])
            print("clear_block rc", r.returncode)
    sys.exit(0)

raise SystemExit(__doc__)
