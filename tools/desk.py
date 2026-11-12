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
  python tools/desk.py domains list|search "<text>"|show <archetype>|classify <requirements.json|"text">|rules <archetype> [--overlays a,b]|validate <requirements.json|"text">|check
                                                     Domain Intelligence: 100 PCB archetypes, component families and the deterministic rule engine (--json for machine output)
                                                     tool-calling agent on NVIDIA NIM (Nemotron 3 Ultra by default): reads the sheet, plans wires, mutates only with --allow-mutation
  python tools/desk.py config show|schema [--json]   effective configuration (env > ~/.desk/config.json > desk.config.json > default), secrets masked
  python tools/desk.py weft status|workflows|nodes|validate [<workflow>]|serve|run <workflow> --project <P> --requirements <file>|history --project <P>|resume <run-id>
                                                     Weft orchestration: typed workflows over DESK nodes; `weft` alone prints the full help (docs/weft/)
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


def _default_project() -> str:
    """The project is always explicit: --project projects/<P> or DESK_PROJECT. No built-in default."""
    from desk import config as deskcfg
    p = (deskcfg.get("DESK_PROJECT") or "").strip()
    if not p:
        raise SystemExit("no project given: pass --project projects/<P> (or a project path) or set DESK_PROJECT")
    return p



def main(argv):
    """Run one desk.py subcommand; returns the process exit code (importable: tests call main([...]))."""
    from desk.errors import UsageError
    a = list(argv)
    if not a or a[0] == "tools":
        here = os.path.dirname(os.path.abspath(__file__))
        for f in sorted(glob.glob(os.path.join(here, "*.py"))):
            n = os.path.basename(f)
            if n.startswith("_"):
                continue
            with open(f, encoding="utf-8") as h:
                doc = ast.get_docstring(ast.parse(h.read())) or ""
            print(f"{n:16s} {doc.splitlines()[0] if doc else ''}"[:150])
        return 0

    if a[0] == "dashboard":
        port = int(a[a.index("--port") + 1]) if "--port" in a else 49630
        proj = a[a.index("--project") + 1] if "--project" in a else _default_project()
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
            return 0

    if a[0] == "serve":
        port = int(a[a.index("--port") + 1]) if "--port" in a else 49630
        proj = a[a.index("--project") + 1] if "--project" in a else _default_project()
        if not os.path.exists(proj) and os.path.exists(os.path.join(S.ROOT, proj)):
            proj = os.path.join(S.ROOT, proj)
        from desk.runtime.projection import get_execution_projection
        from desk.runtime.server import DeskServer

        get_execution_projection(proj)
        server = DeskServer(port=port)
        url, p = server.start(background=False)
        return 0

    if a[0] == "status":
        proj = a[a.index("--project") + 1] if "--project" in a else _default_project()
        if not os.path.exists(proj) and os.path.exists(os.path.join(S.ROOT, proj)):
            proj = os.path.join(S.ROOT, proj)
        from desk.runtime.projection import CANONICAL_STAGES, STAGE_NAMES, get_execution_projection
        projection = get_execution_projection(proj)
        summary = projection.get_summary()

        if "--json" in a:
            print(json.dumps(summary, indent=2))
            return 0

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
        return 0

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
        proj = proj_arg[0] if proj_arg else _default_project()
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
            return 0

        session = get_latest_rework_session(norm_proj)
        if not session:
            print(f"No active rework session found for {proj}. Start one with: python tools/desk.py rework start {proj}")
            return 0

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
            return 0

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
            return 0

        if sub == "plan":
            plan = RepairPlanner.load_plan(norm_proj, session.session_id)
            if not plan:
                inv_path = os.path.join(norm_proj, "state", "rework", session.session_id, "issue_inventory.json")
                if not os.path.exists(inv_path):
                    print(f"No issue inventory found. Run audit first: python tools/desk.py rework audit {proj}")
                    return 0
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
            return 0

        if sub == "issues":
            inv_path = os.path.join(norm_proj, "state", "rework", session.session_id, "issue_inventory.json")
            if not os.path.exists(inv_path):
                print(f"No issue inventory found. Run: python tools/desk.py rework audit {proj}")
                return 0
            with open(inv_path, "r", encoding="utf-8") as f:
                issues = json.load(f)
            print(f"\nIssue Inventory ({len(issues)} issues):")
            for i in issues:
                print(f"  {i['issue_id']} [{i['severity']}]: {i['title']} ({i['category']})")
            return 0

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
            return 0

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
            return 0

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
            return 0

    if a[0] == "auth":
        from desk.auth.cli import run_auth_cli
        run_auth_cli(a[1:])
        return 0

    if a[0] == "settings":
        from desk.ui.settings import run_settings_cli
        run_settings_cli()
        return 0

    if a[0] == "doctor":
        from desk.doctor import main as doctor_main
        return doctor_main(a[1:])

    if a[0] == "weft":
        from desk.weft.cli import main as weft_main
        return weft_main(a[1:])

    if a[0] == "domains":
        from desk.domain_intelligence import api as dapi
        sub = a[1] if len(a) > 1 else "list"
        # Drop flags AND the values of flags that take one (--project <P>, --overlays <a,b>); otherwise
        # `validate req.json --project projects/P` joins to "req.json projects/P", the file is not found
        # and the JSON path is classified as prose (UPS_1000 run, F-003).
        _valued = {"--project", "--overlays"}
        rest = [x for i, x in enumerate(a[2:]) if not x.startswith("--") and not (i > 0 and a[2:][i - 1] in _valued)]
        as_json = "--json" in a

        def _source(arg):
            if arg and os.path.exists(arg):
                with open(arg, encoding="utf-8") as fh:
                    return json.load(fh) if arg.endswith(".json") else fh.read()
            return arg or ""

        if sub == "list":
            out = dapi.list_domains()
            if as_json:
                print(json.dumps(out, indent=1))
            else:
                for d in out:
                    print(f"{d['domain_id']:20s} {d['name']} ({len(d['archetypes'])})")
                    for x in d["archetypes"]:
                        print(f"    {x['id']:34s} {x['name']}  [{x['maturity']}]")
            return 0
        if sub == "search":
            hits = dapi.search(" ".join(rest))
            print(json.dumps(hits, indent=1) if as_json else "\n".join(f"{h['score']:>4}  {h['archetype_id']:34s} {h['name']} ({h['domain']})" for h in hits))
            return 0
        if sub == "show":
            d = dapi.show(rest[0])
            if as_json:
                print(json.dumps(d, indent=1))
            else:
                print(f"{d['archetype_id']}: {d['name']}  [{d['domain']}, {d['maturity']['status']}]\n{d['description']}")
                for key in ("required_component_roles", "critical_electrical_constraints", "unsupported_conditions", "applicable_standards"):
                    print(f"\n{key}:")
                    for x in d[key]:
                        print("  -", x)
                print("\nrules:")
                for r in d["rules"]:
                    print(f"  {r['rule_id']:18s} {r['severity']:8s} {r['mode']:11s} {r['status']:15s} {r['name']}")
            return 0
        if sub == "classify":
            r = dapi.classify(_source(" ".join(rest)))
            if as_json:
                print(dapi.to_json(r))
            else:
                print(f"primary: {r.primary_archetype}  status: {r.classification_status}  confidence: {r.confidence}")
                print(f"secondary: {r.secondary_archetypes}\noverlays: {r.required_overlays}\nfamilies: {r.required_component_families}")
                print("candidates:", [(c.archetype_id, c.score) for c in r.candidates[:5]])
                for e in r.evidence:
                    print("  evidence:", e)
                for c in r.conflicts:
                    print("  CONFLICT:", c)
                for m in r.missing_information:
                    print("  missing:", m)
            return 0 if r.classification_status == "CLASSIFIED" else 1
        if sub == "rules":
            ov = a[a.index("--overlays") + 1].split(",") if "--overlays" in a else None
            d = dapi.rules_for(rest[0], overlays=ov)
            if as_json:
                print(json.dumps(d, indent=1))
            else:
                print(f"{d['archetype_id']} overlays={d['overlays']} rules={len(d['rules'])}")
                for r in d["rules"]:
                    print(f"  {r['rule_id']:18s} {r['severity']:8s} {r['mode']:11s} {r['status']:15s} {r['name']}  <- {','.join(r['scope_reason'])}")
                for c in d["conflicts"]:
                    print("  CONFLICT:", c)
            return 0
        if sub == "validate":
            proj = a[a.index("--project") + 1] if "--project" in a else "UNBOUND"
            out = dapi.validate_requirements(_source(" ".join(rest)), project_id=proj)
            if as_json:
                print(json.dumps(out, indent=1))
            else:
                c, cp = out["classification"], out["compiled"]
                print(f"primary: {c['primary_archetype']} ({c['classification_status']}, {c['confidence']})  profile status: {cp['status']}")
                print(f"overlays: {cp['overlays']}\nenforced: {len(cp['enforced_rule_ids'])}  advisory: {len(cp['advisory_rule_ids'])}  unsupported: {cp['unsupported_rule_ids']}")
                for b in cp["blocking_issues"]:
                    print("  BLOCKING:", b)
                for e in cp["evaluations"]:
                    if e["outcome"] in ("FAIL", "PASS"):
                        print(f"  {e['outcome']:5s} {e['rule_id']:18s} {e['message'][:110]}")
                for m in cp["missing_information"]:
                    print("  missing:", m)
            return 0 if out["compiled"]["status"] == "READY" else 1
        if sub == "check":
            rep = dapi.validate_library_report()
            print(json.dumps(rep, indent=1) if as_json else (f"library {rep['version']}: {rep['archetypes']} archetypes, {rep['overlays']} overlays, {rep['families']} families, {rep['rules']} rules, {rep['references']} references -> " + ("OK" if rep["ok"] else "\n".join(rep["problems"]))))
            return 0 if rep["ok"] else 1
        raise SystemExit("usage: desk.py domains list|search|show|classify|rules|validate|check")


    if a[0] == "config":
        from desk import config as deskcfg
        sub = a[1] if len(a) > 1 else "show"
        cfg = deskcfg.get_config()
        if sub == "schema":
            rows = cfg.schema_rows()
            if "--json" in a:
                print(json.dumps(rows, indent=1))
            else:
                for r in rows:
                    d = "" if r["default"] is None else f" (default {r['default']})"
                    print(f"{r['key']:<36} {r['type']:<7} {r['group']:<12} {r['description']}{d}")
            return 0
        if sub == "show":
            if "--json" in a:
                print(json.dumps({"rows": cfg.as_rows(), "problems": cfg.validate(),
                                  "user_file": cfg.user_file, "repo_file": cfg.repo_file}, indent=1))
            else:
                print(cfg.render())
            return 1 if cfg.validate() else 0
        raise UsageError("usage: desk.py config show|schema [--json]")

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
        return 0 if run.stopped_reason == "final" else 1

    if a[0] == "recover":
        proj = a[1]
        pend = ops.pending(proj)
        if not pend:
            print("no pending operations")
            return 0
        if "--mark-resolved" in a:
            i = a.index("--mark-resolved")
            oid = a[i + 1]
            reason = a[a.index("--reason") + 1] if "--reason" in a else ""
            if not reason:
                raise SystemExit("--reason is required")
            ops.resolve_pending(proj, oid, reason)
            print("resolved", oid)
            return 0
        for p in pend:
            hint = (f"python tools/clear_block.py {proj} {p['target']}  then rebuild" if p["op"] == "build" else
                    "inspect PCB, restore EasyEDA revision if needed" if p["op"] == "route_import" else "inspect, then --mark-resolved")
            print(f"{p['id']} {p['op']} {p['target']} {'DIRTY' if p.get('dirty') else 'interrupted'} -> {hint}")
            if "--clear" in a and p["op"] == "build":
                r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "clear_block.py"), proj, p["target"]])
                print("clear_block rc", r.returncode)
        return 0

    raise UsageError(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
