"""T-17: durable approval records, MutationPolicy in write_op, registry side_effect in the journal."""
import os
import tempfile
import unittest
from unittest import mock

from desk import ops
from desk.errors import ApprovalRequired


class ApprovalRecords(unittest.TestCase):
    def setUp(self):
        self.p = tempfile.mkdtemp()

    def test_record_approval_is_journalled_and_linked_from_begin(self):
        aid = ops.record_approval(self.p, "build", "02_PWR", granted_by="CAPTAIN", how="cli tools/build.py", reason="gate B passed")
        with ops.write_op(self.p, "build", "02_PWR", approval=aid):
            pass
        j = ops.journal(self.p)
        appr = [r for r in j if r["phase"] == "approval"]
        begin = [r for r in j if r["phase"] == "begin"][0]
        self.assertEqual(len(appr), 1)
        self.assertEqual(appr[0]["id"], aid)
        self.assertEqual(appr[0]["granted_by"], "CAPTAIN")
        self.assertEqual(begin["approval"], aid)
        self.assertEqual(begin["policy"], "record")
        self.assertEqual(ops.approvals(self.p)[0]["reason"], "gate B passed")

    def test_cli_approval_records_the_invocation(self):
        aid = ops.cli_approval(self.p, "clear", "03_MCU", argv=["tools/clear_block.py", "projects/X", "03_MCU"])
        a = ops.approvals(self.p)[0]
        self.assertEqual(a["id"], aid)
        self.assertEqual(a["granted_by"], "operator")
        self.assertTrue(a["how"].startswith("cli clear_block.py projects/X 03_MCU"))

    def test_record_mode_journals_missing_approval_but_does_not_refuse(self):
        with mock.patch.dict(os.environ, {"DESK_MUTATION_POLICY": "record"}):
            with ops.write_op(self.p, "build", "A"):
                pass
        begin = [r for r in ops.journal(self.p) if r["phase"] == "begin"][0]
        self.assertIsNone(begin["approval"])
        self.assertEqual(begin["policy"], "record")

    def test_require_mode_refuses_unapproved_non_idempotent_mutation_before_locking(self):
        with mock.patch.dict(os.environ, {"DESK_MUTATION_POLICY": "require"}):
            with self.assertRaises(ApprovalRequired) as cm:
                with ops.write_op(self.p, "build", "A"):
                    self.fail("body must not run")
            self.assertEqual(cm.exception.context["op"], "build")
            self.assertEqual(ops.journal(self.p), [])                       # nothing journalled, no lock taken
            self.assertFalse(os.path.exists(os.path.join(self.p, "state", "write.lock")))
            # an idempotent mutation (read-back probe) is allowed without approval
            with ops.write_op(self.p, "pins_probe", "MPN", classification=ops.OP_IDEMPOTENT_MUTATION):
                pass
            # and an approved one proceeds
            aid = ops.record_approval(self.p, "build", "A", "operator", "cli")
            with ops.write_op(self.p, "build", "A", approval=aid):
                pass
        kinds = [(r["phase"], r.get("op")) for r in ops.journal(self.p)]
        self.assertIn(("begin", "pins_probe"), kinds)
        self.assertIn(("approval", "build"), kinds)
        self.assertIn(("end", "build"), kinds)

    def test_unknown_policy_value_falls_back_to_record(self):
        with mock.patch.dict(os.environ, {"DESK_MUTATION_POLICY": "whatever"}):
            self.assertEqual(ops.MutationPolicy.mode(), "record")

    def test_registry_side_effect_is_recorded_for_known_operations(self):
        self.assertTrue(ops.MutationPolicy.registry_side_effect("create_copper_zone"))
        self.assertFalse(ops.MutationPolicy.registry_side_effect("calc_trace_width"))
        self.assertIsNone(ops.MutationPolicy.registry_side_effect("build"))     # tool-level op, not a registry id
        with ops.write_op(self.p, "create_copper_zone", "GND"):
            pass
        begin = [r for r in ops.journal(self.p) if r["phase"] == "begin"][0]
        self.assertTrue(begin["registry_side_effect"])


class EveryMutationPathIsJournalled(unittest.TestCase):
    """Every live `is_mutation=True` call in desk/ and tools/ sits inside a write_op block (or is the one
    disposable-project test harness, which runs only on a throw-away project)."""
    ALLOWED_FILES = {"tools/live_disposable_test.py"}

    def test_mutation_calls_are_inside_write_op(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for sub in ("desk", "tools"):
            for dp, _, files in os.walk(os.path.join(root, sub)):
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
                    if rel in self.ALLOWED_FILES:
                        continue
                    with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                        lines = f.read().split("\n")
                    for i, line in enumerate(lines):
                        if "is_mutation=True" not in line or "def ex(" in line:
                            continue
                        window = "\n".join(lines[max(0, i - 12): i + 1])
                        if "write_op(" not in window:
                            offenders.append(f"{rel}:{i + 1}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_callers_pass_an_approval(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in ("tools/build.py", "tools/clear_block.py", "tools/pins.py", "desk/routing/pipeline.py",
                    "desk/rework/executor.py", "desk/schematic_io.py"):
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                src = f.read()
            for m in __import__("re").finditer(r"write_op\((?:[^()]|\([^()]*\))*\)", src):
                self.assertIn("approval", m.group(0), f"{rel}: {m.group(0)[:80]}")


if __name__ == "__main__":
    unittest.main()
