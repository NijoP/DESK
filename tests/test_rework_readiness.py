"""
Unit tests for DESK Rework Mode Manufacturing Readiness & Release Assessment.
Zero external dependencies.
"""

import os
import shutil
import tempfile
import unittest

from desk.snapshot import IndexedPCBSnapshot
from desk.rework import (
    ReadinessOutcome,
    ManufacturingReadinessEngine,
)


class TestReworkReadiness(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.comps = {
            "U1": {"x": 100.0, "y": 100.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "3V3"}]}
        }
        self.snap = IndexedPCBSnapshot(raw_dump=self.comps, project_id="TEST_PROJ")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_incomplete_outcome_when_issues_remain(self):
        """Validates that outstanding issues result in INCOMPLETE outcome."""
        assessment = ManufacturingReadinessEngine.evaluate(
            session_id="rework_s1",
            project_path=self.tmp_dir,
            snapshot=self.snap,
            issues_count=5,
            resolved_count=2,
        )
        self.assertEqual(assessment.outcome, ReadinessOutcome.INCOMPLETE)
        self.assertEqual(assessment.issues_outstanding, 3)
        self.assertIsNotNone(assessment.report_path)
        self.assertTrue(os.path.exists(assessment.report_path))

    def test_ready_outcome_when_all_issues_resolved_and_gates_pass(self):
        """Validates READY_FOR_MANUFACTURING when all gates pass and 0 issues remain."""
        assessment = ManufacturingReadinessEngine.evaluate(
            session_id="rework_s1",
            project_path=self.tmp_dir,
            snapshot=self.snap,
            issues_count=3,
            resolved_count=3,
            discontinuities_count=0,
        )
        self.assertIn(assessment.outcome, (ReadinessOutcome.READY_FOR_MANUFACTURING, ReadinessOutcome.CONDITIONALLY_READY))
        self.assertEqual(assessment.issues_outstanding, 0)


if __name__ == "__main__":
    unittest.main()
