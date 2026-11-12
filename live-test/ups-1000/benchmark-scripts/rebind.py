"""Re-bind projects/UPS_1000/project.json window_id to the gateway window whose project UUID matches.
Read-only towards EasyEDA. Never falls back to the active window. Logs each rebind to execution.jsonl."""
import json, os, sys, urllib.request, subprocess
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PJ = os.path.join(ROOT, "projects", "UPS_1000", "project.json")
p = json.load(open(PJ, encoding="utf-8"))
def post(wid, code):
    req = urllib.request.Request("http://127.0.0.1:49620/execute", data=json.dumps({"windowId": wid, "code": code}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())
wins = json.loads(urllib.request.urlopen("http://127.0.0.1:49620/eda-windows", timeout=5).read().decode())["windows"]
code = "const p=await eda.dmt_Project.getCurrentProjectInfo(); return {name:p&&p.friendlyName,uuid:p&&p.uuid};"
match = []
for w in wins:
    try:
        r = post(w["windowId"], code)
        if r.get("success") and r["result"]["uuid"] == p["project_uuid"]:
            match.append(w["windowId"])
    except Exception:
        pass
if len(match) != 1:
    sys.exit(f"REBIND FAILED: {len(match)} windows host project {p['project_uuid']} -> no mutation allowed")
if match[0] != p.get("window_id"):
    old = p.get("window_id"); p["window_id"] = match[0]
    json.dump(p, open(PJ, "w", encoding="utf-8"), indent=1)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "bench.py"), "event", "0", "REBIND",
                    f"window_id {old} -> {match[0]} (matched project_uuid {p['project_uuid']} 'ups claude test')"], stdout=subprocess.DEVNULL)
    print("REBOUND", old, "->", match[0])
else:
    print("BOUND", match[0])
