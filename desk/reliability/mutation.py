"""The mutation contract: one path for every live EasyEDA change.

    1. precondition           caller-supplied check on the current state (optional)
    2. journal BEGIN          ops.write_op with window id, document uuid, before-fingerprint, idempotency key
    3. target identity        EXPECTED DOCUMENT UUID == ACTIVE DOCUMENT UUID in the bound window
    4. execute                the mutating call (any callable; the bridge in production, a fake in tests)
    5. journal END / UNKNOWN  dirty when the outcome is unknown (timeout, lost response)
    6. independent readback   caller-supplied readback of the live state
    7. postcondition          operation-specific verification contract (desk.reliability.api_registry)
    8. fingerprint comparison before/after, so "returned true, nothing changed" is API_FALSE_SUCCESS

`MutationResult.verified` is the only success signal. HTTP 200, a JS `true`, exit code 0 or a model claiming
success never establish it. The execution state follows the API failure model (cases A-H).

`reconcile()` handles the unknown-outcome case: it never repeats the mutation; it reads the document, compares
against the postcondition and reports whether the operation is complete, partial or absent so the caller can
resume from the verified state.

Zero external dependencies; EasyEDA access is injected.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from desk import ops
from desk.errors import BridgeMutationTimeout, BridgeWindowRotated, IdentityUnverified, BridgeUnreachable, DeskError
from desk.reliability import api_registry
from desk.reliability.models import (ExecutionState, FailureCategory, FailureRecord, VerificationResult, fingerprint)
from desk.reliability.project_isolation import ProjectSession, SessionResolver


@dataclass
class MutationSpec:
    """What one live mutation intends to do and how its completion is proven."""
    op: str                                   # journal op name ("route_import", "pcb_import_changes", ...)
    target: str                               # journal target ("PCB", block id, ...)
    document_uuid: str                        # the document the mutation must land on
    verifier: str                             # api_registry verification contract name
    expected: Any                             # the postcondition the verifier compares against
    classification: str = ops.OP_NON_IDEMPOTENT_MUTATION
    methods: List[str] = field(default_factory=list)   # eda.* methods used (for the capability registry)
    idempotency_key: str = ""                 # same key => same intended change; derived when empty
    approval: Optional[str] = None
    settle_s: float = 0.0                     # wait before the first readback (EasyEDA applies async)
    readback_attempts: int = 2                # readbacks that may still be stale before FALSE_SUCCESS is declared
    readback_interval_s: float = 2.0

    def key(self) -> str:
        if self.idempotency_key:
            return self.idempotency_key
        raw = "|".join([self.op, self.target, self.document_uuid, self.verifier, repr(self.expected)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class MutationResult:
    spec: MutationSpec
    state: ExecutionState
    verification: Optional[VerificationResult]
    before: Any
    after: Any
    before_fingerprint: str
    after_fingerprint: str
    journal_id: str = ""
    raw_return: Any = None
    error: str = ""
    duration_s: float = 0.0
    capability_status: str = ""
    failure: Optional[FailureRecord] = None

    @property
    def verified(self) -> bool:
        return self.state == ExecutionState.EXECUTED_VERIFIED and bool(self.verification and self.verification.passed)

    def to_dict(self) -> Dict[str, Any]:
        return {"op": self.spec.op, "target": self.spec.target, "document_uuid": self.spec.document_uuid, "state": self.state.value,
                "verified": self.verified, "verification": self.verification.to_dict() if self.verification else None,
                "before_fingerprint": self.before_fingerprint, "after_fingerprint": self.after_fingerprint,
                "journal_id": self.journal_id, "raw_return": repr(self.raw_return)[:200], "error": self.error,
                "duration_s": round(self.duration_s, 3), "capability_status": self.capability_status,
                "failure_id": self.failure.failure_id if self.failure else None}


class MutationContract:
    """Runs a `MutationSpec` through the eight steps. `execute` performs the change and returns the raw API value;
    `readback` returns the live state the verifier compares (a count, ids, coordinates, a dict ...)."""

    def __init__(self, project: str, session: ProjectSession, resolver: SessionResolver,
                 sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.time):
        self.project = project
        self.session = session
        self.resolver = resolver
        self.sleep = sleep
        self.now = now

    # ---- steps -------------------------------------------------------------------------------------------
    def _verify_identity(self, document_uuid: str, when: str) -> None:
        try:
            ok = self.resolver.verify_target(self.session, document_uuid)
        except BridgeWindowRotated:
            raise
        if not ok:
            raise IdentityUnverified(
                f"STOP ({when}): window {self.session.window_id or '?'} does not show document {document_uuid} as active "
                f"(active: {self.session.bound_document_uuid or 'unknown'}); the mutation is refused.",
                project_id=self.session.project_id, document_uuid=document_uuid, when=when)

    def _readback_until_settled(self, spec: MutationSpec, readback: Callable[[], Any], before: Any) -> Any:
        """Readback that tolerates EasyEDA applying a change asynchronously: re-read a bounded number of times
        while the state is still identical to `before`."""
        if spec.settle_s > 0:
            self.sleep(spec.settle_s)
        after = readback()
        tries = 0
        while fingerprint(after) == fingerprint(before) and tries < spec.readback_attempts:
            tries += 1
            self.sleep(spec.readback_interval_s)
            after = readback()
        return after

    def run(self, spec: MutationSpec, execute: Callable[[], Any], readback: Callable[[], Any],
            precondition: Optional[Callable[[Any], Optional[str]]] = None) -> MutationResult:
        """Execute the contract. Raises DeskError subclasses for refusals (identity, lock, approval, precondition);
        returns a MutationResult (never raises) for outcomes of the mutation itself."""
        t0 = self.now()
        cap = api_registry.riskiest_status(" ".join(spec.methods)) if spec.methods else api_registry.CapabilityStatus.UNKNOWN
        before = readback()
        bf = fingerprint(before)
        if precondition is not None:
            why = precondition(before)
            if why:
                raise DeskError(f"STOP: precondition failed for {spec.op} on {spec.target}: {why}", op=spec.op, target=spec.target)

        self._verify_identity(spec.document_uuid, "before mutation")
        raw: Any = None
        state = ExecutionState.UNKNOWN
        error = ""
        journal_id = ""
        with ops.write_op(self.project, spec.op, spec.target, classification=spec.classification, approval=spec.approval,
                          window_id=self.session.window_id, document_uuid=spec.document_uuid, before_fingerprint=bf,
                          idempotency_key=spec.key(), methods=spec.methods) as rec:
            journal_id = rec["id"]
            rec["dirty"] = spec.classification == ops.OP_NON_IDEMPOTENT_MUTATION
            try:
                raw = execute()
                state = ExecutionState.EXECUTED_RESPONSE_LOST   # ran; not yet proven
            except BridgeMutationTimeout as e:
                error = str(e)
                state = ExecutionState.EXECUTED_RESPONSE_LOST
            except BridgeWindowRotated as e:
                error = str(e)
                state = ExecutionState.GATEWAY_NOT_EXECUTED
                rec["dirty"] = False
            except BridgeUnreachable as e:
                error = str(e)
                state = ExecutionState.NOT_EXECUTED
                rec["dirty"] = False
            except DeskError as e:
                error = str(e)
                state = ExecutionState.UNKNOWN
            # readback and postcondition happen inside the journal window so END carries the verdict
            after = before
            verification: Optional[VerificationResult] = None
            if state in (ExecutionState.EXECUTED_RESPONSE_LOST, ExecutionState.UNKNOWN):
                try:
                    self._verify_identity(spec.document_uuid, "after mutation")
                    after = self._readback_until_settled(spec, readback, before)
                    verification = api_registry.verify(spec.verifier, before, after, spec.expected)
                    af = fingerprint(after)
                    if verification.passed:
                        state = ExecutionState.EXECUTED_VERIFIED
                        rec["dirty"] = False
                    elif af == bf:
                        state = ExecutionState.FALSE_SUCCESS if raw not in (None, False) and not error else state
                        if state == ExecutionState.FALSE_SUCCESS:
                            rec["dirty"] = False     # nothing changed: the board is clean
                    else:
                        state = ExecutionState.PARTIAL
                except IdentityUnverified as e:
                    error = error or str(e)
                    state = ExecutionState.WRONG_DOCUMENT if raw not in (None, False) else state
                except BridgeWindowRotated as e:
                    error = error or str(e)
                    state = ExecutionState.UNKNOWN
            rec["execution_state"] = state.value
            rec["after_fingerprint"] = fingerprint(after)
            rec["verified"] = bool(verification and verification.passed)
            if cap == api_registry.CapabilityStatus.UNSUPPORTED and state != ExecutionState.EXECUTED_VERIFIED:
                state = ExecutionState.UNSUPPORTED
        res = MutationResult(spec=spec, state=state, verification=verification, before=before, after=after,
                             before_fingerprint=bf, after_fingerprint=fingerprint(after), journal_id=journal_id, raw_return=raw,
                             error=error, duration_s=self.now() - t0, capability_status=cap.value)
        if not res.verified:
            res.failure = self._failure_for(res)
        return res

    def _failure_for(self, res: MutationResult) -> FailureRecord:
        cat = {
            ExecutionState.FALSE_SUCCESS: FailureCategory.API_FALSE_SUCCESS,
            ExecutionState.PARTIAL: FailureCategory.PARTIAL_MUTATION,
            ExecutionState.UNKNOWN: FailureCategory.UNKNOWN_MUTATION_OUTCOME,
            ExecutionState.EXECUTED_RESPONSE_LOST: FailureCategory.UNKNOWN_MUTATION_OUTCOME,
            ExecutionState.WRONG_DOCUMENT: FailureCategory.WRONG_PROJECT_CONTEXT,
            ExecutionState.GATEWAY_NOT_EXECUTED: FailureCategory.WINDOW_ID_ROTATED,
            ExecutionState.NOT_EXECUTED: FailureCategory.API_UNAVAILABLE,
            ExecutionState.UNSUPPORTED: FailureCategory.EXTERNAL_TOOL_UNSUPPORTED,
            ExecutionState.EXECUTED_STALE_READBACK: FailureCategory.API_FALSE_SUCCESS,
        }.get(res.state, FailureCategory.UNKNOWN_FAILURE)
        fr = FailureRecord.new(cat, "desk.reliability.mutation", res.spec.op,
                               res.error or f"{res.spec.op} on {res.spec.target}: {res.state.value}",
                               project_id=self.session.project_id, project_uuid=self.session.project_uuid,
                               session_id=self.session.session_id, window_id=self.session.window_id or "",
                               document_uuid=res.spec.document_uuid, operation_id=res.journal_id,
                               before_fingerprint=res.before_fingerprint, after_fingerprint=res.after_fingerprint,
                               execution_state=res.state, params={"verifier": res.spec.verifier, "expected": res.spec.expected,
                                                                   "methods": res.spec.methods, "capability": res.capability_status})
        fr.add_evidence("readback", res.spec.verifier, f"raw return {res.raw_return!r}; before {res.before_fingerprint}, "
                                                        f"after {res.after_fingerprint}")
        if res.verification:
            for c in res.verification.checks:
                fr.add_evidence("readback", c.name, f"expected {c.expected!r} actual {c.actual!r} ok={c.ok}")
        return fr

    # ---- unknown outcome ---------------------------------------------------------------------------------
    def reconcile(self, spec: MutationSpec, readback: Callable[[], Any], before: Any = None) -> MutationResult:
        """For a mutation whose outcome is unknown: read the document, compare with the postcondition and say
        whether it is complete (EXECUTED_VERIFIED), absent (NOT_EXECUTED: safe to run once) or partial.
        Never executes the mutation."""
        t0 = self.now()
        self._verify_identity(spec.document_uuid, "reconcile")
        after = readback()
        verification = api_registry.verify(spec.verifier, before, after, spec.expected)
        if verification.passed:
            state = ExecutionState.EXECUTED_VERIFIED
        elif before is not None and fingerprint(after) == fingerprint(before):
            state = ExecutionState.NOT_EXECUTED
        else:
            state = ExecutionState.PARTIAL
        res = MutationResult(spec, state, verification, before, after, fingerprint(before) if before is not None else "",
                             fingerprint(after), duration_s=self.now() - t0, capability_status="reconcile")
        if not res.verified:
            res.failure = self._failure_for(res)
        return res
