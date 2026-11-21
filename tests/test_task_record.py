"""B2: the engineering task record (desk/tasks.py), its emission from ops.write_op, and `desk.py task show`.

The verify side calls `tasks.record_verify` directly: the one-line call from tools/verify.py is a follow-up.
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

from desk import ops
from desk import tasks as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")


def _desk_main():
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    spec = importlib.util.spec_from_file_location("desk_tool_task_test", os.path.join(TOOLS, "desk.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


class TaskRecord(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_tasks_")
        self.proj = os.path.join(self.d, "FIX")
        os.makedirs(os.path.join(self.proj, "blocks"))
        with open(os.path.join(self.proj, "blocks", "03_BUCK.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "03_BUCK", "parts": []}, f)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_fixture_build_and_verify_yield_one_complete_task(self):
        with ops.write_op(self.proj, "build", "03_BUCK"):
            pass
        rec = T.record_verify(self.proj, "03_BUCK", ok=True, spec_hash="abc123", report="VERIFIED 12 nets")
        store = T.TaskStore(self.proj)
        self.assertEqual(store.ids(), ["T-schematic_block-03_BUCK"])
        T.validate(rec)
        for k in ("inputs", "expected_outputs", "constraints", "execution_status", "verification_status", "failure",
                  "evidence", "provenance"):
            self.assertIn(k, rec)
        self.assertEqual(rec["inputs"][0]["ref"], "blocks/03_BUCK.json")
        self.assertEqual(rec["expected_outputs"][0]["acceptance"], "VERIFIED")
        self.assertEqual(rec["execution_status"], "SUCCEEDED")
        self.assertEqual(rec["verification_status"], "PASS")
        self.assertIsNone(rec["failure"])
        self.assertEqual(rec["attempts"]["count"], 1)
        self.assertEqual({e["kind"] for e in rec["evidence"]}, {"ops_journal", "gate_report"})
        self.assertTrue(rec["provenance"]["actor"].startswith("engine:"))
        self.assertEqual(T.freshness(rec, "abc123"), "PASS")
        self.assertEqual(T.freshness(rec, "changed"), "STALE")

    def test_failed_op_and_failed_verify_carry_a_failure_class(self):
        with self.assertRaises(RuntimeError):
            with ops.write_op(self.proj, "build", "03_BUCK") as r:
                r["dirty"] = True
                raise RuntimeError("bridge timeout")
        rec = T.TaskStore(self.proj).get("T-schematic_block-03_BUCK")
        self.assertEqual(rec["execution_status"], "FAILED")
        self.assertEqual(rec["failure"]["category"], "PARTIAL_MUTATION")
        self.assertEqual(rec["failure"]["layer"], "OPERATIONAL")
        self.assertEqual(len(rec["attempts"]["signatures"]), 1)
        T.validate(rec)
        rec = T.record_verify(self.proj, "03_BUCK", ok=False, report="2 single-pin nets")
        self.assertEqual(rec["verification_status"], "FAIL")
        self.assertEqual(rec["failure"]["layer"], "ENGINEERING")

    def test_new_execution_makes_verification_stale(self):
        T.record_verify(self.proj, "03_BUCK", ok=True, spec_hash="h1")
        with ops.write_op(self.proj, "build", "03_BUCK"):
            pass
        self.assertEqual(T.TaskStore(self.proj).get("T-schematic_block-03_BUCK")["verification_status"], "STALE")

    def test_schema_rejects_missing_fields(self):
        good = T.fold([{"ev": "created", "ts": "2026-01-01T00:00:00", "task_id": "T-routing-pcb", "stage": "routing",
                        "inputs": [{"kind": "artifact", "ref": "pcb"}],
                        "expected_outputs": [{"kind": "gate", "ref": "routing:pcb", "acceptance": "connectivity FULL"}],
                        "provenance": {"actor": "engine:test", "ts": "2026-01-01T00:00:00"}}], "T-routing-pcb")
        T.validate(good)
        for field in ("inputs", "expected_outputs", "constraints", "execution_status", "verification_status", "failure",
                      "evidence", "provenance"):
            bad = dict(good)
            del bad[field]
            with self.assertRaises(T.TaskSchemaError, msg=field):
                T.validate(bad)
        with self.assertRaises(T.TaskSchemaError):
            T.validate(dict(good, inputs=[]))
        with self.assertRaises(T.TaskSchemaError):
            T.validate(dict(good, execution_status="FAILED", failure=None))
        with self.assertRaises(T.TaskSchemaError):
            T.validate(dict(good, failure={"category": "NOT_A_CATEGORY", "layer": "ENGINEERING"}))
        with self.assertRaises(T.TaskSchemaError):
            T.TaskStore(self.proj).create("nonsense_stage", "x", [{"kind": "spec", "ref": "a"}],
                                          [{"kind": "gate", "ref": "g", "acceptance": "PASS"}])
        self.assertEqual(T.TaskStore(self.proj).ids(), [])           # a malformed task never lands

    def test_fold_of_1k_events_under_10ms(self):
        events = [{"ev": "created", "ts": "t", "task_id": "T-routing-pcb", "stage": "routing",
                   "inputs": [{"kind": "artifact", "ref": "pcb"}],
                   "expected_outputs": [{"kind": "gate", "ref": "r", "acceptance": "FULL"}], "provenance": {"actor": "a", "ts": "t"}}]
        for i in range(999):
            events.append({"ev": ("started", "failed", "succeeded")[i % 3], "ts": "t", "op_id": str(i),
                           "failure": {"category": "ROUTER_STAGNATION", "layer": "ENGINEERING", "signature": f"s{i}"},
                           "evidence": [{"kind": "tool_output", "ref": f"r{i}"}]})
        best = min(self._time(events) for _ in range(5))
        sys.stderr.write(f"\n[measured] tasks.fold of 1000 events: best of 5 = {best * 1000:.2f} ms\n")
        self.assertLess(best, 0.010)

    @staticmethod
    def _time(events):
        t0 = time.perf_counter()
        T.fold(events, "T-routing-pcb")
        return time.perf_counter() - t0

    def test_desk_py_task_show_prints_the_six_fields(self):
        with ops.write_op(self.proj, "build", "03_BUCK"):
            pass
        T.record_verify(self.proj, "03_BUCK", ok=False, report="1 single-pin net")
        main = _desk_main()
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["task", "show", self.proj, "T-schematic_block-03_BUCK"]), 0)
        out = buf.getvalue()
        for needle in ("inputs:", "blocks/03_BUCK.json", "expected outputs:", "VERIFIED", "constraints:",
                       "execution status:    SUCCEEDED", "verification status: FAIL",
                       "failure class:       CONNECTIVITY_VERIFICATION_FAILURE / ENGINEERING", "provenance:"):
            self.assertIn(needle, out)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["task", "list", self.proj]), 0)
        self.assertIn("T-schematic_block-03_BUCK", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
