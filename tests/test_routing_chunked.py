"""Chunked routing keeps the best SES and stops on plateau / completion / budget (mocked engine)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from desk.routing.orchestrator import RoutingEngineOrchestrator, EngineExecutionResult


def fake_result(ses_path, initial, final, write=True, seconds=10.0):
    if write:
        with open(ses_path, "w", encoding="utf-8") as f:
            # a minimal real SES: the checkpoint only adopts a file that parses and carries routed copper
            f.write(f"(session fake (unrouted {final})\n  (routes (resolution mil 10)\n    (network_out (net N1 (wire (path TopLayer 60 0 0 1000 0))))))\n")
    return EngineExecutionResult(success=True, status="SUCCESS", engine_name="Freerouting", engine_version="v2.5.0",
                                 engine_path="x.jar", command=["java"], duration_sec=seconds, returncode=0,
                                 passes_completed=6, initial_unrouted=initial, final_unrouted=final, ses_generated=write,
                                 ses_path=ses_path if write else None, ses_size_bytes=os.path.getsize(ses_path) if write else 0,
                                 pass_history=[{"pass": i, "unrouted": final} for i in range(1, 7)])


class TestChunked(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_chunk_")
        self.dsn = os.path.join(self.d, "b.dsn")
        open(self.dsn, "w").write("(pcb)")
        self.orch = RoutingEngineOrchestrator(tools_dir=self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _run(self, sequence, **kw):
        calls = []

        def fake_exec(**kwargs):
            idx = len(calls)
            calls.append(kwargs)
            initial, final, write = sequence[min(idx, len(sequence) - 1)]
            return fake_result(kwargs["ses_path"], initial, final, write)

        with mock.patch.object(self.orch, "execute_routing", side_effect=fake_exec):
            res = self.orch.execute_routing_chunked(self.dsn, os.path.join(self.d, "out.ses"), self.d, **kw)
        return res, calls

    def test_keeps_best_ses_and_continues_from_it(self):
        res, calls = self._run([(42, 11, True), (11, 7, True), (7, 9, True), (7, 8, True)], chunk_passes=6, max_chunks=8, plateau_chunks=2)
        self.assertEqual(res.status, "PLATEAU_PARTIAL")
        self.assertEqual(res.best_unrouted, 7)
        self.assertTrue(res.ses_generated)
        self.assertIn("(unrouted 7)", open(res.ses_path).read())
        self.assertEqual(len(calls), 4)                       # chunks 3 and 4 did not improve -> stop
        self.assertIsNone(calls[0]["input_ses"])             # first chunk from scratch
        self.assertTrue(calls[1]["input_ses"].endswith("chunk_best.ses"))
        self.assertGreaterEqual(calls[0]["stagnation_patience"], 99)   # chunks are never terminated early

    def test_stops_at_zero_unrouted(self):
        res, calls = self._run([(20, 5, True), (5, 0, True)], chunk_passes=6)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.best_unrouted, 0)
        self.assertEqual(len(calls), 2)

    def test_chunk_without_ses_is_a_tool_defect_and_stops(self):
        res, calls = self._run([(20, 9, False)], chunk_passes=6)
        self.assertFalse(res.success)
        self.assertEqual(len(calls), 1)
        self.assertFalse(res.ses_generated)

    def test_budget_bounds_the_number_of_chunks(self):
        res, calls = self._run([(40, 30, True), (30, 20, True), (20, 10, True), (10, 5, True)], chunk_passes=6, budget_sec=25.0)
        self.assertLessEqual(len(calls), 1)   # 25 s budget, each chunk takes 10 s and the remaining check needs >= 30 s


if __name__ == "__main__":
    unittest.main()
