"""Automated routing round-trip: EasyEDA DSN export -> Freerouting (headless) -> SES import -> DRC.
Usage: python tools/route.py projects/<product> [--passes 30] [--keep-existing] [--dry]
Needs Java 17+ and the Freerouting jar: set FREEROUTING_JAR or put it at library/tools/freerouting.jar
  (get it: gh release download -R freerouting/freerouting --pattern "freerouting-*.jar" -D library/tools)
Order of work (docs/05_ROUTING.md): route critical nets by hand first (switching loops, USB pair, RF), set net
classes + diff pairs (tools/pcb_rules.py), then autoroute the rest; --keep-existing is the default behaviour of
Freerouting (existing tracks are fixed). The DSN/SES files are kept in state/route/ for audit.
After import: tools/drc.py must pass; tools/release.py will refuse otherwise."""
import sys, os, json, subprocess, shutil, base64, time
from _common import ex, guard, load_project, check, S
from desk.bridge import fetch_file
from desk import ops

a = sys.argv[1:]; proj = a[0]; P = load_project(proj)
passes = a[a.index("--passes") + 1] if "--passes" in a else "30"
jar = os.environ.get("FREEROUTING_JAR") or os.path.join(S.ROOT, "library", "tools", "freerouting.jar")
if not os.path.exists(jar): raise SystemExit(f"STOP: Freerouting jar not found ({jar}). See usage.")
if not shutil.which("java"): raise SystemExit("STOP: java not on PATH")
G = guard(P["pcb_uuid"]); wd = os.path.join(proj, "state", "route"); os.makedirs(wd, exist_ok=True)
dsn = fetch_file(G + 'const f=await eda.pcb_ManufactureData.getDsnFile("desk_route");', wd)
print("DSN:", dsn, os.path.getsize(dsn), "B")
if "--dry" in a: sys.exit(0)
ses = os.path.join(wd, "desk_route.ses")
cmd = ["java", "-jar", jar, "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false"]
t0 = time.time(); p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
with open(os.path.join(wd, "freerouting.log"), "w", encoding="utf-8") as f: f.write(p.stdout + p.stderr)
if p.returncode != 0 or not os.path.exists(ses):
    raise SystemExit(f"STOP: Freerouting failed (rc {p.returncode}); see {wd}/freerouting.log")
print(f"Freerouting done in {time.time() - t0:.0f}s -> {ses}")
b64 = base64.b64encode(open(ses, "rb").read()).decode()
with ops.write_op(proj, "route_import", "PCB") as rec:
    rec["dirty"] = True
    r = check(ex(G + 'const b=atob("%s"); const u=new Uint8Array(b.length); for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);'
                     'const ok=await eda.pcb_Document.importAutoRouteSesFile(new File([u],"desk_route.ses")); return ok;' % b64, timeout=600))
print("SES import:", r)
if r is not True: raise SystemExit("STOP: EasyEDA rejected the SES import")
print("NEXT: python tools/drc.py", proj)
