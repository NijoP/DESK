"""Typed models of the DESK reliability layer.

One vocabulary for every subsystem that can fail (bridge, journal, routing engine, agent tool calls):

* `FailureCategory`   the thirty structured failure classes
* `ExecutionState`    what is known about whether a live operation ran (cases A-H of the API failure model)
* `Confidence`        how well a statement is supported by evidence
* `RiskClass`         what the recovery policy allows for an action
* `EvidenceRef`       a pointer to a fact (file, log line, readback, journal record) with a stable id
* `FailureRecord`     the full record of one failure, with before/after fingerprints and the recovery trail
* `Hypothesis`, `RecoveryAction`, `RecoveryPlan`, `RecoveryOutcome`, `VerificationResult`

Nothing here talks to EasyEDA, Java or the network. Records serialise to plain JSON (`to_dict`) and never carry a
secret: `redact()` masks keys that look like credentials and values that look like API keys.

Zero external dependencies.
"""
from __future__ import annotations

import enum
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class FailureCategory(str, enum.Enum):
    TRANSIENT_NETWORK = "TRANSIENT_NETWORK"
    API_UNAVAILABLE = "API_UNAVAILABLE"
    API_TIMEOUT = "API_TIMEOUT"
    API_SCHEMA_MISMATCH = "API_SCHEMA_MISMATCH"
    API_FALSE_SUCCESS = "API_FALSE_SUCCESS"
    WRONG_PROJECT_CONTEXT = "WRONG_PROJECT_CONTEXT"
    WINDOW_DISCONNECTED = "WINDOW_DISCONNECTED"
    WINDOW_ID_ROTATED = "WINDOW_ID_ROTATED"
    DOCUMENT_CONTEXT_LOST = "DOCUMENT_CONTEXT_LOST"
    CONCURRENT_WRITE_CONFLICT = "CONCURRENT_WRITE_CONFLICT"
    LOCK_CONFLICT = "LOCK_CONFLICT"
    PARTIAL_MUTATION = "PARTIAL_MUTATION"
    UNKNOWN_MUTATION_OUTCOME = "UNKNOWN_MUTATION_OUTCOME"
    JAVA_RUNTIME_INCOMPATIBLE = "JAVA_RUNTIME_INCOMPATIBLE"
    ROUTER_ENGINE_CRASH = "ROUTER_ENGINE_CRASH"
    ROUTER_ENGINE_TIMEOUT = "ROUTER_ENGINE_TIMEOUT"
    ROUTER_STAGNATION = "ROUTER_STAGNATION"
    ROUTER_NO_LEGAL_ESCAPE = "ROUTER_NO_LEGAL_ESCAPE"
    ROUTER_RULE_CONFLICT = "ROUTER_RULE_CONFLICT"
    ROUTER_RESOURCE_EXHAUSTION = "ROUTER_RESOURCE_EXHAUSTION"
    ROUTER_SES_MISSING = "ROUTER_SES_MISSING"
    ROUTER_SES_INVALID = "ROUTER_SES_INVALID"
    CONNECTIVITY_VERIFICATION_FAILURE = "CONNECTIVITY_VERIFICATION_FAILURE"
    DRC_FAILURE = "DRC_FAILURE"
    ERC_FAILURE = "ERC_FAILURE"
    REQUIREMENT_CONFLICT = "REQUIREMENT_CONFLICT"
    DESIGN_PROFILE_INVALID = "DESIGN_PROFILE_INVALID"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    EXTERNAL_TOOL_UNSUPPORTED = "EXTERNAL_TOOL_UNSUPPORTED"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class ExecutionState(str, enum.Enum):
    """What is known about a live request (API failure model cases A-H plus the two certain states)."""
    NOT_EXECUTED = "NOT_EXECUTED"                       # A: failed before reaching the gateway
    GATEWAY_NOT_EXECUTED = "GATEWAY_NOT_EXECUTED"       # B: gateway answered, the extension did not run it
    EXECUTED_RESPONSE_LOST = "EXECUTED_RESPONSE_LOST"   # C: ran (or may still be running), reply lost
    PARTIAL = "PARTIAL"                                 # D: part of the mutation applied
    EXECUTED_STALE_READBACK = "EXECUTED_STALE_READBACK" # E: completed, readback not yet consistent
    FALSE_SUCCESS = "FALSE_SUCCESS"                     # F: success returned, no change observed
    UNSUPPORTED = "UNSUPPORTED"                         # G: method not supported for this document type
    WRONG_DOCUMENT = "WRONG_DOCUMENT"                   # H: sent to the wrong document
    EXECUTED_VERIFIED = "EXECUTED_VERIFIED"             # readback proved the intended postcondition
    UNKNOWN = "UNKNOWN"


