"""Plotus routing pipeline (Stage 3), all DESK/EasyEDA calls verified earlier in this run:
1. DSN export from the live board via DESK tools/route.py --dry (route_wrapper.py),
2. rule edits documented in pcb/routing/ROUTING_RECORD.md (clearance 6.1 mil, smd 6.5, signal 6 mil, power 10 mil,
   GND ROUTED in Stage 3 (run 2b change; run 1 F-0xx lesson), keep-outs around USB-C shell slots and the two VBUS-side slot regions),
3. Freerouting 2.1.0 with --router.job_timeout (writes SES on stop),
4. SES import with DESK route.py Phase-15 code (ses_import_verify.py).
Usage: python route_pipeline.py <run_dir_name> [job_timeout=00:02:30]"""
import sys, os, re, subprocess, shutil
ROOT = r"C:\nemotron test\Plotus\run2\ESP32-S3-Development"
DESK = r"C:\nemotron test\Plotus\DESK"
JAR = r"C:\nemotron test\Plotus\environment\freerouting\freerouting-2.1.0.jar"
run = os.path.join(ROOT, "pcb", "routing", sys.argv[1]); os.makedirs(run, exist_ok=True)
jt = sys.argv[2] if len(sys.argv) > 2 else "00:02:30"
env = dict(os.environ, PYTHONIOENCODING="utf-8", EDA_WINDOW_ID="17ea844c-a5d0-4a6a-b78a-b64521ae7895", FREEROUTING_JAR=JAR)
r = subprocess.run([sys.executable, os.path.join(ROOT, "benchmarks", "route_wrapper.py"), r"..\run2\ESP32-S3-Development\schematic\desk", "--dry"],
                   cwd=DESK, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
open(os.path.join(run, "export.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
if "Dry run completed" not in r.stdout: raise SystemExit("DSN export failed: " + (r.stdout + r.stderr)[-800:])
s = open(os.path.join(ROOT, "schematic", "desk", "state", "route", "desk_route_tuned.dsn"), encoding="utf-8").read()
s = re.sub(r"\(rule \(clear [0-9.]+\)\)", "(rule (clear 6.1))", s, count=1)
s = re.sub(r"\(rule \(clear [0-9.]+ \(type (default_smd|smd_smd)\)\)\)", lambda m: "(rule (clear 6.5 (type %s)))" % m.group(1), s)
s = s.replace("(rule (width 5.00))", "(rule (width 6.00))")
s = re.sub(r"\(clearance [0-9.]+\)", "(clearance 6.1)", s)
W = {"VBUS": 10.0, "VBUS_PROT": 10.0, "5V": 10.0, "3V3": 10.0, "GND": 10.0}
def cls(m):
    return re.sub(r"\(width [0-9.]+\)", "(width %.2f)" % W.get(m.group(1), 6.0), m.group(0))
s = re.sub(r"\(class (\S+) [^\n]*\n(?:[^\n]*\n){0,3}?\s*\(rule \(width [0-9.]+\)[^\n]*", cls, s)
M = 39.37007874
kos = ""
for i, (x, y) in enumerate([(2.73, 17.68), (6.91, 17.68), (6.91, 26.32), (2.73, 26.32)]):
    cx, cy, hx, hy = x * M, y * M, 39.4 + 20, 23.6 + 20
    kos += '    (keepout\n      "usb shell slot %d"\n      (polygon signal 0 %.2f %.2f %.2f %.2f %.2f %.2f %.2f %.2f)\n    )\n' % (i + 1, cx - hx, cy - hy, cx + hx, cy - hy, cx + hx, cy + hy, cx - hx, cy + hy)
for i, (x0, y0, x1, y1) in enumerate([(5.6, 18.9, 7.0, 20.1), (5.6, 23.9, 7.0, 25.1)]):
    kos += '    (keepout\n      "usb vbus-side slot region %d"\n      (polygon signal 0 %.2f %.2f %.2f %.2f %.2f %.2f %.2f %.2f)\n    )\n' % (i + 1, x0 * M, y0 * M, x1 * M, y0 * M, x1 * M, y1 * M, x0 * M, y1 * M)
for i, (x0, y0) in enumerate([(0, 0), (72.0, 0), (0, 42.0), (72.0, 42.0)]):
    kos += '    (keepout\n      "rounded corner %d"\n      (polygon signal 0 %.2f %.2f %.2f %.2f %.2f %.2f %.2f %.2f)\n    )\n' % (i + 1, x0 * M, y0 * M, (x0 + 2) * M, y0 * M, (x0 + 2) * M, (y0 + 2) * M, x0 * M, (y0 + 2) * M)
k = s.find("    (keepout\n")
s = s[:k] + kos + s[k:]
dsn = os.path.join(run, "route.dsn"); open(dsn, "w", encoding="utf-8").write(s)
if "--dsn-only" in sys.argv: print("DSN written", dsn); raise SystemExit(0)
r0 = subprocess.run([sys.executable, os.path.join(ROOT, "benchmarks", "usb_route.py"), os.path.join(ROOT, "benchmarks", "snap_r2b_s3a.json"), "--write-dsn", dsn, dsn],
                    cwd=os.path.join(ROOT, "benchmarks"), capture_output=True, text=True, encoding="utf-8", errors="replace")
open(os.path.join(run, "usb_route.log"), "w", encoding="utf-8").write(r0.stdout + r0.stderr)
if "ALL OK" not in r0.stdout or "protected wiring" not in r0.stdout: raise SystemExit("USB protected wiring failed: " + r0.stdout[-600:] + r0.stderr[-600:])
print("USB + U1-GND protected wiring injected")
shutil.copy(os.path.join(DESK, "freerouting.json"), run)
ses = os.path.join(run, "route.ses")
if os.path.exists(ses): os.remove(ses)
with open(os.path.join(run, "fr.log"), "w", encoding="utf-8") as lf:
    subprocess.run(["java", "-jar", JAR, "-de", dsn, "-do", ses, "--router.max_passes=60", "--router.job_timeout=" + jt, "--gui.enabled=false"],
                   cwd=run, stdout=lf, stderr=subprocess.STDOUT, timeout=600)
lines = [l for l in open(os.path.join(run, "fr.log"), encoding="utf-8", errors="replace") if "unrouted)" in l]
print("FR last:", lines[-1].strip()[-90:] if lines else "none", "| SES", os.path.exists(ses))
if not os.path.exists(ses): raise SystemExit("no SES")
r = subprocess.run([sys.executable, os.path.join(ROOT, "benchmarks", "ses_import_verify.py"), ses], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
print([l for l in r.stdout.splitlines() if "SES import" in l or l.startswith("tracks")])
