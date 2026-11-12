"""Recovery execution: policy-gated, bounded, journalled, independently verified.

Handlers are injected per action kind (`handlers[kind](action, ctx) -> Any`). After a handler returns, the verifier for
the action (`verifiers[kind](action, ctx) -> VerificationResult`, or the plan's generic verifier) reads the live state;
only a passing verification makes the outcome SUCCESS. A handler that raises yields FAILED with the error, never an
exception out of the executor. Every executed action is recorded through `RecoveryPolicy.record_attempt` so the same
action is not repeated on unchanged evidence. Zero external dependencies.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from desk.reliability.models import (FailureRecord, RecoveryAction, RecoveryOutcome, RecoveryPlan, RiskClass, VerificationResult)
from desk.reliability.recovery_policy import RecoveryPolicy

Handler = Callable[[RecoveryAction, Dict[str, Any]], Any]
Verifier = Callable[[RecoveryAction, Dict[str, Any]], VerificationResult]


class RecoveryExecutor:
    def __init__(self, handlers: Optional[Dict[str, Handler]] = None, verifiers: Optional[Dict[str, Verifier]] = None,
                 default_verifier: Optional[Verifier] = None, journal: Optional[Callable[[Dict[str, Any]], None]] = None,
                 now: Callable[[], float] = time.time):
        self.handlers = dict(handlers or {})
        self.verifiers = dict(verifiers or {})
        self.default_verifier = default_verifier
        self.journal_default = journal is None
        self.journal = journal or (lambda rec: None)
        self.now = now

    def execute(self, plan: RecoveryPlan, rec: FailureRecord, policy: RecoveryPolicy, ctx: Dict[str, Any],
                evidence_signature: str, approvals: Sequence[str] = (), stop_on_success: bool = True) -> List[RecoveryOutcome]:
        outcomes: List[RecoveryOutcome] = []
        for action in plan.actions:
            decision = policy.decide(rec.failure_id, action, evidence_signature, approvals)
            if not decision.allowed:
                o = RecoveryOutcome(action.id, executed=False, result="REFUSED", note=decision.reason)
                outcomes.append(o)
                self.journal({"failure_id": rec.failure_id, "action": action.to_dict(), "outcome": o.to_dict(), "ts": self.now()})
                continue
            handler = self.handlers.get(action.kind)
            if handler is None:
                o = RecoveryOutcome(action.id, executed=False, result="SKIPPED", note=f"no handler for {action.kind}; proposal only")
                outcomes.append(o)
                self.journal({"failure_id": rec.failure_id, "action": action.to_dict(), "outcome": o.to_dict(), "ts": self.now()})
                continue
            policy.record_attempt(rec.failure_id, action, evidence_signature)
            approval_id = next((a for a in approvals if a), None) if action.risk == RiskClass.APPROVAL else None
            try:
                result = handler(action, ctx)
            except BaseException as e:   # DeskError subclasses SystemExit: catch everything, report, continue
                o = RecoveryOutcome(action.id, executed=True, result="FAILED", note=f"{type(e).__name__}: {e}"[:300], approval_id=approval_id)
                outcomes.append(o)
                self.journal({"failure_id": rec.failure_id, "action": action.to_dict(), "outcome": o.to_dict(), "ts": self.now()})
                continue
            verifier = self.verifiers.get(action.kind) or self.default_verifier
            verification: Optional[VerificationResult] = None
            if verifier is not None:
                try:
                    verification = verifier(action, ctx)
                except BaseException as e:
                    verification = VerificationResult().add("verifier_ran", True, False, ok=False, note=f"{type(e).__name__}: {e}"[:200])
            else:
                verification = VerificationResult().add("independent_verification", "performed", "no verifier", ok=False,
                                                        note="no verifier registered: an unverified recovery is not a success")
            o = RecoveryOutcome(action.id, executed=True, result="SUCCESS" if verification.passed else "FAILED", verification=verification,
                                note=str(result)[:200] if result is not None else "", approval_id=approval_id,
                                journal_id=str(ctx.get("journal_id") or "") or None)
            outcomes.append(o)
            self.journal({"failure_id": rec.failure_id, "action": action.to_dict(), "outcome": o.to_dict(), "ts": self.now()})
            if o.result == "SUCCESS" and stop_on_success:
                break
        return outcomes
