"""Single-writer lock + operation journal for live EasyEDA writes (recovery after crashes/timeouts).
Features:
- Atomic cross-process lock via OS-level O_CREAT | O_EXCL
- Real process liveness checks (cross-platform Windows & POSIX)
- Process start-time detection to eliminate PID recycling hazards
- Verified-owner lock release semantics (prevents deleting foreign locks)
- Atomic stale lock reclamation (race-free TOCTOU handling via atomic replacement)
- Unknown mutation outcome handling: failsafe dirty flagging for non-idempotent operations
- Operation classification (READ_ONLY, IDEMPOTENT_MUTATION, NON_IDEMPOTENT_MUTATION, VALIDATION)
- Durable append-only journal (ops.jsonl)

lock    projects/<P>/state/write.lock   one writer at a time; stale after LOCK_TTL seconds or dead PID
journal projects/<P>/state/ops.jsonl    {"op","target","phase":"begin"|"end"|"fail","ts","id","classification",...}
"""
import contextlib
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

LOCK_TTL = 1800

# Operation Classifications
OP_READ_ONLY = "READ_ONLY"
OP_IDEMPOTENT_MUTATION = "IDEMPOTENT_MUTATION"
OP_NON_IDEMPOTENT_MUTATION = "NON_IDEMPOTENT_MUTATION"
OP_VALIDATION = "VALIDATION"


def get_process_start_time(pid: int) -> Optional[float]:
    """Retrieves process creation timestamp to detect PID reuse."""
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return None
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]
            creation = FILETIME()
            exit_t = FILETIME()
            kernel_t = FILETIME()
            user_t = FILETIME()
            ok = ctypes.windll.kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_t), ctypes.byref(kernel_t), ctypes.byref(user_t)
            )
            ctypes.windll.kernel32.CloseHandle(handle)
            if ok:
                ft = (creation.dwHighDateTime << 32) + creation.dwLowDateTime
                return (ft - 116444736000000000) / 10000000.0
            return None
        except Exception:
            return None
    else:
        try:
            st = os.stat(f"/proc/{pid}")
            return st.st_ctime
        except Exception:
            return None


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


def release_atomic_lock(lock_path: str, lock_id: str, pid: int) -> bool:
    """Releases the lock file ONLY if the current process is the verified owner."""
    try:
        if not os.path.exists(lock_path):
            return True
        with open(lock_path, "r", encoding="utf-8") as h:
            info = json.load(h)
        if info.get("id") == lock_id and info.get("pid") == pid:
            os.remove(lock_path)
            return True
        return False
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def acquire_atomic_lock(lock_path: str, rec: Dict[str, Any], force_unlock: bool = False, ttl: int = LOCK_TTL):
    """Acquires lock file using atomic OS-level mutual exclusion with race-free reclamation."""
    for attempt in range(5):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with open(fd, "w", encoding="utf-8") as h:
                json.dump(rec, h)
            return
        except FileExistsError:
            try:
                with open(lock_path, "r", encoding="utf-8") as h:
                    info = json.load(h)
            except Exception:
                info = {}

            holder_pid = info.get("pid", 0)
            holder_start_time = info.get("pid_start_time")
            elapsed = time.time() - info.get("ts", 0)

            pid_alive = is_process_alive(holder_pid) if holder_pid else False
            if pid_alive and holder_start_time is not None:
                actual_start_time = get_process_start_time(holder_pid)
                if actual_start_time and actual_start_time > (info.get("ts", 0) + 1.0):
                    # PID recycling detected: process died and PID was reassigned
                    pid_alive = False

            is_stale = (elapsed >= ttl) or (not pid_alive)

            if force_unlock or is_stale:
                reclaim_tmp = f"{lock_path}.reclaim_{uuid.uuid4().hex[:6]}"
                try:
                    os.replace(lock_path, reclaim_tmp)
                    with contextlib.suppress(FileNotFoundError):
                        os.remove(reclaim_tmp)
                except (FileNotFoundError, OSError):
                    pass
                continue
            else:
                raise SystemExit(
                    f"STOP: another writer holds the lock ({info.get('op')} {info.get('target')}, pid {holder_pid}). "
                    f"Wait, or --force-unlock if that process is dead."
                )
    raise SystemExit(f"STOP: Could not acquire lock {lock_path} after reclaiming stale lock.")


@contextlib.contextmanager
def write_op(
    project: str,
    op: str,
    target: str,
    force_unlock: bool = False,
    classification: str = OP_NON_IDEMPOTENT_MUTATION,
):
    """with write_op(P, "build", "02_PWR_3V3") as rec: ... -> atomic lock + begin/end journal."""
    lock = os.path.join(_state(project), "write.lock")

    stuck = [p for p in pending(project) if p["target"] == target]
    if stuck:
        raise SystemExit(
            f"STOP: unfinished {stuck[-1]['op']} on {target} (op {stuck[-1]['id']}). "
            f"Run: python tools/desk.py recover {project}"
        )

    my_pid = os.getpid()
    rec = {
        "id": uuid.uuid4().hex[:8],
        "op": op,
        "target": target,
        "classification": classification,
        "phase": "begin",
        "ts": time.time(),
        "pid": my_pid,
        "pid_start_time": get_process_start_time(my_pid),
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
            "ts": time.time(),
        })
    except BaseException as e:
        if rec.get("dirty"):
            is_dirty = True
        elif isinstance(e, SystemExit):
            is_dirty = False
        else:
            is_dirty = (classification == OP_NON_IDEMPOTENT_MUTATION)

        _log(project, {
            "id": rec["id"],
            "op": op,
            "target": target,
            "classification": classification,
            "phase": "fail",
            "ts": time.time(),
            "error": str(e)[:300],
            "dirty": is_dirty,
        })
        raise
    finally:
        release_atomic_lock(lock, rec["id"], rec["pid"])
