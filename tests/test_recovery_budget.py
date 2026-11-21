"""B1: the recovery attempt budget is persisted in state/reliability/recoveries.jsonl and survives the process.

Two separate Supervisor instances on one project stand in for two processes (study report section 4.4 bug 8).
"""
import json
import os
import shutil
import tempfile
import unittest

from desk.reliability.models import FailureCategory as C, FailureRecord, VerificationResult
from desk.reliability.recovery_executor import RecoveryExecutor
from desk.reliability.recovery_policy import RecoveryPolicy
from desk.reliability.supervisor import Supervisor


class _NoEvidence:
    """Collector stand-in: a fixed evidence signature, so only the persisted budget decides."""
    def __init__(self, sig="EVSIG-1"):
        self.sig = sig

    def collect(self, rec):
        return {"signature": self.sig}


def _fail(action, ctx):
    raise RuntimeError("still broken")


def _verify_ok(action, ctx):
    return VerificationResult().add("readback", True, True)


class PersistedBudget(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_budget_")
        self.proj = os.path.join(self.d, "projects", "P")
        os.makedirs(self.proj)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def sup(self, handlers, verifiers=None, sig="EVSIG-1", max_attempts=2):
        return Supervisor(self.proj, collector=_NoEvidence(sig), policy=RecoveryPolicy(max_attempts=max_attempts),
                          executor=RecoveryExecutor(handlers, verifiers or {}, journal=None))

    def record(self, fid="FR-fixed"):
        rec = FailureRecord.new(C.ROUTER_ENGINE_TIMEOUT, "desk.routing", "chunk", "chunk 1 TIMEOUT no SES")
        rec.failure_id = fid
        return rec

    def journal(self):
        with open(os.path.join(self.proj, "state", "reliability", "recoveries.jsonl"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_third_attempt_for_same_failure_refused_across_instances(self):
        handlers = {"adaptive_chunk": _fail}
        # each Supervisor is a new process: a fresh policy object on the same project; the evidence changes each time
        r1 = self.sup(handlers, sig="EVSIG-1").handle(self.record())
        r2 = self.sup(handlers, sig="EVSIG-2").handle(self.record())
        self.assertEqual([o.result for o in r1.outcomes + r2.outcomes if o.executed], ["FAILED", "FAILED"])
        r3 = self.sup(handlers, sig="EVSIG-3").handle(self.record())
        self.assertFalse(any(o.executed for o in r3.outcomes))
        self.assertTrue(any("attempts exhausted" in n for n in r3.plan.refused), r3.plan.refused)
        self.assertTrue(all("evidence_signature" in r and "failure_signature" in r for r in self.journal()))

    def test_same_action_and_signature_refused_across_instances(self):
        handlers = {"adaptive_chunk": _fail}
        r1 = self.sup(handlers, max_attempts=5).handle(self.record())
        self.assertEqual([o.result for o in r1.outcomes if o.executed], ["FAILED"])
        r2 = self.sup(handlers, max_attempts=5).handle(self.record())
        self.assertFalse(any(o.executed for o in r2.outcomes))
        notes = [o.note for o in r2.outcomes] + list(r2.plan.refused)
        self.assertTrue(any("already tried" in n for n in notes), notes)

    def test_new_failure_id_with_same_signature_inherits_budget(self):
        handlers = {"adaptive_chunk": _fail}
        self.sup(handlers, sig="EVSIG-1").handle(self.record("FR-a"))
        self.sup(handlers, sig="EVSIG-2").handle(self.record("FR-b"))
        r3 = self.sup(handlers, sig="EVSIG-3").handle(self.record("FR-c"))
        self.assertFalse(any(o.executed for o in r3.outcomes))
        self.assertTrue(any("attempts exhausted" in n for n in r3.plan.refused), r3.plan.refused)

    def test_verified_recovery_resets_the_signature_budget(self):
        ok = {"adaptive_chunk": lambda a, c: "ok"}
        r1 = self.sup(ok, {"adaptive_chunk": _verify_ok}, max_attempts=1).handle(self.record("FR-a"))
        self.assertTrue(r1.healed)
        r2 = self.sup(ok, {"adaptive_chunk": _verify_ok}, sig="EVSIG-2", max_attempts=1).handle(self.record("FR-b"))
        self.assertTrue(r2.healed)                  # healed earlier: the recurrence gets a fresh budget

    def test_rebuild_reads_legacy_entries_without_signatures(self):
        p = RecoveryPolicy(max_attempts=2).rebuild([
            {"failure_id": "FR-x", "action": {"kind": "retry_read"}, "outcome": {"executed": True, "result": "FAILED"}},
            {"failure_id": "FR-x", "action": {"kind": "retry_read"}, "outcome": {"executed": False, "result": "REFUSED"}},
            "garbage",
        ])
        self.assertEqual(p.attempts, {"FR-x": 1})
        self.assertEqual(p.remaining("FR-x"), 1)

    def test_construction_does_not_create_state(self):
        Supervisor(self.proj, policy=RecoveryPolicy())
        self.assertFalse(os.path.exists(os.path.join(self.proj, "state")))


if __name__ == "__main__":
    unittest.main()
