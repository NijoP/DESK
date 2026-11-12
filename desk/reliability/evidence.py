"""Layer 1 of the diagnosis: a deterministic evidence collector.

Establishes facts before anyone reasons about them: gateway windows and which project/document each hosts, the bound
session, pending journal operations, the routing run's progress / chunk / feasibility / failure files, the engine and
Java versions, resource usage and known-failure matches. Every fact becomes an `EvidenceRef` on the FailureRecord so
later statements can cite it by id. Readers are injectable and every source is optional, so the collector works
offline in tests and never raises.

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from desk.reliability.models import FailureRecord, fingerprint, redact
from desk.reliability import registry as KF

_ROUTE_FILES = ("progress.json", "progress_chunks.json", "feasibility.json", "route_failure.json", "preflight.json",
                "engineering_decisions.json", "dense_analysis.json")


def _tail(path: str, n: int = 40) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def _json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class EvidenceCollector:
    """`collect(record)` returns a facts dict and attaches evidence refs to the record."""

    def __init__(self, project_path: Optional[str] = None, gateway: Optional[Any] = None, session: Optional[Any] = None,
                 engine_versions: Optional[Callable[[], Dict[str, str]]] = None,
                 resource_sampler: Optional[Callable[[], Dict[str, Any]]] = None, now: Callable[[], float] = time.time):
        self.project_path = project_path
        self.gateway = gateway
        self.session = session
        self.engine_versions = engine_versions
        self.resource_sampler = resource_sampler
        self.now = now

    # ---- sources -------------------------------------------------------------------------------------------
    def windows(self, rec: FailureRecord) -> List[Dict[str, Any]]:
        if self.gateway is None:
            return []
        try:
            from desk.reliability.project_isolation import SessionResolver
            wins = [w.__dict__ for w in SessionResolver(self.gateway).discover()]
        except Exception as e:
            rec.add_evidence("process", "gateway", f"window discovery failed: {e}")
            return []
        rec.add_evidence("readback", "/eda-windows", f"{len(wins)} window(s): " + "; ".join(
            f"{w.get('window_id')}={w.get('project_name') or '?'}/{(w.get('document_uuid') or '')[:8]}" for w in wins), json.dumps(wins, default=str))
        return wins

    def journal(self, rec: FailureRecord) -> List[Dict[str, Any]]:
        if not self.project_path:
            return []
        try:
            from desk import ops
            pend = ops.pending(self.project_path)
        except Exception:
            return []
        if pend:
            rec.add_evidence("journal", os.path.join(self.project_path, "state", "ops.jsonl"),
                             f"{len(pend)} pending/dirty operation(s): " + ", ".join(f"{p['op']}#{p['id']}{' DIRTY' if p.get('dirty') else ''}" for p in pend))
        return pend

    def route_files(self, rec: FailureRecord) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not self.project_path:
            return out
        wd = os.path.join(self.project_path, "state", "route")
        for name in _ROUTE_FILES:
            p = os.path.join(wd, name)
            data = _json(p)
            if data is None:
                continue
            out[name] = data
            summary = {"progress.json": lambda d: f"phase {d.get('phase')} passes {d.get('passes')} best {d.get('best_unrouted')} last {d.get('last_unrouted')}",
                       "progress_chunks.json": lambda d: f"{len(d.get('chunks', []))} chunk(s), outcomes {d.get('outcomes')}, checkpoint best {d.get('best_unrouted')}",
                       "feasibility.json": lambda d: d.get("summary", ""),
                       "route_failure.json": lambda d: f"{d.get('category')} {d.get('failure_id')}",
                       "preflight.json": lambda d: f"passed {d.get('passed')} errors {d.get('errors')}",
                       "engineering_decisions.json": lambda d: f"{len(d)} blocking decision(s)" if isinstance(d, list) else "",
                       "dense_analysis.json": lambda d: f"congestion {d.get('overall_congestion')} hotspots {len(d.get('hotspots', []))} escape {d.get('escape_summary')}",
                       }.get(name, lambda d: "")(data)
            rec.add_evidence("file", p, summary or name, json.dumps(data, default=str)[:20000])
        log = os.path.join(wd, "freerouting.log")
        if os.path.exists(log):
            tail = _tail(log, 30)
            out["freerouting_log_tail"] = tail
            rec.add_evidence("log", log, f"last {tail.count(chr(10)) + 1} line(s) of the engine log", tail)
        return out

    def engines(self, rec: FailureRecord) -> Dict[str, str]:
        if self.engine_versions is None:
            return {}
        try:
            v = self.engine_versions()
        except Exception as e:
            v = {"error": str(e)}
        if v:
            rec.add_evidence("env", "engine", ", ".join(f"{k}={val}" for k, val in v.items()))
        return v

    def resources(self, rec: FailureRecord) -> Dict[str, Any]:
        if self.resource_sampler is None:
            return {}
        try:
            r = self.resource_sampler()
        except Exception:
            return {}
        rec.add_evidence("process", "resources", json.dumps(r, default=str)[:300])
        return r

    # ---- packet -------------------------------------------------------------------------------------------
    def collect(self, rec: FailureRecord) -> Dict[str, Any]:
        facts: Dict[str, Any] = {"collected_at": self.now(), "category": rec.category.value, "execution_state": rec.execution_state.value,
                                 "mutating": rec.execution_state.value not in ("NOT_EXECUTED",) and bool(rec.params.get("verifier") or rec.operation.startswith(("route_", "pcb_", "build", "wire")))}
        wins = self.windows(rec)
        facts["windows"] = wins
        if self.session is not None:
            s = self.session
            wid = getattr(s, "window_id", None) or getattr(s, "last_window_id", None)
            facts["session"] = {"window_id": wid, "project_uuid": getattr(s, "project_uuid", None),
                                "bound_by": getattr(s, "bound_by", None), "generation": getattr(s, "window_generation", None),
                                "rotations": getattr(s, "rotations", None), "last_response": getattr(s, "last_response_meta", None)}
            rec.add_evidence("process", "session", json.dumps(redact(facts["session"]), default=str)[:400])
            if wins:
                mine = [w for w in wins if w.get("project_uuid") and w.get("project_uuid") == getattr(s, "project_uuid", None)]
                facts["windows_hosting_project"] = [w.get("window_id") for w in mine]
                facts["bound_window_present"] = any(w.get("window_id") == wid for w in wins)
        facts["pending_ops"] = self.journal(rec)
        rf = self.route_files(rec)
        if rf:
            facts["route"] = {k: v for k, v in rf.items() if k != "freerouting_log_tail"}
            facts["freerouting_log_tail"] = rf.get("freerouting_log_tail", "")
            pc = rf.get("progress_chunks.json") or {}
            facts["checkpoint"] = pc.get("checkpoint") or {}
            facts["chunk_outcomes"] = pc.get("outcomes") or []
            facts["plans"] = pc.get("plans") or []
            feas = rf.get("feasibility.json") or {}
            facts["decisions"] = rf.get("engineering_decisions.json") or feas.get("decisions") or []
            facts["blocked_pads"] = feas.get("blocked", [])[:20]
            dense = rf.get("dense_analysis.json") or {}
            facts["hotspots"] = dense.get("hotspots", [])[:8]
            prog = rf.get("progress.json") or {}
            facts["problem_nets"] = prog.get("problem_nets", [])
            facts["pass_history"] = prog.get("history", [])
        facts["engines"] = self.engines(rec)
        facts["resources"] = self.resources(rec)
        from desk.reliability import api_registry
        methods = rec.params.get("methods") or []
        facts["dialog_method"] = next((m for m in methods if api_registry.capability(m).status == api_registry.CapabilityStatus.DIALOG), None)
        facts["capabilities"] = {m: api_registry.capability(m).status.value for m in methods}
        known = KF.match(rec)
        facts["known_failures"] = [k.id for k in known]
        for k in known:
            rec.add_evidence("incident", k.id, f"{k.title} ({k.confidence.value})")
        facts["signature"] = evidence_signature(facts)
        return facts


def evidence_signature(facts: Dict[str, Any]) -> str:
    """Hash of the facts that would change a plan (windows, chunk outcomes, checkpoint, decisions, pending ops)."""
    core = {"windows": [(w.get("window_id"), w.get("project_uuid"), w.get("document_uuid")) for w in facts.get("windows", [])],
            "outcomes": facts.get("chunk_outcomes"), "checkpoint_best": (facts.get("checkpoint") or {}).get("best_unrouted"),
            "decisions": [d.get("decision_id") for d in facts.get("decisions", []) if isinstance(d, dict)],
            "pending": [p.get("id") for p in facts.get("pending_ops", [])], "category": facts.get("category"),
            "state": facts.get("execution_state"), "engines": facts.get("engines")}
    return fingerprint(core)
