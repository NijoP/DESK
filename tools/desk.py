"""DESK entry point for agents: discover tools cheaply and recover from interrupted live writes.
  python tools/desk.py tools                         one line per tool (what it does) - read this, not the tool sources
  python tools/desk.py auth [configure|status|test]  secure credential vault management
  python tools/desk.py settings                      ecosystem provider health and readiness dashboard
  python tools/desk.py recover projects/<P>          list unfinished/dirty live operations and how to resolve each
  python tools/desk.py recover projects/<P> --clear  resolve dirty builds by running tools/clear_block.py for them (live)
  python tools/desk.py recover projects/<P> --mark-resolved <op_id> --reason "checked by hand"
"""
import os, sys, glob, subprocess, ast
from _common import S  # noqa: F401
from desk import ops

a = sys.argv[1:]
if not a or a[0] == "tools":
    here = os.path.dirname(os.path.abspath(__file__))
    for f in sorted(glob.glob(os.path.join(here, "*.py"))):
        n = os.path.basename(f)
        if n.startswith("_"): continue
        with open(f, encoding="utf-8") as h:
            doc = ast.get_docstring(ast.parse(h.read())) or ""
        print(f"{n:16s} {doc.splitlines()[0] if doc else ''}"[:150])
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
    proj = a[1]; pend = ops.pending(proj)
    if not pend: print("no pending operations"); sys.exit(0)
    if "--mark-resolved" in a:
        i = a.index("--mark-resolved"); oid = a[i + 1]
        reason = a[a.index("--reason") + 1] if "--reason" in a else ""
        if not reason: raise SystemExit("--reason is required")
        ops.resolve_pending(proj, oid, reason); print("resolved", oid); sys.exit(0)
    for p in pend:
        hint = (f"python tools/clear_block.py {proj} {p['target']}  then rebuild" if p["op"] == "build" else
                "inspect PCB, restore EasyEDA revision if needed" if p["op"] == "route_import" else "inspect, then --mark-resolved")
        print(f"{p['id']} {p['op']} {p['target']} {'DIRTY' if p.get('dirty') else 'interrupted'} -> {hint}")
        if "--clear" in a and p["op"] == "build":
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "clear_block.py"), proj, p["target"]])
            print("clear_block rc", r.returncode)
    sys.exit(0)
raise SystemExit(__doc__)
