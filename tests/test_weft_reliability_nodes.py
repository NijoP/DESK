"""DESK Weft reliability nodes (record -> diagnose -> plan -> checkpoint status) against a temporary project.
Mock-based: no Weft runtime, no bridge, no engine. The deferred Linux runtime validation is not claimed here."""
import json
import os
import shutil
import tempfile
import unittest

from desk.weft import contracts as C
from desk.weft import nodes


class ReliabilityNodes(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="desk_weft_rel_")
        self.proj = os.path.join(self.root, "UPS")
        os.makedirs(os.path.join(self.proj, "state", "route"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def call(self, node, **inputs):
        return nodes.execute(node, dict(projectId="UPS", runId="run-1", **inputs), projects_root=self.root, sleep=lambda s: None)

    def _write_route_evidence(self):
        with open(os.path.join(self.proj, "state", "route", "progress_chunks.json"), "w", encoding="utf-8") as f:
            json.dump({"chunks": [{"chunk": 1, "status": "TIMEOUT", "outcome": "CHUNK_TIMEOUT", "passes": 5, "final_unrouted": 70}],
                       "outcomes": ["CHUNK_TIMEOUT"], "best_unrouted": None,
                       "checkpoint": {"has_best": False, "best_unrouted": None, "engine_version": "v2.1.0"}}, f)

    def test_record_diagnose_plan(self):
        self._write_route_evidence()
        st, env = self.call("DeskFailureRecorder", category="ROUTER_ENGINE_TIMEOUT", module="desk.routing.orchestrator",
                            operation="execute_routing_chunked", message="chunk 1 TIMEOUT 420 s, 5 passes, no SES",
                            evidence={"items": [{"kind": "log", "source": "freerouting.log", "summary": "pass 1 3 min 4 s"}]})
        self.assertEqual(st, 200, env)
        ref = env["outputs"]["failureRef"]
        self.assertTrue(ref.startswith("FR-"))
        self.assertEqual(env["outputs"]["category"], "ROUTER_ENGINE_TIMEOUT")
        self.assertTrue(os.path.exists(os.path.join(self.proj, "state", "weft", "failures", ref + ".json")))

        st, env = self.call("DeskFailureDiagnoser", failureRef=ref)
        self.assertEqual(st, 200, env)
        self.assertEqual(env["outputs"]["rootCauseCategory"], "ROUTER_ENGINE_TIMEOUT")
        self.assertEqual(env["outputs"]["confidence"], "CONFIRMED")
        self.assertTrue(env["passed"])
        self.assertIn("KF-20261112-ROUTE-CHUNK", env["outputs"]["knownFailures"])

        st, env = self.call("DeskRecoveryPlanner", failureRef=ref)
        self.assertEqual(st, 200, env)
        self.assertIn("adaptive_chunk", env["outputs"]["actionKinds"])
        self.assertNotIn("resume_from_checkpoint", env["outputs"]["actionKinds"])     # there is no checkpoint
        self.assertTrue(env["outputs"]["requiresApproval"])                          # extend_budget is a Captain decision
        self.assertFalse(env["passed"])                                              # blocking: approval needed
        self.assertTrue(os.path.exists(os.path.join(self.proj, "state", "weft", "plans", ref + ".json")))

        st, env = self.call("DeskRoutingCheckpointStatus")
        self.assertEqual(st, 200, env)
        self.assertEqual(env["outputs"]["hasBest"], False)
        self.assertEqual(env["outputs"]["bestUnrouted"], -1)
        self.assertEqual(env["outputs"]["chunkOutcomes"], ["CHUNK_TIMEOUT"])
        self.assertEqual(env["outputs"]["engineVersion"], "v2.1.0")

    def test_bad_category_and_missing_record(self):
        st, env = self.call("DeskFailureRecorder", category="NOT_A_CATEGORY", module="m", operation="o", message="x")
        self.assertEqual((st, env["error"]["code"]), (400, "INVALID_INPUT"))
        st, env = self.call("DeskFailureDiagnoser", failureRef="FR-nope")
        self.assertEqual((st, env["error"]["code"]), (404, "RECORD_NOT_FOUND"))

    def test_executor_node_is_declared_unavailable_and_mutating(self):
        c = C.get("DeskRecoveryExecutor")
        self.assertEqual(c.status, "unavailable")
        self.assertTrue(c.mutation)
        st, env = self.call("DeskRecoveryExecutor")
        self.assertEqual(st, 501)
        self.assertEqual(env["error"]["code"], "NODE_UNAVAILABLE")

    def test_contracts_validate(self):
        for node in ("DeskFailureRecorder", "DeskFailureDiagnoser", "DeskRecoveryPlanner", "DeskRoutingCheckpointStatus"):
            self.assertEqual(C.get(node).problems(), [], node)


if __name__ == "__main__":
    unittest.main()
