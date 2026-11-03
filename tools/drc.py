"""EasyEDA PCB DRC with the board's current rule configuration. Live, read-only (saves nothing).
Usage: python tools/drc.py projects/<product> [--json]   exit 0 only with 0 errors.
Uses pcb_Drc.check(strict=true, userInterface=false, includeVerboseError=true) -> list of violations."""
import sys, json, collections
from _common import ex, guard, load_project, check

proj = sys.argv[1]; P = load_project(proj)
r = check(ex(guard(P["pcb_uuid"]) + 'const r=await eda.pcb_Drc.check(true,false,true); return Array.isArray(r)?r:{raw:r};', timeout=600))
items = r if isinstance(r, list) else []
def key(e): return str(e.get("ruleName") or e.get("errorType") or e.get("type") or e.get("message") or json.dumps(e)[:80])
if "--json" in sys.argv: print(json.dumps({"violations": len(items), "by_rule": collections.Counter(key(e) for e in items), "first": items[:20]}))
else:
    for k, n in collections.Counter(key(e) for e in items).most_common(30): print(f"{n:5d}x {k[:110]}")
    print(f"DRC: {len(items)} violations" + ("" if isinstance(r, list) else f" (unexpected result: {str(r)[:200]})"))
sys.exit(0 if isinstance(r, list) and not items else 1)
