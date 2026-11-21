"""Shared engineering task record (study report section 7.2): one append-only event stream per task.

    projects/<P>/state/tasks/<task_id>.jsonl      one JSON event per line; the current record is the fold of its events

A folded record carries the six fields fragment 4/5 section 6 asks for, plus evidence, provenance and the attempt
budget: `inputs`, `expected_outputs`, `constraints`, `execution_status`, `verification_status`, `failure`,
`evidence`, `provenance`, `attempts`. DESK code computes `execution_status`, `verification_status` and `attempts` from
events. `validate()` is fail-closed: a record with a missing or malformed field raises `TaskSchemaError`.

Emission points that exist today:
  * `on_op(project, phase, rec)` is called by `desk.ops.write_op` on begin / end / fail (one task per stage + target).
  * `record_verify(project, block_id, ok, ...)` is the hook for `tools/verify.py`; the one-line call from verify.py
    is NOT wired yet (follow-up: verify.py is owned by parallel work).

Zero external dependencies.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

from desk.errors import ProjectError

STAGES = ("requirements", "architecture", "bom", "schematic_block", "placement", "stackup", "routing", "drc", "erc",
          "manufacturing", "release")
EXECUTION = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "BLOCKED", "SUPERSEDED")
VERIFICATION = ("NOT_RUN", "PASS", "FAIL", "STALE")
LAYERS = ("OPERATIONAL", "ENGINEERING")
DEFAULT_MAX_ATTEMPTS = 2          # AGENTS.md section F: retry ceiling of 2 attempts

# write_op op name -> task stage; ops not listed (rebind, bookkeeping) get no task record
OP_STAGE = {"build": "schematic_block", "clear_block": "schematic_block", "wire": "schematic_block",
            "place": "placement", "placement": "placement", "route": "routing", "route_import": "routing",
            "pour": "routing", "drc": "drc", "release": "release"}

_ID_RX = re.compile(r"^T-[A-Za-z0-9_.\-]+$")


class TaskSchemaError(ProjectError):
    """A task record or event that does not satisfy the section 7.2 schema."""


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def task_id(stage: str, scope: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", str(scope)) or "scope"
    return f"T-{stage}-{safe}"


def _desk_commit() -> str:
    head = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".git", "HEAD")
    try:
        with open(head, encoding="utf-8") as f:
            ref = f.read().strip()
        if ref.startswith("ref: "):
            with open(os.path.join(os.path.dirname(head), *ref[5:].split("/")), encoding="utf-8") as f:
                return f.read().strip()[:12]
        return ref[:12]
    except OSError:
        return ""          # a worktree .git file or an installed package: no commit is known, never guessed


# ------------------------------------------------------------------------------------------------ fold
def _blank(tid: str) -> Dict[str, Any]:
    return {"task_id": tid, "parent_task_id": None, "stage": None, "scope": None, "inputs": [], "expected_outputs": [],
            "constraints": [], "execution_status": "PENDING", "verification_status": "NOT_RUN", "failure": None,
            "evidence": [], "provenance": {}, "attempts": {"count": 0, "max": DEFAULT_MAX_ATTEMPTS, "signatures": []},
            "verified_spec_hash": None, "ops": [], "recovery": [], "events": 0}


def fold(events: Iterable[Dict[str, Any]], tid: str = "") -> Dict[str, Any]:
    """Current state of a task from its events (oldest first)."""
    t = _blank(tid)
    for e in events:
        t["events"] += 1
        ev = e.get("ev")
        if ev == "created":
            for k in ("task_id", "parent_task_id", "stage", "scope"):
                if e.get(k) is not None:
                    t[k] = e[k]
            for k in ("inputs", "expected_outputs", "constraints"):
                t[k] = list(e.get(k) or [])
            t["provenance"] = dict(e.get("provenance") or {})
            if e.get("max_attempts"):
                t["attempts"]["max"] = int(e["max_attempts"])
        elif ev == "started":
            t["execution_status"] = "RUNNING"
            t["attempts"]["count"] += 1
            if e.get("op_id"):
                t["ops"].append(e["op_id"])
            if t["verification_status"] in ("PASS", "FAIL"):
                t["verification_status"] = "STALE"      # a new execution invalidates the earlier verification
        elif ev == "succeeded":
            t["execution_status"] = "SUCCEEDED"
            t["failure"] = None
        elif ev == "failed":
            t["execution_status"] = "FAILED"
            t["failure"] = dict(e.get("failure") or {})
            sig = (e.get("failure") or {}).get("signature")
            if sig:
                t["attempts"]["signatures"].append(sig)
        elif ev == "blocked":
            t["execution_status"] = "BLOCKED"
            if e.get("failure"):
                t["failure"] = dict(e["failure"])
        elif ev == "superseded":
            t["execution_status"] = "SUPERSEDED"
        elif ev == "verified":
            t["verification_status"] = "PASS" if e.get("ok") else "FAIL"
            t["verified_spec_hash"] = e.get("spec_hash")
            t["failure"] = dict(e["failure"]) if (not e.get("ok") and e.get("failure")) else (None if e.get("ok") else t["failure"])
        elif ev == "recovery":
            t["recovery"].append({k: v for k, v in e.items() if k != "ev"})
        if e.get("evidence"):
            t["evidence"].extend(e["evidence"])
        if e.get("ts"):
            t["provenance"].setdefault("ts", e["ts"])
            t["provenance"]["last_ts"] = e["ts"]
    return t


def freshness(record: Dict[str, Any], current_spec_hash: Optional[str]) -> str:
    """verification_status with the ledger's spec_hash freshness rule applied (desk.ledger.verification_state)."""
    st = record.get("verification_status", "NOT_RUN")
    if st == "PASS" and current_spec_hash and record.get("verified_spec_hash") and record["verified_spec_hash"] != current_spec_hash:
        return "STALE"
    return st


