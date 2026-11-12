"""API failure intelligence: the mutation contract, the capability registry, retries and breakers.

Simulates HTTP 500, connection refused, timeout before and after execution, true-without-mutation (importChanges),
false-after-partial-mutation (delete that leaves survivors), stale readback, wrong document, window rotation during
a mutation and an unsupported method. No EasyEDA.
"""
import os
import shutil
import tempfile
import unittest

from desk import ops
from desk.errors import (BridgeMutationTimeout, BridgeUnreachable, BridgeScriptError, BridgeWindowRotated, IdentityUnverified,
                         DeskError, CircuitOpen)
from desk.reliability import api_registry as AR
from desk.reliability.circuit_breaker import CircuitBreaker, BreakerRegistry
from desk.reliability.models import ExecutionState as X, FailureCategory as C
from desk.reliability.mutation import MutationContract, MutationSpec
from desk.reliability.project_isolation import ProjectSession, SessionResolver, PROJECT_INFO_JS, ACTIVE_DOC_JS
from desk.reliability.retry_policy import RetryPolicy

PU, PCB = "proj-uuid", "pcb-uuid"


class Gateway:
    def __init__(self, active_doc=PCB):
        self.active_doc = active_doc
        self.connected = True

    def windows(self):
        return [{"windowId": "w1"}] if self.connected else []

    def execute(self, window_id, code, timeout=5.0):
        if not self.connected or window_id != "w1":
            return {"success": False, "error": "EDA window is no longer connected"}
        if code == PROJECT_INFO_JS:
            return {"success": True, "result": {"project_uuid": PU, "project_name": "P", "document_uuid": self.active_doc}}
        if code == ACTIVE_DOC_JS:
            return {"success": True, "result": self.active_doc}
        return {"success": True, "result": True}


class Board:
    """A PCB with a component count and track ids; the readbacks the contract compares."""
    def __init__(self):
        self.components = 0
        self.tracks = {"t1", "t2", "t3"}


