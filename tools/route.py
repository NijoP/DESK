"""Priority-Based Autonomous PCB Routing & Recovery Engine.
Usage: python tools/route.py projects/<product> [--passes 30] [--recovery] [--dry]

Order of Execution:
1. Priority Scheduling: Stages 1 (GND) through 6 (Remaining)
2. Recovery Rip-up: If --recovery, selectively deletes conflicting primitives from state/recovery_plan.json
3. DSN Export & Tuning: Automatically tunes boundary, fine-pitch clearances, and class widths
4. Autorouting: Executes Freerouting with tailored constraints
5. SES Import: Imports routed copper tracks and vias back into EasyEDA Pro
6. Routing Audit: Logs attempt metrics to state/route/routing_attempt.json and LEDGER.jsonl
"""
import sys, os, json, subprocess, shutil, base64, time
from _common import ex, guard, load_project, check, S
from desk.bridge import fetch_file
from desk import ops
from desk import ledger as LG
from desk.routability import RoutabilityEvaluator
from desk.router import RoutingPlanGenerator, DSNTuningEngine

MIL = 39.37007874
args = sys.argv[1:]
if not args or args[0].startswith("-"):
    raise SystemExit(__doc__)

proj = args[0]
passes = args[args.index("--passes") + 1] if "--passes" in args else "30"
dry = "--dry" in args
recovery = "--recovery" in args

P = load_project(proj)
dump_path = os.path.join(proj, "state", "pcb_dump.json")
dump = json.load(open(dump_path, encoding="utf-8")) if os.path.exists(dump_path) else {}
plan_path = os.path.join(proj, "placement.json")
plan = json.load(open(plan_path, encoding="utf-8")) if os.path.exists(plan_path) else {"board_mm": [50.0, 50.0]}

# Build net graph and ordered routing plan
net_graph = RoutabilityEvaluator.build_connectivity_graph(dump)
routing_plan = RoutingPlanGenerator.generate_plan(
    net_graph, dump, tuple(plan.get("board_mm", [50.0, 50.0])), rules=plan.get("rules")
)

print(f"Routing Strategy: Stackup {routing_plan.board_stackup}")
for s_num in range(1, 7):
    s_nets = routing_plan.stage_nets.get(s_num, [])
    if s_nets:
        print(f"  Stage {s_num}: {len(s_nets)} nets ({', '.join(s_nets[:5])}{'...' if len(s_nets) > 5 else ''})")

G = guard(P["pcb_uuid"])
wd = os.path.join(proj, "state", "route")
os.makedirs(wd, exist_ok=True)

# Selective rip-up if in recovery mode
if recovery:
    rec_plan_path = os.path.join(proj, "state", "recovery_plan.json")
    if os.path.exists(rec_plan_path):
        rec_data = json.load(open(rec_plan_path, encoding="utf-8"))
        rip_ids = rec_data.get("conflicting_tracks_to_ripup", [])
        if rip_ids:
            print(f"Recovery: Selectively ripping up {len(rip_ids)} conflicting tracks...")
            check(ex(G + f'await eda.pcb_PrimitiveTrack.delete({json.dumps(rip_ids)}); return true;',
                     timeout=60, window_id=P.get("window_id")))

# Export DSN
dsn = fetch_file(G + 'const f=await eda.pcb_ManufactureData.getDsnFile("desk_route");', wd, window_id=P.get("window_id"))
print("DSN raw:", dsn, os.path.getsize(dsn), "B")

# Tune DSN with true boundary and tuned widths/clearances
with open(dsn, "r", encoding="utf-8", errors="ignore") as f:
    dsn_content = f.read()

board_w_mil = plan.get("board_mm", [50.0, 50.0])[0] * MIL
board_h_mil = plan.get("board_mm", [50.0, 50.0])[1] * MIL
power_nets = set(routing_plan.stage_nets.get(1, []) + routing_plan.stage_nets.get(5, []))
tuned_dsn = DSNTuningEngine.tune_dsn(dsn_content, (board_w_mil, board_h_mil), power_nets=power_nets)

tuned_dsn_path = os.path.join(wd, "desk_route_tuned.dsn")
with open(tuned_dsn_path, "w", encoding="utf-8") as f:
    f.write(tuned_dsn)
print("DSN tuned ->", tuned_dsn_path)

if dry:
    print("Dry run completed. DSN prepared."); sys.exit(0)

# Check Freerouting jar
jar = os.environ.get("FREEROUTING_JAR") or os.path.join(S.ROOT, "library", "tools", "freerouting.jar")
if not os.path.exists(jar):
    raise SystemExit(f"STOP: Freerouting jar not found at {jar}. Set FREEROUTING_JAR.")
if not shutil.which("java"):
    raise SystemExit("STOP: java not found on PATH.")

ses = os.path.join(wd, "desk_route.ses")
cmd = ["java", "-jar", jar, "-de", tuned_dsn_path, "-do", ses, "-mp", str(passes), "--gui.enabled=false"]
t0 = time.time()
p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
with open(os.path.join(wd, "freerouting.log"), "w", encoding="utf-8") as f:
    f.write(p.stdout + p.stderr)

if p.returncode != 0 or not os.path.exists(ses):
    raise SystemExit(f"STOP: Freerouting failed (rc {p.returncode}); see {wd}/freerouting.log")

dur = time.time() - t0
print(f"Freerouting completed in {dur:.1f}s -> {ses}")

# Import SES back into EasyEDA Pro
b64 = base64.b64encode(open(ses, "rb").read()).decode()
with ops.write_op(proj, "route_import", "PCB") as rec:
    rec["dirty"] = True
    r = check(ex(G + 'const b=atob("%s"); const u=new Uint8Array(b.length); for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);'
                     'const ok=await eda.pcb_Document.importAutoRouteSesFile(new File([u],"desk_route.ses")); return ok;' % b64,
                 timeout=600, window_id=P.get("window_id")))

print("SES import:", r)
if r is not True: raise SystemExit("STOP: EasyEDA rejected the SES import")

# Log attempt
attempt_record = {
    "timestamp": time.time(),
    "passes": passes,
    "duration_sec": round(dur, 1),
    "populated_nets": len(net_graph.nets),
    "import_success": (r is True)
}
with open(os.path.join(wd, "routing_attempt.json"), "w", encoding="utf-8") as f:
    json.dump(attempt_record, f, indent=2)

LG.add(proj, "routing_attempt",
       f"Autonomous routing executed with {passes} passes in {dur:.1f}s. "
       f"Populated nets: {len(net_graph.nets)} across {len(routing_plan.board_stackup)} layers.",
       source="tools/route.py")

print("NEXT: python tools/drc.py", proj, "--converge")