# ------------------------------------------------------------------------------------------------ schema
def validate(record: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed schema check of a folded record (section 7.2). Returns the record or raises TaskSchemaError."""
    p: List[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            p.append(msg)

    if not isinstance(record, dict):
        raise TaskSchemaError("task record is not an object")
    for k in ("task_id", "stage", "inputs", "expected_outputs", "constraints", "execution_status", "verification_status",
              "failure", "evidence", "provenance", "attempts"):
        need(k in record, f"missing field '{k}'")
    if p:
        raise TaskSchemaError("invalid task record: " + "; ".join(p), problems=p)
    need(isinstance(record["task_id"], str) and bool(_ID_RX.match(record["task_id"])), "task_id must look like T-<stage>-<scope>")
    need(record["stage"] in STAGES, f"stage must be one of {STAGES}")
    for k, keys in (("inputs", ("kind", "ref")), ("expected_outputs", ("kind", "ref", "acceptance")),
                    ("constraints", ("rule_id", "source")), ("evidence", ("kind", "ref"))):
        v = record[k]
        need(isinstance(v, list), f"{k} must be a list")
        for i, item in enumerate(v if isinstance(v, list) else []):
            need(isinstance(item, dict) and all(item.get(f) for f in keys), f"{k}[{i}] needs {', '.join(keys)}")
    need(bool(record["inputs"]), "inputs must name at least one input")
    need(bool(record["expected_outputs"]), "expected_outputs must name at least one output")
    need(record["execution_status"] in EXECUTION, f"execution_status must be one of {EXECUTION}")
    need(record["verification_status"] in VERIFICATION, f"verification_status must be one of {VERIFICATION}")
    f = record["failure"]
    if f is not None:
        from desk.reliability.models import FailureCategory
        need(isinstance(f, dict) and f.get("category") in FailureCategory.__members__, "failure needs a known FailureCategory")
        need(isinstance(f, dict) and f.get("layer") in LAYERS, f"failure layer must be one of {LAYERS}")
    if record["execution_status"] == "FAILED":
        need(f is not None, "a FAILED task needs a failure classification")
    prov = record["provenance"]
    need(isinstance(prov, dict) and bool(prov.get("actor")) and bool(prov.get("ts")), "provenance needs actor and ts")
    a = record["attempts"]
    need(isinstance(a, dict) and isinstance(a.get("count"), int) and isinstance(a.get("max"), int)
         and isinstance(a.get("signatures"), list), "attempts needs count, max, signatures")
    if p:
        raise TaskSchemaError("invalid task record: " + "; ".join(p), problems=p)
    return record


# ------------------------------------------------------------------------------------------------ store
class TaskStore:
    def __init__(self, project: str):
        self.project = project

    def dir(self) -> str:
        return os.path.join(self.project, "state", "tasks")

    def path(self, tid: str) -> str:
        if not _ID_RX.match(tid or ""):
            raise TaskSchemaError(f"bad task id {tid!r}")
        return os.path.join(self.dir(), tid + ".jsonl")

    def exists(self, tid: str) -> bool:
        return os.path.exists(self.path(tid))

    def append(self, tid: str, ev: str, **fields: Any) -> Dict[str, Any]:
        e = {"ev": ev, "ts": fields.pop("ts", None) or _now(), **{k: v for k, v in fields.items() if v is not None}}
        os.makedirs(self.dir(), exist_ok=True)
        with open(self.path(tid), "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        return e

    def create(self, stage: str, scope: str, inputs: List[Dict[str, Any]], expected_outputs: List[Dict[str, Any]],
               constraints: Optional[List[Dict[str, Any]]] = None, actor: str = "engine:desk",
               parent_task_id: Optional[str] = None, max_attempts: int = DEFAULT_MAX_ATTEMPTS,
               tid: Optional[str] = None) -> Dict[str, Any]:
        """Open a task; the created event is validated before it is written, so a malformed task never lands."""
        tid = tid or task_id(stage, scope)
        if self.exists(tid):
            return self.get(tid)
        ts = _now()
        created = {"task_id": tid, "parent_task_id": parent_task_id, "stage": stage, "scope": scope, "inputs": inputs,
                   "expected_outputs": expected_outputs, "constraints": constraints or [],
                   "provenance": {"actor": actor, "desk_commit": _desk_commit(), "ts": ts}, "max_attempts": max_attempts}
        validate(fold([dict(created, ev="created", ts=ts)], tid))
        self.append(tid, "created", ts=ts, **created)
        return self.get(tid)

    def events(self, tid: str) -> List[Dict[str, Any]]:
        p = self.path(tid)
        if not os.path.exists(p):
            raise ProjectError(f"no task {tid} in {self.project}")
        out = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue      # a torn last line from an interrupted write is skipped, never guessed
        return out

    def get(self, tid: str) -> Dict[str, Any]:
        return fold(self.events(tid), tid)

    def ids(self) -> List[str]:
        if not os.path.isdir(self.dir()):
            return []
        return sorted(f[:-6] for f in os.listdir(self.dir()) if f.endswith(".jsonl"))


# ------------------------------------------------------------------------------------------------ emission hooks
def _ensure(store: TaskStore, stage: str, scope: str, actor: str) -> str:
    tid = task_id(stage, scope)
    if not store.exists(tid):
        if stage == "schematic_block":
            inputs = [{"kind": "spec", "ref": f"blocks/{scope}.json"}]
            outputs = [{"kind": "gate", "ref": f"verify:{scope}", "acceptance": "VERIFIED"}]
        else:
            inputs = [{"kind": "artifact", "ref": scope}]
            outputs = [{"kind": "gate", "ref": f"{stage}:{scope}", "acceptance": "PASS"}]
        store.create(stage, scope, inputs, outputs, actor=actor)
    return tid


def on_op(project: str, phase: str, rec: Dict[str, Any]) -> None:
    """Called by desk.ops.write_op on begin / end / fail. One task per (stage, target); every op is one attempt."""
    stage = OP_STAGE.get(str(rec.get("op")))
    if stage is None:
        return
    store = TaskStore(project)
    tid = _ensure(store, stage, str(rec.get("target") or "scope"), f"engine:{rec.get('op')}")
    ev = {"kind": "ops_journal", "ref": f"state/ops.jsonl#{rec.get('id')}"}
    if phase == "begin":
        store.append(tid, "started", op_id=rec.get("id"), evidence=[ev])
    elif phase == "end":
        store.append(tid, "succeeded", op_id=rec.get("id"), evidence=[ev])
    elif phase == "fail":
        from desk.reliability.failure_classifier import signature
        from desk.reliability.models import FailureCategory as C
        err = str(rec.get("error") or "")
        cat = C.PARTIAL_MUTATION if rec.get("dirty") else C.UNKNOWN_FAILURE
        store.append(tid, "failed", op_id=rec.get("id"), evidence=[dict(ev, excerpt=err[:200])],
                     failure={"category": cat.value, "layer": "OPERATIONAL", "error": err[:300],
                              "signature": signature(cat, err, str(rec.get("op") or ""))})


def record_verify(project: str, block_id: str, ok: bool, spec_hash: Optional[str] = None, report: str = "",
                  failure_category: str = "CONNECTIVITY_VERIFICATION_FAILURE", actor: str = "engine:verify") -> Dict[str, Any]:
    """Hook for tools/verify.py: record a block verification result (validator output) on its schematic_block task."""
    store = TaskStore(project)
    tid = _ensure(store, "schematic_block", block_id, actor)
    evidence = [{"kind": "gate_report", "ref": f"verify:{block_id}", "excerpt": str(report)[:300]}]
    failure = None if ok else {"category": failure_category, "layer": "ENGINEERING", "error": str(report)[:300]}
    store.append(tid, "verified", ok=bool(ok), spec_hash=spec_hash, evidence=evidence, failure=failure, actor=actor)
    return store.get(tid)


# ------------------------------------------------------------------------------------------------ display
def fmt(record: Dict[str, Any], current_spec_hash: Optional[str] = None) -> str:
    def items(xs, keys):
        return "\n".join("    - " + " | ".join(str(x.get(k)) for k in keys if x.get(k)) for x in xs) or "    (none)"
    f = record.get("failure") or {}
    a = record.get("attempts") or {}
    prov = record.get("provenance") or {}
    return "\n".join([
        f"TASK {record['task_id']}  stage={record.get('stage')}  parent={record.get('parent_task_id') or '-'}",
        "  inputs:", items(record.get("inputs", []), ("kind", "ref", "hash")),
        "  expected outputs:", items(record.get("expected_outputs", []), ("kind", "ref", "acceptance")),
        "  constraints:", items(record.get("constraints", []), ("rule_id", "source", "enforcement")),
        f"  execution status:    {record.get('execution_status')}",
        f"  verification status: {freshness(record, current_spec_hash)}",
        f"  failure class:       {(str(f.get('category')) + ' / ' + str(f.get('layer'))) if f else 'none'}",
        f"  attempts:            {a.get('count')} of {a.get('max')}",
        f"  provenance:          {prov.get('actor')} @ {prov.get('ts')} (desk {prov.get('desk_commit') or 'unknown'})",
        f"  evidence:            {len(record.get('evidence', []))} item(s)",
    ])
