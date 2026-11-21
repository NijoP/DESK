"""
Unit tests for DESK Rework Mode Controlled Mutation Executor & Readback Verification.
Zero external dependencies.
"""

import os
import shutil
import tempfile
import unittest

from desk.snapshot import IndexedPCBSnapshot
from desk.rework import (
    ProjectBinding,
    RepairAction,
    ApprovalToken,
    RepairExecutor,
)


class TestReworkExecutor(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.comps = {
            "U1": {
                "x": 100.0, "y": 100.0, "rot": 0, "layer": 1,
                "pads": [
                    {"num": "1", "net": "OLD_NET"},
                    {"num": "2", "net": "GND"},
                ]
            },
            "U2": {
                "x": 200.0, "y": 100.0, "rot": 0, "layer": 1,
                "pads": [
                    {"num": "1", "net": "TARGET_NET"},
                    {"num": "2", "net": "GND"},
                ]
            }
        }
        self.snap = IndexedPCBSnapshot(raw_dump=self.comps, project_id="TEST_PROJ")
        self.binding = ProjectBinding(
            project_name="TEST_PROJ",
            project_path=self.tmp_dir,
            project_uuid="uuid_test",
            window_id="offline",
            eda_port=49620,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_missing_approval_blocks_mutation(self):
        """Validates that a repair without a valid approval token is strictly rejected."""
        repair = RepairAction(
            repair_id="RP-0001",
            issue_id="RW-0001",
            sequence_number=1,
            action_type="UPDATE_PAD_NET",
            description="Reassign U1 pin 1",
            affected_objects={"ref": "U1", "pin": "1", "schematic_net": "NEW_NET"},
        )
        invalid_token = ApprovalToken(
            token="BAD_TOK",
            repair_id="RP-9999",  # Mismatch
            session_id="rework_s1",
            project_id="TEST_PROJ",
            revision_hash="rev1",
            action_type="UPDATE_PAD_NET",
            granted_at=0.0,
            is_valid=False,
        )

        res = RepairExecutor.execute_surgical_repair(
            repair=repair,
            snapshot=self.snap,
            binding=self.binding,
            approval_token=invalid_token,
            project_path=self.tmp_dir,
            session_id="rework_s1",
        )
        self.assertEqual(res.status, "BLOCKED")
        self.assertFalse(res.verification_passed)

    def test_surgical_update_pad_net_and_readback(self):
        """Validates execution of UPDATE_PAD_NET with mandatory physical readback."""
        repair = RepairAction(
            repair_id="RP-0001",
            issue_id="RW-0001",
            sequence_number=1,
            action_type="UPDATE_PAD_NET",
            description="Reassign U1 pin 1 to TARGET_NET",
            affected_objects={"ref": "U1", "pin": "1", "schematic_net": "TARGET_NET"},
        )
        valid_token = ApprovalToken(
            token="RW-APR-TEST1",
            repair_id="RP-0001",
            session_id="rework_s1",
            project_id="TEST_PROJ",
            revision_hash=self.snap.fingerprint,
            action_type="UPDATE_PAD_NET",
            granted_at=0.0,
            is_valid=True,
        )

        res = RepairExecutor.execute_surgical_repair(
            repair=repair,
            snapshot=self.snap,
            binding=self.binding,
            approval_token=valid_token,
            project_path=self.tmp_dir,
            session_id="rework_s1",
        )
        # Report F-3: the executor edits the in-memory snapshot only, so the result is SIMULATED, never VERIFIED.
        self.assertEqual(res.status, "SIMULATED")
        self.assertTrue(res.simulation_passed)
        self.assertFalse(res.verification_passed)
        self.assertFalse(res.live_readback)
        self.assertEqual(res.readback_data["net"], "TARGET_NET")

        # History log must exist
        hist_file = os.path.join(self.tmp_dir, "state", "rework", "rework_s1", "repair_history.jsonl")
        self.assertTrue(os.path.exists(hist_file))

    def test_surgical_route_net_execution(self):
        """Validates execution of ROUTE_NET without disturbing existing geometry."""
        # Add endpoints for NET_A on U1 and U2
        self.snap.update_pad_net("U1", "2", "NET_A")
        self.snap.update_pad_net("U2", "2", "NET_A")

        repair = RepairAction(
            repair_id="RP-0002",
            issue_id="RW-0002",
            sequence_number=2,
            action_type="ROUTE_NET",
            description="Route missing net NET_A",
            affected_objects={"net": "NET_A"},
        )
        token = ApprovalToken(
            token="RW-APR-TEST2",
            repair_id="RP-0002",
            session_id="rework_s1",
            project_id="TEST_PROJ",
            revision_hash=self.snap.fingerprint,
            action_type="ROUTE_NET",
            granted_at=0.0,
            is_valid=True,
        )

        res = RepairExecutor.execute_surgical_repair(
            repair=repair,
            snapshot=self.snap,
            binding=self.binding,
            approval_token=token,
            project_path=self.tmp_dir,
            session_id="rework_s1",
        )
        self.assertEqual(res.status, "SIMULATED")
        self.assertTrue(res.simulation_passed)
        self.assertFalse(res.verification_passed)
        self.assertGreaterEqual(res.readback_data["tracks_count"], 1)

    def _run(self, rid, action, objects):
        repair = RepairAction(repair_id=rid, issue_id="RW-0009", sequence_number=9, action_type=action,
                              description="synthetic", affected_objects=objects)
        token = ApprovalToken(token="RW-APR-" + rid, repair_id=rid, session_id="rework_s1", project_id="TEST_PROJ",
                              revision_hash=self.snap.fingerprint, action_type=action, granted_at=0.0, is_valid=True)
        return RepairExecutor.execute_surgical_repair(repair=repair, snapshot=self.snap, binding=self.binding,
                                                      approval_token=token, project_path=self.tmp_dir, session_id="rework_s1")

    def test_invented_action_type_fails_instead_of_default_pass(self):
        res = self._run("RP-0003", "TELEPORT_COMPONENT", {"ref": "U1"})
        self.assertEqual(res.status, "FAILED")
        self.assertFalse(res.simulation_passed)
        self.assertFalse(res.verification_passed)

    def test_widening_a_nonexistent_track_fails(self):
        res = self._run("RP-0004", "WIDEN_POWER_TRACK", {"track_id": "NO_SUCH_TRACK", "new_width": 20.0})
        self.assertEqual(res.status, "FAILED")
        self.assertFalse(res.verification_passed)

    def test_no_result_is_ever_verified_and_journal_records_no_board_mutation(self):
        from desk import ops
        for i, (action, objs) in enumerate([("UPDATE_PAD_NET", {"ref": "U1", "pin": "1", "schematic_net": "N"}),
                                            ("REPOUR_COPPER_ZONE", {"zone_id": "Z9"}),
                                            ("NUDGE_COMPONENT", {"ref": "U2"})]):
            res = self._run(f"RP-01{i}", action, objs)
            self.assertNotEqual(res.status, "VERIFIED", action)
            self.assertFalse(res.verification_passed, action)
            self.assertIn("SIMULATED", res.verification_details)
        begins = [r for r in ops.journal(self.tmp_dir) if r["phase"] == "begin"]
        self.assertTrue(begins)
        self.assertTrue(all(r["op"] == "rework_simulate" and r["classification"] == ops.OP_VALIDATION for r in begins))


if __name__ == "__main__":
    unittest.main()