class Confidence(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"
    PLAUSIBLE = "PLAUSIBLE"
    UNVERIFIED = "UNVERIFIED"
    DISPROVEN = "DISPROVEN"


class RiskClass(str, enum.Enum):
    AUTO = "AUTO"            # may run without a human (read-only reconnects, checkpoint resume, temp workspace)
    APPROVAL = "APPROVAL"    # needs a recorded human approval (rule changes, deletions, uncertain mutations)
    REFUSE = "REFUSE"        # never performed by the self-healing layer


class HealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    UNVERIFIED = "UNVERIFIED"


# ------------------------------------------------------------------------------------------------ helpers
_SECRET_KEY_RX = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|cookie)", re.I)
_SECRET_VALUE_RX = re.compile(r"\b(nvapi-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._\-]{8,})")


def redact(value: Any) -> Any:
    """Return a copy of `value` with credential-like keys masked and API-key-like strings replaced."""
    if isinstance(value, dict):
        return {k: ("***" if _SECRET_KEY_RX.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _SECRET_VALUE_RX.sub("***", value)
    return value


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(obj: Any) -> str:
    """Stable sha256 of a state snapshot (counts, ids, coordinates ...) for before/after comparison."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:24]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ------------------------------------------------------------------------------------------------ evidence
@dataclass
class EvidenceRef:
    """A fact with an address. `kind` is one of: file, log, readback, journal, process, env, incident, test."""
    id: str
    kind: str
    source: str                 # path, URL-less locator, journal id, method name
    summary: str
    sha256: str = ""
    ts: float = field(default_factory=time.time)

    @classmethod
    def make(cls, kind: str, source: str, summary: str, content: Optional[str] = None) -> "EvidenceRef":
        sha = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()[:16] if content else ""
        return cls(id=new_id("EV"), kind=kind, source=source, summary=redact(summary), sha256=sha)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------------------------------------ diagnosis
@dataclass
class Hypothesis:
    category: FailureCategory
    statement: str
    confidence: Confidence
    evidence_ids: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    source: str = "deterministic"    # deterministic | model | evaluator | human

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["confidence"] = self.confidence.value
        return d


@dataclass
class VerificationCheck:
    name: str
    expected: Any
    actual: Any
    ok: bool
    note: str = ""


@dataclass
class VerificationResult:
    """Independent readback against the intended postcondition. `passed` is True only when every check is ok
    and at least one check was performed (missing evidence is a failure, never a pass)."""
    checks: List[VerificationCheck] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    performed_at: float = field(default_factory=time.time)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def add(self, name: str, expected: Any, actual: Any, ok: Optional[bool] = None, note: str = "") -> "VerificationResult":
        self.checks.append(VerificationCheck(name, expected, actual, (expected == actual) if ok is None else bool(ok), note))
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "checks": [asdict(c) for c in self.checks], "evidence_ids": list(self.evidence_ids),
                "performed_at": self.performed_at}


# ------------------------------------------------------------------------------------------------ recovery
@dataclass
class RecoveryAction:
    id: str
    kind: str                      # e.g. "rebind_session", "resume_from_checkpoint", "retry_read", "escalate"
    description: str
    risk: RiskClass
    idempotent: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    expected_effect: str = ""
    verification: str = ""         # how the outcome will be verified, in words

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk"] = self.risk.value
        return d


@dataclass
class RecoveryPlan:
    failure_id: str
    actions: List[RecoveryAction]
    rationale: str
    requires_approval: bool
    verification_criteria: List[str] = field(default_factory=list)
    refused: List[str] = field(default_factory=list)   # actions the policy refused, with the reason
    source: str = "deterministic"

    def to_dict(self) -> Dict[str, Any]:
        return {"failure_id": self.failure_id, "actions": [a.to_dict() for a in self.actions], "rationale": self.rationale,
                "requires_approval": self.requires_approval, "verification_criteria": list(self.verification_criteria),
                "refused": list(self.refused), "source": self.source}


@dataclass
class RecoveryOutcome:
    action_id: str
    executed: bool
    result: str                    # "SUCCESS", "FAILED", "REFUSED", "SKIPPED", "UNKNOWN"
    verification: Optional[VerificationResult] = None
    note: str = ""
    approval_id: Optional[str] = None
    journal_id: Optional[str] = None

    @property
    def verified(self) -> bool:
        return bool(self.verification and self.verification.passed)

    def to_dict(self) -> Dict[str, Any]:
        return {"action_id": self.action_id, "executed": self.executed, "result": self.result,
                "verification": self.verification.to_dict() if self.verification else None, "note": self.note,
                "approval_id": self.approval_id, "journal_id": self.journal_id, "verified": self.verified}


# ------------------------------------------------------------------------------------------------ failure record
@dataclass
class FailureRecord:
    """Everything the self-healing lifecycle knows about one failure. Written to
    projects/<P>/state/reliability/failures.jsonl by the supervisor."""
    failure_id: str
    category: FailureCategory
    module: str
    operation: str
    message: str
    project_id: str = ""
    project_uuid: str = ""
    session_id: str = ""
    window_id: str = ""
    document_uuid: str = ""
    operation_id: str = ""
    run_id: str = ""
    ts: float = field(default_factory=time.time)
    command: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    engine_version: str = ""
    api_version: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""
    request_meta: Dict[str, Any] = field(default_factory=dict)
    response_meta: Dict[str, Any] = field(default_factory=dict)
    before_fingerprint: str = ""
    after_fingerprint: str = ""
    execution_state: ExecutionState = ExecutionState.UNKNOWN
    evidence: List[EvidenceRef] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    confidence: Confidence = Confidence.UNVERIFIED
    plan: Optional[RecoveryPlan] = None
    outcomes: List[RecoveryOutcome] = field(default_factory=list)
    verification: Optional[VerificationResult] = None
    status: str = "OPEN"           # OPEN | RECOVERING | RECOVERED | VERIFIED | REFUSED | ESCALATED | FAILED
    related_incidents: List[str] = field(default_factory=list)
    signature: str = ""            # stable key used to match known failures

    @classmethod
    def new(cls, category: FailureCategory, module: str, operation: str, message: str, **fields: Any) -> "FailureRecord":
        return cls(failure_id=new_id("FR"), category=category, module=module, operation=operation,
                   message=redact(str(message))[:2000], **fields)

    def add_evidence(self, kind: str, source: str, summary: str, content: Optional[str] = None) -> EvidenceRef:
        ev = EvidenceRef.make(kind, source, summary, content)
        self.evidence.append(ev)
        return ev

    @property
    def root_cause(self) -> Optional[Hypothesis]:
        """The best-supported hypothesis, or None. DISPROVEN hypotheses never qualify."""
        order = [Confidence.CONFIRMED, Confidence.STRONGLY_SUPPORTED, Confidence.PLAUSIBLE, Confidence.UNVERIFIED]
        live = [h for h in self.hypotheses if h.confidence != Confidence.DISPROVEN]
        live.sort(key=lambda h: order.index(h.confidence))
        return live[0] if live else None

    @property
    def healed(self) -> bool:
        """True only when an independent verification passed after a recovery was executed."""
        return self.status == "VERIFIED" and bool(self.verification and self.verification.passed) \
            and any(o.executed and o.result == "SUCCESS" for o in self.outcomes)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "failure_id": self.failure_id, "category": self.category.value, "module": self.module, "operation": self.operation,
            "message": self.message, "project_id": self.project_id, "project_uuid": self.project_uuid,
            "session_id": self.session_id, "window_id": self.window_id, "document_uuid": self.document_uuid,
            "operation_id": self.operation_id, "run_id": self.run_id, "ts": self.ts, "command": list(self.command),
            "params": redact(self.params), "engine_version": self.engine_version, "api_version": self.api_version,
            "stdout_tail": redact(self.stdout_tail)[-2000:], "stderr_tail": redact(self.stderr_tail)[-2000:],
            "request_meta": redact(self.request_meta), "response_meta": redact(self.response_meta),
            "before_fingerprint": self.before_fingerprint, "after_fingerprint": self.after_fingerprint,
            "execution_state": self.execution_state.value, "evidence": [e.to_dict() for e in self.evidence],
            "hypotheses": [h.to_dict() for h in self.hypotheses], "confidence": self.confidence.value,
            "plan": self.plan.to_dict() if self.plan else None, "outcomes": [o.to_dict() for o in self.outcomes],
            "verification": self.verification.to_dict() if self.verification else None, "status": self.status,
            "related_incidents": list(self.related_incidents), "signature": self.signature, "healed": self.healed,
        }
        rc = self.root_cause
        d["root_cause"] = rc.to_dict() if rc else None
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FailureRecord":
        rec = cls(failure_id=d["failure_id"], category=FailureCategory(d["category"]), module=d.get("module", ""),
                  operation=d.get("operation", ""), message=d.get("message", ""))
        for k in ("project_id", "project_uuid", "session_id", "window_id", "document_uuid", "operation_id", "run_id",
                  "engine_version", "api_version", "stdout_tail", "stderr_tail", "before_fingerprint", "after_fingerprint",
                  "status", "signature"):
            setattr(rec, k, d.get(k, getattr(rec, k)))
        rec.ts = float(d.get("ts", rec.ts))
        rec.command = list(d.get("command", []))
        rec.params = dict(d.get("params", {}))
        rec.request_meta = dict(d.get("request_meta", {}))
        rec.response_meta = dict(d.get("response_meta", {}))
        rec.execution_state = ExecutionState(d.get("execution_state", "UNKNOWN"))
        rec.confidence = Confidence(d.get("confidence", "UNVERIFIED"))
        rec.evidence = [EvidenceRef(**e) for e in d.get("evidence", [])]
        rec.hypotheses = [Hypothesis(category=FailureCategory(h["category"]), statement=h["statement"],
                                     confidence=Confidence(h["confidence"]), evidence_ids=list(h.get("evidence_ids", [])),
                                     alternatives=list(h.get("alternatives", [])), missing_evidence=list(h.get("missing_evidence", [])),
                                     source=h.get("source", "deterministic")) for h in d.get("hypotheses", [])]
        rec.related_incidents = list(d.get("related_incidents", []))
        if d.get("verification"):
            v = d["verification"]
            rec.verification = VerificationResult([VerificationCheck(**c) for c in v.get("checks", [])], list(v.get("evidence_ids", [])),
                                                  float(v.get("performed_at", 0.0)))
        for o in d.get("outcomes", []):
            ver = None
            if o.get("verification"):
                v = o["verification"]
                ver = VerificationResult([VerificationCheck(**c) for c in v.get("checks", [])], list(v.get("evidence_ids", [])),
                                         float(v.get("performed_at", 0.0)))
            rec.outcomes.append(RecoveryOutcome(o["action_id"], bool(o.get("executed")), o.get("result", "UNKNOWN"), ver,
                                                o.get("note", ""), o.get("approval_id"), o.get("journal_id")))
        if d.get("plan"):
            p = d["plan"]
            rec.plan = RecoveryPlan(p["failure_id"], [RecoveryAction(a["id"], a["kind"], a["description"], RiskClass(a["risk"]),
                                                                    bool(a.get("idempotent", True)), dict(a.get("params", {})),
                                                                    a.get("expected_effect", ""), a.get("verification", ""))
                                                     for a in p.get("actions", [])],
                                    p.get("rationale", ""), bool(p.get("requires_approval")), list(p.get("verification_criteria", [])),
                                    list(p.get("refused", [])), p.get("source", "deterministic"))
        return rec


ROUTER_CATEGORIES = {
    FailureCategory.JAVA_RUNTIME_INCOMPATIBLE, FailureCategory.ROUTER_ENGINE_CRASH, FailureCategory.ROUTER_ENGINE_TIMEOUT,
    FailureCategory.ROUTER_STAGNATION, FailureCategory.ROUTER_NO_LEGAL_ESCAPE, FailureCategory.ROUTER_RULE_CONFLICT,
    FailureCategory.ROUTER_RESOURCE_EXHAUSTION, FailureCategory.ROUTER_SES_MISSING, FailureCategory.ROUTER_SES_INVALID,
}
API_CATEGORIES = {
    FailureCategory.TRANSIENT_NETWORK, FailureCategory.API_UNAVAILABLE, FailureCategory.API_TIMEOUT,
    FailureCategory.API_SCHEMA_MISMATCH, FailureCategory.API_FALSE_SUCCESS, FailureCategory.WRONG_PROJECT_CONTEXT,
    FailureCategory.WINDOW_DISCONNECTED, FailureCategory.WINDOW_ID_ROTATED, FailureCategory.DOCUMENT_CONTEXT_LOST,
    FailureCategory.CONCURRENT_WRITE_CONFLICT, FailureCategory.LOCK_CONFLICT, FailureCategory.PARTIAL_MUTATION,
    FailureCategory.UNKNOWN_MUTATION_OUTCOME,
}
