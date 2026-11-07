"""EasyEDA's own schematic ERC (independent from DESK's offline checks). Live, read-only.
Usage: python tools/erc.py projects/<product> [--json]   exit 0 only with 0 errors.
Uses sch_Drc.check(strict=true, userInterface=false, includeVerboseError=true)."""
import sys, json, collections
from _common import ex, guard, load_project, check

proj = sys.argv[1]; P = load_project(proj)
r = check(ex(guard(P["sheet_uuid"]) + 'const r=await eda.sch_Drc.check(true,false,true); return Array.isArray(r)?r:{raw:r};', timeout=300, window_id=P.get("window_id")))
items = r if isinstance(r, list) else []
def level(e): return str(e.get("errorLevel") or e.get("level") or e.get("type") or "").lower()
def text(e): return str(e.get("message") or e.get("errorMessage") or e.get("msg") or json.dumps(e)[:160])
errs = [e for e in items if "warn" not in level(e)]
warns = [e for e in items if "warn" in level(e)]
if "--json" in sys.argv: print(json.dumps({"errors": len(errs), "warnings": len(warns), "items": items[:50], "raw": r if not items else None}))
else:
    c = collections.Counter(text(e)[:90] for e in items)
    for t, n in c.most_common(25): print(f"{n:4d}x {t}")
    print(f"ERC: {len(errs)} errors, {len(warns)} warnings" + ("" if isinstance(r, list) else f" (unexpected result: {str(r)[:200]})"))
sys.exit(0 if isinstance(r, list) and not errs else 1)
