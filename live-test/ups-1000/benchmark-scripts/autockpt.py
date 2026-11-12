"""Background 10-minute checkpoint writer: records stage/elapsed/last-event/resources at the moment it fires."""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
EXEC = os.path.join(HERE, "..", "builder-records", "execution.jsonl")
T0 = 85446171000000
k = 1
while True:
    target = T0 + k * 600 * 10**9
    while time.monotonic_ns() < target:
        time.sleep(5)
    last = ""
    try:
        lines = [json.loads(l) for l in open(EXEC, encoding="utf-8") if l.strip()]
        ev = [l for l in lines if l["status"] != "CHECKPOINT"]
        last = f'{ev[-1]["status"]}: {ev[-1]["message"]}' if ev else ""
    except Exception as e:
        last = f"read error {e}"
    subprocess.run([sys.executable, os.path.join(HERE, "bench.py"), "checkpoint",
                    f"T+{k*10:02d} auto-checkpoint; last builder event -> {last[:300]}",
                    "see latest builder event", "see builder-records/drc", "see failure_register.json"])
    k += 1
    if k > 19:
        break
