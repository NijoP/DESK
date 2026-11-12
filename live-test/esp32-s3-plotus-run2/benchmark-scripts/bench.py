"""Plotus benchmark timer / logger (monotonic, high resolution).

Usage:
  python bench.py start                      # start 225-min engineering clock
  python bench.py stage-start <N>            # start stage N (1..5)
  python bench.py stage-end <N> <PASS|FAIL|PARTIAL|TIMEOUT> "<note>"
  python bench.py event <stage> <status> "<message>"
  python bench.py status                     # elapsed / remaining
time.monotonic_ns() on Windows is system-wide (QueryUnbiasedInterruptTime based),
so readings are comparable across processes.
"""
import json, sys, time, datetime, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMING = os.path.join(ROOT, "benchmarks", "timing.json")
STAGES_F = os.path.join(ROOT, "benchmarks", "stage_metrics.json")
PROGRESS = os.path.join(ROOT, "logs", "progress.json")
EXEC = os.path.join(ROOT, "logs", "execution.jsonl")
BUDGET = {1: 45, 2: 45, 3: 90, 4: 30, 5: 15}
NAMES = {1: "Schematic design and validation", 2: "Component placement",
         3: "Routing and connectivity", 4: "Copper pouring", 5: "Manufacturing checks"}
TOTAL_MIN = 225


def now():
    return time.monotonic_ns(), datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return d


def save(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, p)


def log(stage, status, msg):
    m, w = now()
    t = load(TIMING, {})
    el = (m - t["start_mono_ns"]) / 6e10 if "start_mono_ns" in t else None
    rec = {"wall": w, "mono_ns": m, "elapsed_min": round(el, 3) if el is not None else None,
           "stage": stage, "status": status, "message": msg}
    with open(EXEC, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def progress():
    t = load(TIMING, {})
    s = load(STAGES_F, {"stages": {}})
    m, w = now()
    el = (m - t["start_mono_ns"]) / 6e10 if "start_mono_ns" in t else 0
    p = {"updated": w, "engineering_elapsed_min": round(el, 2),
         "engineering_remaining_min": round(TOTAL_MIN - el, 2), "stages": {}}
    for k, st in s["stages"].items():
        e = dict(st)
        if st.get("state") == "running":
            se = (m - st["start_mono_ns"]) / 6e10
            e["elapsed_min"] = round(se, 2)
            e["remaining_min"] = round(BUDGET[int(k)] - se, 2)
        p["stages"][k] = e
    save(PROGRESS, p)
    return p


def main():
    a = sys.argv[1:]
    cmd = a[0]
    m, w = now()
    if cmd == "start":
        t = load(TIMING, {})
        if "start_mono_ns" in t:
            sys.exit("already started")
        t = {"start_wall": w, "start_mono_ns": m, "total_budget_min": TOTAL_MIN,
             "deadline_wall": (datetime.datetime.now().astimezone() + datetime.timedelta(minutes=TOTAL_MIN)).isoformat(timespec="seconds"),
             "clock": "time.monotonic_ns (system-wide)", "stage_budgets_min": BUDGET}
        save(TIMING, t)
        save(STAGES_F, {"stages": {}})
        print(log(0, "START", "engineering timer started"))
    elif cmd == "stage-start":
        n = int(a[1])
        s = load(STAGES_F, {"stages": {}})
        s["stages"][str(n)] = {"name": NAMES[n], "budget_min": BUDGET[n], "state": "running",
                               "start_wall": w, "start_mono_ns": m,
                               "deadline_wall": (datetime.datetime.now().astimezone() + datetime.timedelta(minutes=BUDGET[n])).isoformat(timespec="seconds")}
        save(STAGES_F, s)
        print(log(n, "STAGE_START", NAMES[n]))
    elif cmd == "stage-end":
        n, res, note = int(a[1]), a[2], a[3] if len(a) > 3 else ""
        s = load(STAGES_F, {"stages": {}})
        st = s["stages"][str(n)]
        dur = (m - st["start_mono_ns"]) / 6e10
        st.update({"state": "ended", "end_wall": w, "end_mono_ns": m, "duration_min": round(dur, 3),
                   "within_budget": dur <= BUDGET[n], "result": res, "note": note})
        save(STAGES_F, s)
        t = load(TIMING, {})
        t.setdefault("stages", {})[str(n)] = {"duration_min": round(dur, 3), "result": res}
        save(TIMING, t)
        print(log(n, "STAGE_END_" + res, f"{note} (duration {dur:.2f} min / budget {BUDGET[n]})"))
    elif cmd == "end":
        t = load(TIMING, {})
        el = (m - t["start_mono_ns"]) / 6e10
        t.update({"end_wall": w, "end_mono_ns": m, "total_elapsed_min": round(el, 3)})
        save(TIMING, t)
        print(log(0, "END", f"engineering benchmark ended at {el:.2f} min"))
    elif cmd == "event":
        print(log(int(a[1]), a[2], a[3]))
    elif cmd == "status":
        pass
    p = progress()
    if cmd == "status":
        print(json.dumps(p, indent=1))


if __name__ == "__main__":
    main()