class ContractCase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_mc_")
        self.proj = os.path.join(self.d, "P")
        os.makedirs(self.proj)
        self.gw = Gateway()
        self.session = ProjectSession("P", self.proj, project_uuid=PU, pcb_uuid=PCB)
        self.resolver = SessionResolver(self.gw)
        self.resolver.resolve(self.session)
        self.sleeps = []
        self.mc = MutationContract(self.proj, self.session, self.resolver, sleep=self.sleeps.append)
        self.board = Board()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def journal(self):
        return ops.journal(self.proj)

    # ---- F: success returned, nothing changed ------------------------------------------------------------------
    def test_import_changes_true_without_components_is_false_success(self):
        spec = MutationSpec("pcb_import_changes", PCB, PCB, "count_increased", {"min_count": 123},
                            methods=["eda.pcb_Document.importChanges"], readback_attempts=2)
        res = self.mc.run(spec, execute=lambda: True, readback=lambda: self.board.components)
        self.assertEqual(res.state, X.FALSE_SUCCESS)
        self.assertFalse(res.verified)
        self.assertIs(res.raw_return, True)
        self.assertEqual(res.capability_status, "DIALOG")
        self.assertEqual(res.failure.category, C.API_FALSE_SUCCESS)
        self.assertEqual(len(self.sleeps), 2)                           # re-read twice before declaring it
        end = [r for r in self.journal() if r["phase"] == "end"][0]
        self.assertEqual(end["execution_state"], "FALSE_SUCCESS")
        self.assertFalse(end["verified"])
        begin = [r for r in self.journal() if r["phase"] == "begin"][0]
        self.assertEqual((begin["window_id"], begin["document_uuid"]), ("w1", PCB))
        self.assertTrue(begin["idempotency_key"])

    def test_human_apply_then_readback_verifies(self):
        spec = MutationSpec("pcb_import_changes", PCB, PCB, "count_increased", {"min_count": 123}, readback_attempts=3)
        reads = [0, 0, 123]
        res = self.mc.run(spec, execute=lambda: True, readback=lambda: reads.pop(0) if len(reads) > 1 else 123)
        self.assertEqual(res.state, X.EXECUTED_VERIFIED)              # a stale readback followed by the change
        self.assertTrue(res.verified)
        self.assertIsNone(res.failure)

    # ---- D: partial -----------------------------------------------------------------------------------------------
    def test_delete_true_with_survivors_is_partial(self):
        spec = MutationSpec("route_ripup", "PCB", PCB, "ids_absent", {"ids": ["t1", "t2", "t3"]}, methods=["eda.pcb_PrimitiveLine.delete"])

        def execute():
            self.board.tracks -= {"t1", "t2"}        # t3 survives although delete() says true
            return True
        res = self.mc.run(spec, execute=execute, readback=lambda: sorted(self.board.tracks))
        self.assertEqual(res.state, X.PARTIAL)
        self.assertEqual(res.failure.category, C.PARTIAL_MUTATION)
        self.assertEqual(res.verification.checks[0].actual, ["t3"])
        self.assertTrue([r for r in self.journal() if r["phase"] == "end"][0]["execution_state"] == "PARTIAL")

    # ---- C: timeout after execution ------------------------------------------------------------------------------
    def test_timeout_after_execution_is_verified_by_readback_not_retried(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 2, "document_uuid": PCB})
        calls = []

        def execute():
            calls.append(1)
            self.board.tracks = {"a", "b", "c"}
            raise BridgeMutationTimeout("gateway cap")
        res = self.mc.run(spec, execute=execute, readback=lambda: {"tracks": len(self.board.tracks), "vias": 0, "document_uuid": PCB})
        self.assertEqual(res.state, X.EXECUTED_VERIFIED)
        self.assertTrue(res.verified)
        self.assertEqual(len(calls), 1)
        self.assertIn("gateway cap", res.error)
        end = [r for r in self.journal() if r["phase"] == "end"][0]
        self.assertTrue(end["verified"])

    def test_timeout_before_execution_stays_unknown_and_dirty(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 9}, readback_attempts=1)

        def execute():
            raise BridgeMutationTimeout("lost")
        res = self.mc.run(spec, execute=execute, readback=lambda: {"tracks": 3, "vias": 0})
        self.assertEqual(res.state, X.EXECUTED_RESPONSE_LOST)
        self.assertEqual(res.failure.category, C.UNKNOWN_MUTATION_OUTCOME)
        fail = [r for r in self.journal() if r["phase"] == "end"][0]
        self.assertEqual(fail["execution_state"], "EXECUTED_RESPONSE_LOST")
        self.assertEqual(ops.pending(self.proj), [])                     # END was written: the record is complete, not dirty
        # the supervisor sees the state and must reconcile, never repeat:
        rec = self.mc.reconcile(spec, readback=lambda: {"tracks": 3, "vias": 0}, before={"tracks": 3, "vias": 0})
        self.assertEqual(rec.state, X.NOT_EXECUTED)                      # unchanged: safe to run once

    # ---- A / B ----------------------------------------------------------------------------------------------------
    def test_connection_refused_is_not_executed_and_clean(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 1})

        def execute():
            raise BridgeUnreachable("refused")
        res = self.mc.run(spec, execute=execute, readback=lambda: {"tracks": 0})
        self.assertEqual(res.state, X.NOT_EXECUTED)
        self.assertEqual(res.failure.category, C.API_UNAVAILABLE)
        self.assertEqual(ops.pending(self.proj), [])

    def test_http_500_is_unknown_outcome(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 1}, readback_attempts=0)

        def execute():
            raise BridgeScriptError("Bridge HTTP Error 500: a is not iterable", http_status=500)
        res = self.mc.run(spec, execute=execute, readback=lambda: {"tracks": 0})
        self.assertEqual(res.state, X.UNKNOWN)
        self.assertEqual(res.failure.category, C.UNKNOWN_MUTATION_OUTCOME)

    def test_window_rotation_during_mutation_is_gateway_not_executed(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 1})

        def execute():
            raise BridgeWindowRotated("no longer connected")
        res = self.mc.run(spec, execute=execute, readback=lambda: {"tracks": 0})
        self.assertEqual(res.state, X.GATEWAY_NOT_EXECUTED)
        self.assertEqual(res.failure.category, C.WINDOW_ID_ROTATED)
        self.assertEqual(ops.pending(self.proj), [])

    # ---- H: wrong document ----------------------------------------------------------------------------------------
    def test_wrong_active_document_refuses_before_executing(self):
        self.gw.active_doc = "schematic-uuid"
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 1})
        ran = []
        with self.assertRaises(IdentityUnverified):
            self.mc.run(spec, execute=lambda: ran.append(1), readback=lambda: {"tracks": 0})
        self.assertEqual(ran, [])
        self.assertEqual(self.journal(), [])                              # not even a BEGIN

    def test_document_switched_after_execution_is_wrong_document(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 1}, readback_attempts=0)

        def execute():
            self.gw.active_doc = "schematic-uuid"                         # the user clicked another tab
            return True
        res = self.mc.run(spec, execute=execute, readback=lambda: {"tracks": 0})
        self.assertEqual(res.state, X.WRONG_DOCUMENT)
        self.assertEqual(res.failure.category, C.WRONG_PROJECT_CONTEXT)

    # ---- G: unsupported -------------------------------------------------------------------------------------------
    def test_unsupported_method_is_marked(self):
        spec = MutationSpec("rename", "PCB", PCB, "value_equals", "newname", methods=["eda.dmt_Pcb.modifyPcbName"], readback_attempts=0)
        res = self.mc.run(spec, execute=lambda: True, readback=lambda: "oldname")
        self.assertEqual(res.state, X.UNSUPPORTED)
        self.assertEqual(res.failure.category, C.EXTERNAL_TOOL_UNSUPPORTED)

    def test_precondition_refuses(self):
        spec = MutationSpec("route_import", "PCB", PCB, "copper_counts", {"min_tracks": 1})
        with self.assertRaises(DeskError):
            self.mc.run(spec, execute=lambda: True, readback=lambda: {"tracks": 5}, precondition=lambda b: "board already routed")


