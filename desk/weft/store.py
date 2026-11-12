"""DESK-side records for Weft runs.

Weft's journal holds orchestration state. Engineering records stay under DESK's ownership, in
<projects_root>/<project_id>/state/weft/ :

    requirements/<sha256>.json   stored requirement text
    profiles/<profile_hash>.json compiled domain profile
    notes/<sha256>.json          validated model notes (advisory)
    evidence/<name>.json         verification evidence a quality gate reads
    approvals/<ref>.json         human decisions bound to a subject hash
    results/<key>.json           idempotent node results
    runs/<run_id>.jsonl          one line per node call: the link between a Weft run and DESK records

Nodes exchange hashes and record names, never documents. Nothing here stores credentials.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from desk.weft.contracts import SAFE_ID


class StoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_projects_root() -> str:
    env = os.environ.get("DESK_WEFT_PROJECTS_ROOT")
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "projects")


class RecordStore:
    """Records of one DESK project. Refuses ids that could leave the projects root."""

    def __init__(self, project_id: str, projects_root: Optional[str] = None):
        if not isinstance(project_id, str) or not SAFE_ID.match(project_id):
            raise StoreError("INVALID_INPUT", "projectId must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
        self.project_id = project_id
        self.projects_root = os.path.abspath(projects_root or default_projects_root())
        self.project_dir = os.path.join(self.projects_root, project_id)
        if not os.path.isdir(self.project_dir):
            raise StoreError("PROJECT_NOT_FOUND", f"no DESK project folder for '{project_id}'")
        self.root = os.path.join(self.project_dir, "state", "weft")

    # ---- primitives -------------------------------------------------------------------------------------
    def _path(self, kind: str, name: str, ext: str = ".json") -> str:
        if not SAFE_ID.match(name):
            raise StoreError("INVALID_INPUT", f"bad record name for {kind}")
        return os.path.join(self.root, kind, name + ext)

    def _write(self, kind: str, name: str, doc: Dict[str, Any]) -> str:
        path = self._path(kind, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
        return path

    def _read(self, kind: str, name: str) -> Dict[str, Any]:
        path = self._path(kind, name)
        if not os.path.exists(path):
            raise StoreError("RECORD_NOT_FOUND", f"no {kind} record '{name}' in project {self.project_id}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def ref(self, kind: str, name: str) -> str:
        """Evidence reference, relative to the project folder."""
        return f"state/weft/{kind}/{name}.json"

    # ---- reliability (desk/reliability) -------------------------------------------------------------------
    def put_failure(self, doc: Dict[str, Any]) -> str:
        """Store a FailureRecord dict (desk.reliability.models.FailureRecord.to_dict); returns its ref name."""
        name = str(doc.get("failure_id") or "").replace(":", "-")
        self._write("failures", name, doc)
        return name

    def get_failure(self, name: str) -> Dict[str, Any]:
        return self._read("failures", name)

    def put_plan(self, failure_name: str, doc: Dict[str, Any]) -> str:
        self._write("plans", failure_name, doc)
        return failure_name

    # ---- requirements -----------------------------------------------------------------------------------
    def put_requirements(self, text: str) -> str:
        h = sha256_text(text)
        self._write("requirements", h, {"sha256": h, "text": text, "stored_at": time.time()})
        return h

    def get_requirements(self, h: str) -> str:
        doc = self._read("requirements", h)
        if sha256_text(doc.get("text", "")) != h:
            raise StoreError("RECORD_NOT_FOUND", "stored requirements do not match their hash")
        return doc["text"]

    # ---- profiles, notes, evidence ----------------------------------------------------------------------
    def put_profile(self, profile_hash: str, compiled: Dict[str, Any], requirements_hash: str) -> None:
        self._write("profiles", profile_hash, {"profile_hash": profile_hash, "requirements_hash": requirements_hash, "compiled": compiled})

    def get_profile(self, profile_hash: str) -> Dict[str, Any]:
        return self._read("profiles", profile_hash)

    def put_notes(self, doc: Dict[str, Any]) -> str:
        name = sha256_text(canonical(doc))
        self._write("notes", name, doc)
        return name

    def put_evidence(self, name: str, doc: Dict[str, Any]) -> None:
        self._write("evidence", name, doc)

    def get_evidence(self, name: str) -> Dict[str, Any]:
        return self._read("evidence", name)

    # ---- approvals --------------------------------------------------------------------------------------
    def put_approval(self, stage: str, decision: str, subject_hash: str, run_id: str, note: str = "") -> str:
        ref = f"{stage}-{sha256_text(canonical([stage, subject_hash, run_id, decision]))[:16]}"
        self._write("approvals", ref, {"ref": ref, "stage": stage, "decision": decision, "subject_hash": subject_hash,
                                       "run_id": run_id, "note": note, "recorded_at": time.time()})
        return ref

    def get_approval(self, ref: str) -> Dict[str, Any]:
        return self._read("approvals", ref)

    # ---- idempotent results -----------------------------------------------------------------------------
    def get_result(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            return self._read("results", key)
        except StoreError:
            return None

    def put_result(self, key: str, envelope: Dict[str, Any]) -> None:
        self._write("results", key, envelope)

    # ---- run trace --------------------------------------------------------------------------------------
    def trace(self, run_id: str, entry: Dict[str, Any]) -> None:
        name = run_id if SAFE_ID.match(run_id or "") else "untracked"
        path = self._path("runs", name, ".jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(canonical(entry) + "\n")

    def read_trace(self, run_id: str) -> List[Dict[str, Any]]:
        path = self._path("runs", run_id, ".jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def list_runs(self) -> List[Dict[str, Any]]:
        d = os.path.join(self.root, "runs")
        out = []
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".jsonl"):
                    continue
                entries = self.read_trace(fn[:-6])
                if entries:
                    out.append({"runId": fn[:-6], "calls": len(entries), "started": entries[0].get("at"), "last": entries[-1].get("at"),
                                "lastNode": entries[-1].get("node"), "failed": [e["node"] for e in entries if not e.get("ok")],
                                "blocked": [e["node"] for e in entries if e.get("ok") and not e.get("passed")]})
        return out
