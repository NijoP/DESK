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
from desk.errors import WriteLockHeld, PendingOperationError, ApprovalRequired  # noqa: E402
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
    if os.path.isdir("/proc"):
        try:
            return os.stat(f"/proc/{pid}").st_ctime
        except Exception:
            return None
    # macOS / BSD have no procfs: `ps -o etimes=` reports elapsed seconds since the process started.
    try:
        import subprocess
        out = subprocess.run(["ps", "-o", "etimes=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=2).stdout.strip()
        return time.time() - float(out) if out else None
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


# ---- human approval and mutation policy (T-17) ---------------------------------------------------------
def record_approval(project: str, op: str, target: str, granted_by: str, how: str,
                    token: Optional[str] = None, reason: str = "") -> str:
    """Durable approval record in state/ops.jsonl (phase "approval"); returns its id.

    Pass the id to `write_op(..., approval=<id>)` so the mutation's begin record points at who approved
    what, when and how. `granted_by` is a role or name ("operator", "CAPTAIN"), `how` the channel
    ("cli tools/build.py", "desk.py agent --allow-mutation", "rework approve RW-APR-..")."""
    rec = {"id": uuid.uuid4().hex[:8], "phase": "approval", "op": op, "target": target, "granted_by": granted_by,
           "how": how, "token": token, "reason": reason, "ts": time.time(), "pid": os.getpid()}
    _log(project, rec)
    return rec["id"]


def cli_approval(project: str, op: str, target: str, argv: Optional[List[str]] = None) -> str:
    """The operator ran a mutating tool by hand: that invocation is the approval. Records it and returns the id."""
    import sys as _sys
    args = list(argv if argv is not None else _sys.argv)
    how = "cli " + " ".join(os.path.basename(a) if i == 0 else a for i, a in enumerate(args))[:200]
    return record_approval(project, op, target, granted_by="operator", how=how)


def approvals(project: str) -> List[Dict[str, Any]]:
    return [r for r in journal(project) if r.get("phase") == "approval"]


class MutationPolicy:
    """Decides whether a live mutation may start and what the journal records about its approval.

    DESK_MUTATION_POLICY (desk/config.py):
      record  (default) every mutation records whether an approval accompanied it; nothing is refused
      require a NON_IDEMPOTENT mutation without an approval raises ApprovalRequired before the lock is taken
    The operation registry's `side_effect` flag is recorded for known operation ids so the journal shows when a
    tool journals an operation the registry does not consider side-effecting (or the reverse)."""
    RECORD, REQUIRE = "record", "require"

    @staticmethod
    def mode() -> str:
        from desk import config as deskcfg
        m = (deskcfg.get("DESK_MUTATION_POLICY") or MutationPolicy.RECORD).lower()
        return m if m in (MutationPolicy.RECORD, MutationPolicy.REQUIRE) else MutationPolicy.RECORD

    @staticmethod
    def registry_side_effect(op: str) -> Optional[bool]:
        try:
            from desk.operation_registry import get_operation_registry
            d = get_operation_registry().get(op)
            return None if d is None else bool(d.side_effect)
        except Exception:
            return None

    @classmethod
    def check(cls, project: str, op: str, target: str, classification: str, approval: Optional[str]) -> Dict[str, Any]:
        mode = cls.mode()
        info = {"policy": mode, "approval": approval or None, "registry_side_effect": cls.registry_side_effect(op)}
        if mode == cls.REQUIRE and classification == OP_NON_IDEMPOTENT_MUTATION and not approval:
            raise ApprovalRequired(
                f"STOP: {op} on {target} is a non-idempotent live mutation and DESK_MUTATION_POLICY=require, "
                f"but no approval was recorded. Record one (ops.record_approval / cli_approval) or run the tool by hand.",
                op=op, target=target)
        return info


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


LOCK_WRITE_GRACE_SEC = 2.0  # a lock file younger than this with no readable record is being written, not stale


def acquire_atomic_lock(lock_path: str, rec: Dict[str, Any], force_unlock: bool = False, ttl: int = LOCK_TTL):
    """Acquires lock file using atomic OS-level mutual exclusion with race-free reclamation.

    The lock is created with O_EXCL and its record written immediately after. A
    second acquirer that reads the file in that window sees an empty or partial
    record. Such a record must not be treated as a dead holder: if the file is
    younger than LOCK_WRITE_GRACE_SEC we wait and re-read instead of reclaiming.
    """
    for attempt in range(40):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with open(fd, "w", encoding="utf-8") as h:
                json.dump(rec, h)
                h.flush()
            return
        except FileExistsError:
            info: Dict[str, Any] = {}
            readable = False
            try:
                with open(lock_path, "r", encoding="utf-8") as h:
                    info = json.load(h)
                readable = isinstance(info, dict) and "pid" in info
            except Exception:
                readable = False

            if not readable and not force_unlock:
                try:
                    age = time.time() - os.path.getmtime(lock_path)
                except OSError:
                    continue  # vanished between our open and stat: retry the O_EXCL create
                if age < LOCK_WRITE_GRACE_SEC:
                    time.sleep(0.05)
                    continue
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
                raise WriteLockHeld(
                    f"STOP: another writer holds the lock ({info.get('op')} {info.get('target')}, pid {holder_pid}). "
                    f"Wait, or --force-unlock if that process is dead.", holder_pid=holder_pid, lock_path=lock_path,
                )
    raise WriteLockHeld(f"STOP: Could not acquire lock {lock_path} after reclaiming stale lock.", lock_path=lock_path)


@contextlib.contextmanager
def write_op(
    project: str,
    op: str,
    target: str,
    force_unlock: bool = False,
    classification: str = OP_NON_IDEMPOTENT_MUTATION,
    approval: Optional[str] = None,
):
    """with write_op(P, "build", "02_PWR_3V3", approval=aid) as rec: ... -> policy check + atomic lock + begin/end journal.

    `approval` is the id returned by record_approval()/cli_approval() (or a rework RW-APR token). It is written
    into the begin record together with the policy in force and the registry's side_effect flag for `op`."""
    lock = os.path.join(_state(project), "write.lock")
    policy = MutationPolicy.check(project, op, target, classification, approval)

    stuck = [p for p in pending(project) if p["target"] == target]
    if stuck:
        raise PendingOperationError(
            f"STOP: unfinished {stuck[-1]['op']} on {target} (op {stuck[-1]['id']}). "
            f"Run: python tools/desk.py recover {project}", op_id=stuck[-1]["id"], target=target,
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
        **policy,
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
        elif getattr(e, "possibly_mutated", False):
            # A bridge timeout during a mutation: EasyEDA may have applied part of it.
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
