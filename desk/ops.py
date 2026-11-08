"""Single-writer lock + operation journal for live EasyEDA writes (recovery after crashes/timeouts).
Features:
- Atomic cross-process lock via OS-level O_CREAT | O_EXCL
- Real process liveness checks (cross-platform Windows & POSIX)
- Operation classification (READ_ONLY, IDEMPOTENT_MUTATION, NON_IDEMPOTENT_MUTATION, VALIDATION)
- Durable append-only journal (ops.jsonl)

lock    projects/<P>/state/write.lock   one writer at a time; stale after LOCK_TTL seconds or dead PID
journal projects/<P>/state/ops.jsonl    {"op","target","phase":"begin"|"end"|"fail","ts","id","classification",...}
"""
import json
import os
import time
import uuid
import contextlib
from typing import Dict, List, Optional, Any

LOCK_TTL = 1800

# Operation Classifications
OP_READ_ONLY = "READ_ONLY"
OP_IDEMPOTENT_MUTATION = "IDEMPOTENT_MUTATION"
OP_NON_IDEMPOTENT_MUTATION = "NON_IDEMPOTENT_MUTATION"
OP_VALIDATION = "VALIDATION"


def is_process_alive(pid: int) -> bool:
    """Verifies whether a PID is actually active on the host OS."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        except Exception:
            return True  # Conservative fallback if ctypes check fails
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _state(project: str) -> str:
    d = os.path.join(project, "state")
    os.makedirs(d, exist_ok=True)
    return d


def journal(project: str) -> List[Dict[str, Any]]:
    f = os.path.join(_state(project), "ops.jsonl")
    if not os.path.exists(f):
        return []
    with open(f, encoding="utf-8") as h:
        return [json.loads(l) for l in h if l.strip()]


def _log(project: str, rec: Dict[str, Any]):
    with open(os.path.join(_state(project), "ops.jsonl"), "a", encoding="utf-8") as h:
        h.write(json.dumps(rec) + "\n")


def pending(project: str) -> List[Dict[str, Any]]:
    open_ = {}
    for r in journal(project):
        if r["phase"] == "begin":
            open_[r["id"]] = r
        elif r["phase"] == "fail" and r.get("dirty"):
            open_.setdefault(r["id"], r)["dirty"] = True
        else:
            open_.pop(r["id"], None)  # end / clean fail / resolved
    return list(open_.values())


def resolve_pending(project: str, op_id: str, how: str):
    _log(project, {"id": op_id, "phase": "resolved", "ts": time.time(), "how": how})


def acquire_atomic_lock(lock_path: str, rec: Dict[str, Any], force_unlock: bool = False, ttl: int = LOCK_TTL):
    """Acquires lock file using atomic OS-level mutual exclusion."""
    for attempt in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with open(fd, "w", encoding="utf-8") as h:
                json.dump(rec, h)
            return
        except FileExistsError:
            # Check existing lock holder
            try:
                with open(lock_path, "r", encoding="utf-8") as h:
                    info = json.load(h)
            except Exception:
                info = {}

            holder_pid = info.get("pid", 0)
            elapsed = time.time() - info.get("ts", 0)
            pid_alive = is_process_alive(holder_pid) if holder_pid else False

            is_stale = (elapsed >= ttl) or (not pid_alive)

            if force_unlock or is_stale:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(lock_path)
                continue
            else:
                raise SystemExit(
                    f"STOP: another writer holds the lock ({info.get('op')} {info.get('target')}, pid {holder_pid}). "
                    f"Wait, or --force-unlock if that process is dead."
                )
    raise SystemExit(f"STOP: Could not acquire lock {lock_path} after reclaiming stale lock.")


@contextlib.contextmanager
def write_op(project: str, op: str, target: str, force_unlock: bool = False,
             classification: str = OP_NON_IDEMPOTENT_MUTATION):
    """with write_op(P, "build", "02_PWR_3V3") as rec: ... -> atomic lock + begin/end journal."""
    lock = os.path.join(_state(project), "write.lock")

    stuck = [p for p in pending(project) if p["target"] == target]
    if stuck:
        raise SystemExit(
            f"STOP: unfinished {stuck[-1]['op']} on {target} (op {stuck[-1]['id']}). "
            f"Run: python tools/desk.py recover {project}"
        )

    rec = {
        "id": uuid.uuid4().hex[:8],
        "op": op,
        "target": target,
        "classification": classification,
        "phase": "begin",
        "ts": time.time(),
        "pid": os.getpid()
    }

    acquire_atomic_lock(lock, rec, force_unlock=force_unlock)
    _log(project, rec)

    try:
        yield rec
        _log(project, {
            "id": rec["id"],
            "op": op,
            "target": target,
            "classification": classification,
            "phase": "end",
            "ts": time.time()
        })
    except BaseException as e:
        _log(project, {
            "id": rec["id"],
            "op": op,
            "target": target,
            "classification": classification,
            "phase": "fail",
            "ts": time.time(),
            "error": str(e)[:300],
            "dirty": bool(rec.get("dirty"))
        })
        raise
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(lock)
