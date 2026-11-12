"""The self-healing supervisor: one lifecycle for every failure DESK observes.

    OBSERVE -> COLLECT EVIDENCE -> CLASSIFY -> IDENTIFY ROOT CAUSE -> ASSESS CONFIDENCE AND RISK -> SELECT RECOVERY PLAN
    -> CHECK PERMISSIONS AND SAFETY -> EXECUTE RECOVERY -> READ BACK -> INDEPENDENTLY VERIFY -> RECORD -> LEARN

`Supervisor.handle(exc_or_record, ...)` runs the lifecycle and returns the FailureRecord. A failure counts as healed
only when `record.healed` is True: an executed recovery followed by a passing independent verification. Every record
is appended to projects/<P>/state/reliability/failures.jsonl; every recovery action to recoveries.jsonl. `explain()`
answers the seven questions (what, where, why, evidence, safest recovery, what changed, did verification pass).

The supervisor owns no EasyEDA or engine code: handlers and verifiers are injected (desk.reliability.handlers in
production, fakes in tests). Zero external dependencies.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from desk.reliability import failure_classifier as FC
from desk.reliability import recovery_planner as RP
from desk.reliability import registry as KF
from desk.reliability import root_cause as RCA
from desk.reliability.evidence import EvidenceCollector
from desk.reliability.learning import IncidentWriter, RecoveryOutcomes
from desk.reliability.models import (Confidence as K, ExecutionState as X, FailureCategory as C, FailureRecord, Hypothesis,
                                     RecoveryPlan, VerificationResult)
from desk.reliability.recovery_executor import RecoveryExecutor
from desk.reliability.recovery_policy import RecoveryPolicy

ModelDiagnoser = Callable[[Dict[str, Any]], Any]      # packet -> model answer (dict or JSON text)


class Supervisor:
    def __init__(self, project_path: Optional[str] = None, session: Optional[Any] = None, collector: Optional[EvidenceCollector] = None,
                 policy: Optional[RecoveryPolicy] = None, executor: Optional[RecoveryExecutor] = None,
                 incidents: Optional[IncidentWriter] = None, outcomes: Optional[RecoveryOutcomes] = None,
                 builder_model: Optional[ModelDiagnoser] = None, evaluator_model: Optional[ModelDiagnoser] = None,
                 write_incidents: bool = False, now: Callable[[], float] = time.time):
        self.project_path = project_path
        self.session = session
        self.collector = collector or EvidenceCollector(project_path=project_path, session=session)
        self.policy = policy or RecoveryPolicy()
        self.executor = executor or RecoveryExecutor(journal=self._journal_recovery)
        if getattr(self.executor, "journal_default", False):
            self.executor.journal = self._journal_recovery      # an injected executor still journals to the project
        self.incidents = incidents
        self.outcomes = outcomes
        self.builder_model = builder_model
        self.evaluator_model = evaluator_model
        self.write_incidents = write_incidents
        self.now = now
        self.records: List[FailureRecord] = []

    # ---- persistence --------------------------------------------------------------------------------------
    def _state_dir(self) -> Optional[str]:
        if not self.project_path:
            return None
        d = os.path.join(self.project_path, "state", "reliability")
        os.makedirs(d, exist_ok=True)
        return d

    def persist(self, rec: FailureRecord) -> None:
        d = self._state_dir()
        if not d:
            return
        with open(os.path.join(d, "failures.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), default=str) + "\n")

    def _journal_recovery(self, entry: Dict[str, Any]) -> None:
        d = self._state_dir()
        if not d:
            return
        with open(os.path.join(d, "recoveries.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def load_records(self) -> List[FailureRecord]:
        d = self._state_dir()
        if not d or not os.path.exists(os.path.join(d, "failures.jsonl")):
            return []
        out = []
        with open(os.path.join(d, "failures.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(FailureRecord.from_dict(json.loads(line)))
                except Exception:
                    pass
        return out

    # ---- lifecycle ------------------------------------------------------------------------------------------
    def observe(self, failure: Any, module: str = "", operation: str = "", mutating: bool = False, **fields: Any) -> FailureRecord:
        """Turn an exception, an engine result or a record into a FailureRecord (OBSERVE + CLASSIFY)."""
        if isinstance(failure, FailureRecord):
            rec = failure
        elif isinstance(failure, BaseException):
            cat, state = FC.classify_exception(failure, mutating)
            ctx = dict(getattr(failure, "context", {}) or {})
            rec = FailureRecord.new(cat, module or type(failure).__module__, operation or type(failure).__name__, str(failure),
                                    execution_state=state, params={k: v for k, v in ctx.items() if isinstance(v, (str, int, float, bool, list, dict))},
                                    **fields)
        else:
            rec = FailureRecord.new(C.UNKNOWN_FAILURE, module, operation, str(failure), **fields)
        if self.session is not None:
            rec.project_uuid = rec.project_uuid or str(getattr(self.session, "project_uuid", "") or "")
            rec.window_id = rec.window_id or str(getattr(self.session, "window_id", "") or "")
            rec.session_id = rec.session_id or str(getattr(self.session, "session_id", "") or "")
            rec.project_id = rec.project_id or str(getattr(self.session, "project_id", "") or "")
        if not rec.project_id and self.project_path:
            rec.project_id = os.path.basename(self.project_path.rstrip("/\\"))
        return FC.classify_record(rec)

    def diagnose(self, rec: FailureRecord, facts: Dict[str, Any]) -> List[Hypothesis]:
        hyps = RCA.diagnose(rec, facts)
        rec.hypotheses = list(hyps)
        strong = [h for h in hyps if h.confidence in (K.CONFIRMED, K.STRONGLY_SUPPORTED)]
        if not strong and self.builder_model is not None:
            packet = RCA.diagnostic_packet(rec, facts, hyps)
            try:
                b_hyp, b_problems = RCA.validate_model_diagnosis(self.builder_model(packet), packet, source="model")
            except Exception as e:
                b_hyp, b_problems = None, [f"builder model failed: {e}"]
            rec.params["model_diagnosis_problems"] = b_problems
            if b_hyp is not None:
                rec.hypotheses.append(b_hyp)
            if self.evaluator_model is not None:
                try:
                    e_hyp, e_problems = RCA.validate_model_diagnosis(self.evaluator_model(packet), packet, source="evaluator")
                except Exception as e:
                    e_hyp, e_problems = None, [f"evaluator model failed: {e}"]
                if e_hyp is not None:
                    rec.hypotheses.append(e_hyp)
                rec.params["evaluation"] = RCA.evaluate(b_hyp, e_hyp, e_problems)
        rc = rec.root_cause
        rec.confidence = rc.confidence if rc else K.UNVERIFIED
        return rec.hypotheses

    def handle(self, failure: Any, module: str = "", operation: str = "", mutating: bool = False, approvals: Sequence[str] = (),
               ctx: Optional[Dict[str, Any]] = None, execute: bool = True, verifier: Optional[Callable[[FailureRecord, Dict[str, Any]], VerificationResult]] = None,
               **fields: Any) -> FailureRecord:
        rec = self.observe(failure, module, operation, mutating, **fields)
        facts = self.collector.collect(rec)
        facts.setdefault("mutating", mutating)
        self.diagnose(rec, facts)
        known = KF.match(rec)
        sig = facts.get("signature", "")
        failed_before = self.outcomes.failed_kinds(rec.signature) if self.outcomes else []
        plan = RP.plan(rec, facts, self.policy, known, sig, approvals)
        if failed_before:
            keep = [a for a in plan.actions if a.kind not in failed_before]
            plan.refused.extend(f"{a.kind}: failed before for this signature without new evidence" for a in plan.actions if a.kind in failed_before)
            plan.actions = keep
        rec.plan = plan
        rec.status = "RECOVERING" if plan.actions else "ESCALATED"
        if execute and plan.actions:
            context = dict(ctx or {}, record=rec, facts=facts, session=self.session, project_path=self.project_path)
            rec.outcomes = self.executor.execute(plan, rec, self.policy, context, sig, approvals)
            success = next((o for o in rec.outcomes if o.result == "SUCCESS"), None)
            if success is not None:
                rec.status = "RECOVERED"
                if verifier is not None:
                    try:
                        rec.verification = verifier(rec, context)
                    except BaseException as e:
                        rec.verification = VerificationResult().add("final_verifier", True, False, ok=False, note=str(e)[:200])
                else:
                    rec.verification = success.verification
                rec.status = "VERIFIED" if rec.verification and rec.verification.passed else "RECOVERED"
            elif any(o.result == "REFUSED" for o in rec.outcomes) and not any(o.executed for o in rec.outcomes):
                rec.status = "REFUSED" if not plan.requires_approval else "ESCALATED"
            else:
                rec.status = "FAILED" if any(o.executed for o in rec.outcomes) else "ESCALATED"
        self.records.append(rec)
        self.persist(rec)
        if self.outcomes is not None:
            self.outcomes.record(rec)
        if self.write_incidents and self.incidents is not None:
            try:
                self.incidents.write(rec)
            except OSError:
                pass
        return rec

    # ---- explanation ----------------------------------------------------------------------------------------
    @staticmethod
    def explain(rec: FailureRecord) -> str:
        rc = rec.root_cause
        ev = {e.id: e for e in rec.evidence}
        cited = [f"{ev[i].kind}:{ev[i].source} ({ev[i].summary[:60]})" for i in (rc.evidence_ids if rc else []) if i in ev]
        safest = rec.plan.actions[0] if rec.plan and rec.plan.actions else None
        executed = [o for o in rec.outcomes if o.executed]
        changed = "; ".join(f"{o.action_id}: {o.result}{' verified' if o.verified else ''}" for o in executed) or "nothing was changed"
        verified = "YES" if rec.verification and rec.verification.passed else "NO"
        lines = [
            f"What failed?        {rec.category.value}: {rec.message[:160]}",
            f"Where?              {rec.module}.{rec.operation} (project {rec.project_id or '?'}, document {rec.document_uuid or '?'}, window {rec.window_id or '?'})",
            f"Why?                {(rc.statement if rc else 'UNKNOWN')} [{(rc.confidence.value if rc else 'UNVERIFIED')}, {(rc.source if rc else '-')}]",
            f"Evidence?           {'; '.join(cited) or 'none cited'}",
            f"Safest recovery?    {(safest.kind + ' [' + safest.risk.value + ']: ' + safest.description) if safest else 'none; escalate'}",
            f"What changed?       {changed}",
            f"Verification?       {verified}" + (f" ({len(rec.verification.checks)} check(s))" if rec.verification else " (not performed)"),
            f"Healed?             {'YES' if rec.healed else 'NO'} (status {rec.status})",
        ]
        if rec.plan and rec.plan.refused:
            lines.append("Refused actions:    " + "; ".join(rec.plan.refused[:4]))
        return "\n".join(lines)
