"""Single-writer lock + operation journal for live EasyEDA writes (recovery after crashes/timeouts).

lock    projects/<P>/state/write.lock   one writer at a time; stale after LOCK_TTL seconds (or --force-unlock)
journal projects/<P>/state/ops.jsonl    {"op","target","phase":"begin"|"end"|"fail","ts","id",...}
An op with 'begin' but no 'end'/'fail' is PENDING: the sheet may hold a half-drawn block.
Writers refuse to start while a pending op exists for the same target; `tools/desk.py recover` resolves it."""
import json, os, time, uuid, contextlib

LOCK_TTL = 1800


def _state(project):
    d = os.path.join(project, "state"); os.makedirs(d, exist_ok=True); return d


def journal(project):
    f = os.path.join(_state(project), "ops.jsonl")
    if not os.path.exists(f): return []
    with open(f, encoding="utf-8") as h: return [json.loads(l) for l in h if l.strip()]


def _log(project, rec):
    with open(os.path.join(_state(project), "ops.jsonl"), "a", encoding="utf-8") as h: h.write(json.dumps(rec) + "\n")


def pending(project):
    open_ = {}
    for r in journal(project):
        if r["phase"] == "begin": open_[r["id"]] = r
        elif r["phase"] == "fail" and r.get("dirty"): open_.setdefault(r["id"], r)["dirty"] = True
        else: open_.pop(r["id"], None)          # end / clean fail / resolved
    return list(open_.values())


def resolve_pending(project, op_id, how):
    _log(project, {"id": op_id, "phase": "resolved", "ts": time.time(), "how": how})


@contextlib.contextmanager
def write_op(project, op, target, force_unlock=False):
    """with write_op(P, "build", "02_PWR_3V3") as rec: ...  -> lock + begin/end journal."""
    lock = os.path.join(_state(project), "write.lock")
    if os.path.exists(lock):
        with open(lock) as h: info = json.load(h)
        if not force_unlock and time.time() - info.get("ts", 0) < LOCK_TTL:
            raise SystemExit(f"STOP: another writer holds the lock ({info.get('op')} {info.get('target')}, pid {info.get('pid')}). "
                             f"Wait, or --force-unlock if that process is dead.")
    stuck = [p for p in pending(project) if p["target"] == target]
    if stuck:
        raise SystemExit(f"STOP: unfinished {stuck[-1]['op']} on {target} (op {stuck[-1]['id']}). "
                         f"Run: python tools/desk.py recover {project}")
    rec = {"id": uuid.uuid4().hex[:8], "op": op, "target": target, "phase": "begin", "ts": time.time(), "pid": os.getpid()}
    with open(lock, "w") as h: json.dump(rec, h)
    _log(project, rec)
    try:
        yield rec
        _log(project, {"id": rec["id"], "op": op, "target": target, "phase": "end", "ts": time.time()})
    except BaseException as e:
        # SystemExit from a guarded STOP before anything was written is a clean failure
        _log(project, {"id": rec["id"], "op": op, "target": target, "phase": "fail", "ts": time.time(), "error": str(e)[:300],
                       "dirty": bool(rec.get("dirty"))})
        raise
    finally:
        with contextlib.suppress(FileNotFoundError): os.remove(lock)