class Registry(unittest.TestCase):
    def test_dialog_and_unknown(self):
        self.assertEqual(AR.capability("pcb_Document.importChanges").status, AR.CapabilityStatus.DIALOG)
        self.assertEqual(AR.capability("eda.pcb_Foo.bar").status, AR.CapabilityStatus.UNKNOWN)
        self.assertEqual(AR.capability("dmt_Pcb.modifyPcbName").status, AR.CapabilityStatus.UNSUPPORTED)
        self.assertEqual(AR.verification_contract("pcb_Document.importAutoRouteSesFile"), "copper_counts")

    def test_every_write_has_a_verifier_and_evidence(self):
        for c in AR.CAPABILITIES.values():
            if c.rw in ("write", "dialog"):
                if c.verifier:
                    self.assertIn(c.verifier, AR.VERIFIERS, c.method)
                else:   # a write without a readable postcondition must say so instead of pretending
                    self.assertTrue(any("no readback" in l for l in c.limitations), c.method)
            if c.status != AR.CapabilityStatus.UNKNOWN:
                self.assertTrue(c.evidence, c.method)

    def test_riskiest_status_in_a_script(self):
        js = "await eda.sch_Document.save(); return await eda.pcb_Document.importChanges();"
        self.assertEqual(AR.riskiest_status(js), AR.CapabilityStatus.DIALOG)
        self.assertEqual(AR.methods_in(js), ["eda.pcb_Document.importChanges", "eda.sch_Document.save"])

    def test_unknown_contract_fails_closed(self):
        self.assertFalse(AR.verify("no_such_contract", None, None, None).passed)

    def test_pin_net_map_contract(self):
        v = AR.verify("pin_net_map", None, {"components": 3, "pad_nets": {"R1.1": "GND", "R1.2": "VCC"}},
                      {"components": 3, "pad_nets": {"R1.1": "GND", "R1.2": "3V3"}})
        self.assertFalse(v.passed)
        self.assertEqual(v.checks[1].actual, ["R1.2"])


class Retries(unittest.TestCase):
    def test_non_idempotent_unknown_is_never_retried(self):
        p = RetryPolicy(max_attempts=3)
        self.assertTrue(p.should_retry(1, C.API_TIMEOUT, X.NOT_EXECUTED, idempotent=False))
        self.assertFalse(p.should_retry(1, C.API_TIMEOUT, X.UNKNOWN, idempotent=False))
        self.assertFalse(p.should_retry(1, C.API_TIMEOUT, X.EXECUTED_RESPONSE_LOST, idempotent=False))
        self.assertTrue(p.should_retry(1, C.API_TIMEOUT, X.EXECUTED_RESPONSE_LOST, idempotent=True))
        self.assertFalse(p.should_retry(3, C.API_TIMEOUT, X.NOT_EXECUTED, idempotent=True))
        self.assertFalse(p.should_retry(1, C.API_FALSE_SUCCESS, X.NOT_EXECUTED, idempotent=True))

    def test_backoff_is_bounded_with_jitter(self):
        p = RetryPolicy(max_attempts=5, base_delay_s=1.0, max_delay_s=4.0, jitter=0.0, rng=lambda: 0.5)
        self.assertEqual(list(p.delays()), [1.0, 2.0, 4.0, 4.0])
        p2 = RetryPolicy(max_attempts=3, base_delay_s=1.0, jitter=0.5, rng=lambda: 1.0)
        self.assertEqual(list(p2.delays()), [1.5, 3.0])


class Breakers(unittest.TestCase):
    def test_opens_after_threshold_and_half_opens_after_timeout(self):
        t = [0.0]
        b = CircuitBreaker("gateway:1", failure_threshold=2, recovery_timeout_s=10.0, now=lambda: t[0])
        b.record_failure("refused")
        self.assertTrue(b.allow())
        b.record_failure("refused")
        self.assertFalse(b.allow())
        with self.assertRaises(CircuitOpen):
            b.check()
        t[0] = 11.0
        self.assertTrue(b.allow())
        self.assertEqual(b.state, "HALF_OPEN")
        b.record_failure("still down")
        self.assertEqual(b.state, "OPEN")
        t[0] = 30.0
        b.allow()
        b.record_success()
        self.assertEqual(b.state, "CLOSED")

    def test_registry_is_keyed(self):
        BreakerRegistry.reset()
        a, b = BreakerRegistry.get("engine:x"), BreakerRegistry.get("gateway:49620")
        a.record_failure(); a.record_failure(); a.record_failure()
        self.assertFalse(a.allow())
        self.assertTrue(b.allow())                                        # a dead engine never blocks the bridge
        BreakerRegistry.reset()


if __name__ == "__main__":
    unittest.main()
