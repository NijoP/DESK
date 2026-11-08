"""Tests for EasyEDA Pro Integration and Safety Harness."""

import os
import unittest
import tempfile
import shutil
import json
from desk.eda.easyeda_pro import (
    EasyEDAProCLI,
    EasyEDAProManager,
    EasyEDASession,
    SafetyViolationError,
    ProjectNotFoundError,
)


class TestEasyEDAProIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.mgr = EasyEDAProManager()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_protected_project_detection(self):
        self.assertTrue(self.mgr.is_project_protected("projects/BEEBOX_REV3"))
        self.assertTrue(self.mgr.is_project_protected("C:/pcbs/WATCH_v1.0"))
        self.assertTrue(self.mgr.is_project_protected("production_board_main"))
        self.assertFalse(self.mgr.is_project_protected("projects/disposable_test"))
        self.assertFalse(self.mgr.is_project_protected("scratch_run_1"))

    def test_mutation_guard_rejects_protected(self):
        with self.assertRaises(SafetyViolationError) as ctx:
            self.mgr.assert_mutation_permitted(
                "projects/BEEBOX",
                is_disposable_test=False,
                has_snapshot=True,
                captain_approval=True,
            )
        self.assertIn("protected customer pattern", str(ctx.exception))

    def test_mutation_guard_requires_approval_or_disposable(self):
        with self.assertRaises(SafetyViolationError) as ctx:
            self.mgr.assert_mutation_permitted(
                "projects/sample_board",
                is_disposable_test=False,
                has_snapshot=True,
                captain_approval=False,
            )
        self.assertIn("requires explicit Captain authorization", str(ctx.exception))

    def test_mutation_guard_requires_snapshot(self):
        with self.assertRaises(SafetyViolationError) as ctx:
            self.mgr.assert_mutation_permitted(
                "projects/disposable_test",
                is_disposable_test=True,
                has_snapshot=False,
                captain_approval=False,
            )
        self.assertIn("Pre-mutation rollback snapshot must exist", str(ctx.exception))

    def test_mutation_permitted_when_conditions_met(self):
        # Disposable test with snapshot
        try:
            self.mgr.assert_mutation_permitted(
                "projects/disposable_test",
                is_disposable_test=True,
                has_snapshot=True,
                captain_approval=False,
            )
        except SafetyViolationError:
            self.fail("assert_mutation_permitted raised SafetyViolationError unexpectedly")

        # Non-disposable with Captain approval and snapshot
        try:
            self.mgr.assert_mutation_permitted(
                "projects/my_custom_amp",
                is_disposable_test=False,
                has_snapshot=True,
                captain_approval=True,
            )
        except SafetyViolationError:
            self.fail("assert_mutation_permitted raised SafetyViolationError unexpectedly")

    def test_offline_project_inspection(self):
        proj_dir = os.path.join(self.tmp_dir, "test_proj")
        os.makedirs(proj_dir)
        with open(os.path.join(proj_dir, "board.epcb"), "w") as f:
            f.write("{}")
        with open(os.path.join(proj_dir, "schematic.sch"), "w") as f:
            f.write("{}")

        info = self.mgr.inspect_project_offline(proj_dir)
        self.assertEqual(info["project_name"], "test_proj")
        self.assertFalse(info["is_protected"])
        self.assertTrue(info["mutation_allowed"])
        self.assertEqual(len(info["pcb_files"]), 1)
        self.assertEqual(len(info["schematic_files"]), 1)

    def test_offline_pcb_primitives_readback(self):
        pcb_file = os.path.join(self.tmp_dir, "mock_pcb.json")
        sample_data = {
            "components": [{"id": "U1", "footprint": "SOT-23"}],
            "tracks": [{"net": "GND", "layer": 1, "width": 0.25}],
            "vias": [{"net": "GND", "x": 10.0, "y": 20.0}],
            "pads": [{"id": "U1_1", "net": "VCC"}],
            "zones": [{"net": "GND", "layer": 2}],
            "poured_copper": [{"net": "GND", "area": 450.0}],
        }
        with open(pcb_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)

        primitives = self.mgr.read_pcb_primitives_offline(pcb_file)
        self.assertEqual(len(primitives.components), 1)
        self.assertEqual(primitives.components[0]["id"], "U1")
        self.assertEqual(len(primitives.tracks), 1)
        self.assertEqual(len(primitives.vias), 1)
        self.assertEqual(len(primitives.zones), 1)
        self.assertEqual(len(primitives.poured_copper), 1)

    def test_cli_doctor_uninstalled_behavior(self):
        cli = EasyEDAProCLI(custom_binary_path="/nonexistent/easyeda-pro")
        doc = cli.doctor()
        self.assertIn(doc["status"], ("ERROR", "NOT_INSTALLED"))


if __name__ == "__main__":
    unittest.main()
