"""DESK entry point for agents: discover tools cheaply and recover from interrupted live writes.
  python tools/desk.py tools                         one line per tool (what it does) - read this, not the tool sources
  python tools/desk.py dashboard                     launch local Mission Control dashboard and open in browser
  python tools/desk.py serve [--port <P>]            start local Mission Control HTTP & SSE server
  python tools/desk.py status [--json]               display live engineering pipeline progress & status
  python tools/desk.py auth [configure|status|test]  secure credential vault management
  python tools/desk.py settings                      ecosystem provider health and readiness dashboard
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
    port = int(a[a.index("--port") + 1]) if "--port" in a else 49620
    proj = a[a.index("--project") + 1] if "--project" in a else "projects/WATCH"
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
    print(f"Press Ctrl+C to stop dashboard server.\n")

    if "--no-open" not in a:
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
    port = int(a[a.index("--port") + 1]) if "--port" in a else 49620
    proj = a[a.index("--project") + 1] if "--project" in a else "projects/WATCH"
    from desk.runtime.projection import get_execution_projection
    from desk.runtime.server import DeskServer

    get_execution_projection(proj)
    server = DeskServer(port=port)
    url, p = server.start(background=False)
    sys.exit(0)

if a[0] == "status":
    proj = a[a.index("--project") + 1] if "--project" in a else "projects/WATCH"
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

if a[0] == "auth":
    from desk.auth.cli import run_auth_cli
    run_auth_cli(a[1:])
    sys.exit(0)

if a[0] == "settings":
    from desk.ui.settings import run_settings_cli
    run_settings_cli()
    sys.exit(0)

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
