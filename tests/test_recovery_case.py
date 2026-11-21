"""B4: the ten-item recovery case with a fail-closed close (desk/recovery_case.py). Synthetic fixtures only."""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from desk import ledger as LG
from desk import ops
from desk import recovery_case as RC
from desk.decision_graph import history
from desk.errors import RecoveryRefused

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RecoveryCase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_rcase_")
        self.proj = os.path.join(self.d, "FIX")
        os.makedirs(os.path.join(self.proj, "blocks"))
        with open(os.path.join(self.proj, "blocks", "03_BUCK.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "03_BUCK", "qa": [{"value": "trace 0.25 mm for 1.2 A"}]}, f)
        self.dec = LG.add_decision_record(self.proj, "3V3 trace width 0.25 mm", "calc qa[0]", req_ids=["REQ-07"])
        self.asm = LG.add(self.proj, "assumption", "load current 1.2 A", source="REQ-07 rev A")
        self.case = RC.open_case(self.proj, {"failure_id": "FR-abc", "category": "DRC_FAILURE",
                                             "excerpt": "track width 0.25 < 0.40 required"}, task_id="T-drc-pcb")
        self.cid = self.case["case_id"]

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def fill(self):
        S = lambda k, v: RC.set_item(self.proj, self.cid, k, v)
        S("requirements", ["REQ-07"])
        S("assumptions", [self.asm["id"]])
        S("calculations", [{"ref": "blocks/03_BUCK.json#qa[0]", "formula": "IPC-2152", "result": "0.25 mm"}])
        S("components", [{"ref": "L1", "mpn": "XAL4020-222", "footprint": "IND_4020"}])
        S("decision_chain", [self.dec["id"]])
        RC.add_root_cause_claim(self.proj, self.cid, "width sized for 1.2 A; real load is 2.0 A",
                                [{"ref": "blocks/03_BUCK.json", "excerpt": "trace 0.25 mm for 1.2 A"}, {"ref": self.asm["id"]}],
                                confidence="STRONGLY_SUPPORTED", decision_id=self.dec["id"])
        S("correction", {"response": "recalculate_design", "target_decision_id": self.dec["id"], "new_value": "0.40 mm",
                         "proposer": "engine:calc"})
        S("verification", {"source": "validator:drc", "passed": True, "checks": [{"name": "width", "ok": True}]})
        S("approval", {"approval_id": ops.record_approval(self.proj, "recovery", self.cid, "CAPTAIN", "test")})

    def test_close_refused_with_any_item_missing(self):
        for k in RC.ITEMS:
            with self.subTest(missing=k):
                self.tearDown()
                self.setUp()
                self.fill()
                case = RC.load(self.proj, self.cid)
                case["items"][k] = None
                RC.save(self.proj, case)
                with self.assertRaises(RecoveryRefused) as cm:
                    RC.close(self.proj, self.cid, "3V3 trace width 0.40 mm", "calc rerun")
                self.assertIn(k, str(cm.exception))
                self.assertEqual(RC.load(self.proj, self.cid)["status"], "OPEN")

    def test_not_applicable_needs_a_reason_and_then_counts(self):
        self.fill()
        RC.set_item(self.proj, self.cid, "components", [])
        with self.assertRaises(RecoveryRefused):
            RC.mark_not_applicable(self.proj, self.cid, "components", "  ")
        RC.mark_not_applicable(self.proj, self.cid, "components", "trace-width rule; no part involved")
        self.assertEqual(RC.close(self.proj, self.cid, "w", "s")["status"], "CLOSED")

    def test_root_cause_claim_with_missing_evidence_is_discarded(self):
        RC.add_root_cause_claim(self.proj, self.cid, "invented", [{"ref": "state/route/nothing.json"}])
        RC.add_root_cause_claim(self.proj, self.cid, "misquoted", [{"ref": "blocks/03_BUCK.json", "excerpt": "0.6 mm for 3 A"}])
        RC.add_root_cause_claim(self.proj, self.cid, "unknown ledger", [{"ref": "L-0999"}])
        RC.add_root_cause_claim(self.proj, self.cid, "outside", [{"ref": "../../etc/passwd"}])
        RC.add_root_cause_claim(self.proj, self.cid, "uncited", [])
        case = RC.load(self.proj, self.cid)
        self.assertIsNone(case["items"]["root_cause"])
        self.assertEqual(len(case["discarded"]), 5)
        self.assertIn("root_cause", RC.missing_items(case))

    def test_verification_from_proposer_or_model_and_unknown_approval_refused(self):
        self.fill()
        for ver in ({"source": "engine:calc", "passed": True}, {"source": "model:nemotron", "passed": True},
                    {"source": "validator:drc", "passed": False}):
            RC.set_item(self.proj, self.cid, "verification", ver)
            with self.assertRaises(RecoveryRefused, msg=str(ver)):
                RC.close(self.proj, self.cid, "w", "s")
        RC.set_item(self.proj, self.cid, "verification", {"source": "validator:drc", "passed": True})
        for appr in ({"approval_id": "made-up"}, {"not_required": True}):
            RC.set_item(self.proj, self.cid, "approval", appr)
            with self.assertRaises(RecoveryRefused, msg=str(appr)):
                RC.close(self.proj, self.cid, "w", "s")
        RC.set_item(self.proj, self.cid, "approval", {"not_required": True, "policy_rule": "recovery_policy AUTO"})
        self.assertEqual(RC.close(self.proj, self.cid, "w", "s")["status"], "CLOSED")

    def test_close_appends_correction_and_superseding_decision(self):
        self.fill()
        n = len(LG.read(self.proj))
        case = RC.close(self.proj, self.cid, "3V3 trace width 0.40 mm", "calc rerun (IPC-2152, 2.0 A)")
        entries = LG.read(self.proj)
        self.assertEqual(len(entries), n + 2)
        corr, new = entries[-2], entries[-1]
        self.assertEqual((corr["type"], corr["refs"]), ("correction", self.dec["id"]))
        self.assertEqual((new["type"], new["supersedes"], new["req_ids"]), ("decision", self.dec["id"], ["REQ-07"]))
        self.assertEqual((case["closed"]["correction_id"], case["closed"]["decision_id"]), (corr["id"], new["id"]))
        self.assertEqual([e["id"] for e in history(entries, new["id"])["chain"]], [self.dec["id"], new["id"]])
        with self.assertRaises(RecoveryRefused):
            RC.set_item(self.proj, self.cid, "requirements", ["REQ-99"])      # a closed case is never edited

    def test_desk_py_recover_case_shows_all_ten_items(self):
        self.fill()
        tools = os.path.join(ROOT, "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        spec = importlib.util.spec_from_file_location("desk_tool_rcase_test", os.path.join(tools, "desk.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(mod.main(["recover", self.proj, "--case", self.cid]), 0)
        out = buf.getvalue()
        for i, title in enumerate(RC.TITLES, 1):
            self.assertIn(f"{i:2d}. {title}", out)
        self.assertNotIn("MISSING", out)


if __name__ == "__main__":
    unittest.main()
