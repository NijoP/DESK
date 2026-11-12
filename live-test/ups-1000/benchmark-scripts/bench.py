"""UPS-1000 benchmark timer / logger (monotonic). Adapted from esp32-s3-plotus-run2 bench.py.

Usage:
  python bench.py start <start_mono_ns> <start_wall_iso>   # clock reference recorded at task start
  python bench.py stage-start <N>          (1..6)
  python bench.py stage-end <N> <PASS|FAIL|PARTIAL|TIMEOUT|BLOCKED> "<note>"
  python bench.py event <stage> <status> "<message>"
  python bench.py fail <stage> <id> "<description>" "<recovery>" <recovered:true|false>
  python bench.py checkpoint "<completed>" "<nets>" "<drc_erc>" "<blockers>" [recoveries]
  python bench.py end
  python bench.py status
"""
import json, sys, time, datetime, os, csv

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "builder-records")
TIMING = os.path.join(ROOT, "timing.json")
STAGES_F = os.path.join(ROOT, "stage_metrics.json")
PROGRESS = os.path.join(ROOT, "progress.json")
EXEC = os.path.join(ROOT, "execution.jsonl")
FAIL = os.path.join(ROOT, "failure_register.json")
RES = os.path.join(ROOT, "resource_metrics.csv")
BUDGET = {1: 35, 2: 35, 3: 65, 4: 20, 5: 10, 6: 15}
NAMES = {1: "Requirements, domain intelligence, schematic", 2: "Component selection, BOM and placement",
         3: "Power-aware routing and connectivity", 4: "Copper, power, thermal and DRC verification",
         5: "Manufacturing export and preflight", 6: "Final independent Sonnet review"}
TOTAL_MIN = 180


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


def elapsed(m):
    t = load(TIMING, {})
    return (m - t["start_mono_ns"]) / 6e10 if "start_mono_ns" in t else None


def log(stage, status, msg, extra=None):
    m, w = now()
    el = elapsed(m)
    rec = {"wall": w, "mono_ns": m, "elapsed_min": round(el, 3) if el is not None else None,
           "stage": stage, "status": status, "message": msg}
    if extra:
        rec.update(extra)
    with open(EXEC, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def resources(m, w):
    row = {"wall": w, "elapsed_min": round(elapsed(m) or 0, 2)}
    try:
        import psutil
        row.update(cpu_pct=psutil.cpu_percent(interval=0.2), mem_used_pct=psutil.virtual_memory().percent)
    except Exception:
        row.update(cpu_pct="n/a(psutil missing)", mem_used_pct="n/a")
    new = not os.path.exists(RES)
    with open(RES, "a", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(row))
        if new:
            wr.writeheader()
        wr.writerow(row)
    return row


def progress(extra=None):
    s = load(STAGES_F, {"stages": {}})
    m, w = now()
    el = elapsed(m) or 0
    p = load(PROGRESS, {"checkpoints": []})
    p.update({"updated": w, "elapsed_min": round(el, 2), "remaining_min": round(TOTAL_MIN - el, 2), "stages": {}})
    cur = None
    for k, st in s["stages"].items():
        e = {kk: vv for kk, vv in st.items() if not kk.endswith("_ns")}
        if st.get("state") == "running":
            se = (m - st["start_mono_ns"]) / 6e10
            e["elapsed_min"] = round(se, 2)
            e["remaining_min"] = round(BUDGET[int(k)] - se, 2)
            cur = int(k)
        p["stages"][k] = e
    p["current_stage"] = cur
    if extra:
        extra.update({"wall": w, "elapsed_min": round(el, 2), "remaining_min": round(TOTAL_MIN - el, 2),
                      "current_stage": cur, "resources": resources(m, w)})
        p["checkpoints"].append(extra)
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
        sm, sw = int(a[1]), a[2]
        t = {"start_wall": sw, "start_mono_ns": sm, "total_budget_min": TOTAL_MIN,
             "deadline_wall": (datetime.datetime.fromisoformat(sw) + datetime.timedelta(minutes=TOTAL_MIN)).isoformat(timespec="seconds"),
             "clock": "time.monotonic_ns (system-wide, Windows QueryUnbiasedInterruptTime)",
             "note": "start reference captured by the builder's first tool call at task receipt",
             "stage_budgets_min": BUDGET}
        save(TIMING, t)
        save(STAGES_F, {"stages": {}})
        save(FAIL, {"failures": []})
        print(log(0, "START", "benchmark clock reference recorded", {"start_mono_ns": sm}))
    elif cmd == "stage-start":
        n = int(a[1])
        s = load(STAGES_F, {"stages": {}})
        s["stages"][str(n)] = {"name": NAMES[n], "budget_min": BUDGET[n], "state": "running",
                               "start_wall": w, "start_mono_ns": m, "start_elapsed_min": round(elapsed(m), 3),
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
        t.setdefault("stages", {})[str(n)] = {"duration_min": round(dur, 3), "budget_min": BUDGET[n], "result": res}
        save(TIMING, t)
        print(log(n, "STAGE_END_" + res, f"{note} (duration {dur:.2f} min / budget {BUDGET[n]})"))
    elif cmd == "end":
        t = load(TIMING, {})
        el = elapsed(m)
        t.update({"end_wall": w, "end_mono_ns": m, "total_elapsed_min": round(el, 3)})
        save(TIMING, t)
        print(log(0, "END", f"benchmark ended at {el:.2f} min"))
    elif cmd == "event":
        print(log(int(a[1]), a[2], a[3]))
    elif cmd == "fail":
        f = load(FAIL, {"failures": []})
        rec = {"id": a[2], "stage": int(a[1]), "wall": w, "elapsed_min": round(elapsed(m), 3),
               "description": a[3], "recovery": a[4], "recovered": a[5].lower() == "true"}
        f["failures"].append(rec)
        save(FAIL, f)
        print(log(int(a[1]), "FAILURE", a[3], {"failure_id": a[2]}))
    elif cmd == "checkpoint":
        extra = {"completed": a[1], "nets": a[2], "drc_erc": a[3], "blockers": a[4],
                 "recoveries": a[5] if len(a) > 5 else "0"}
        progress(extra)
        print(log(-1, "CHECKPOINT", a[1]))
        return
    p = progress()
    if cmd == "status":
        print(json.dumps({k: p[k] for k in ("elapsed_min", "remaining_min", "current_stage")}, indent=1))
        print(json.dumps(p["stages"], indent=1))


if __name__ == "__main__":
    main()
