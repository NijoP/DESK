"""
Unit tests for DESK Rework Mode 8-Domain Engineering Audit Engine.
Zero external dependencies.
"""

import os
import shutil
import tempfile
import unittest

from desk.snapshot import IndexedPCBSnapshot
from desk.rework import (
    Issue,
    IssueCategory,
    IssueSeverity,
    ReworkAuditEngine,
)


class TestReworkAudit(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.comps = {
            "U1": {
                "x": 500.0, "y": 500.0, "rot": 0, "layer": 1,
                "bbox": [-100.0, 100.0, -100.0, 100.0],
                "pads": [
                    {"num": "1", "net": "3V3"},
                    {"num": "2", "net": "GND"},
                    {"num": "3", "net": "SPI_MOSI"},
                ]
            },
            "U2": {
                "x": 1000.0, "y": 500.0, "rot": 0, "layer": 1,
                "bbox": [-100.0, 100.0, -100.0, 100.0],
                "pads": [
                    {"num": "1", "net": "3V3"},
                    {"num": "2", "net": "GND"},
                    {"num": "3", "net": "SPI_MOSI"},
                ]
            },
            "J_EDGE": {
                # Edge violation: placed at x=10 mil (too close to 0 mil edge)
                "x": 10.0, "y": 500.0, "rot": 0, "layer": 1,
                "bbox": [-50.0, 50.0, -50.0, 50.0],
                "pads": [{"num": "1", "net": "VBUS"}]
            },
            "BAD_FP": {
                # Duplicate pads
                "x": 800.0, "y": 800.0, "rot": 0, "layer": 1,
                "pads": [{"num": "1", "net": "5V"}, {"num": "1", "net": "5V"}]
            }
        }
        self.tracks = [
            # 3V3 routed with narrow 4 mil trace (undersized)
            {"id": "t_3v3", "net": "3V3", "layer": 1, "width": 4.0, "x1": 500.0, "y1": 500.0, "x2": 1000.0, "y2": 500.0}
            # SPI_MOSI is completely unrouted!
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_full_8_domain_audit_execution(self):
        """Validates that ReworkAuditEngine discovers defects across all active domains."""
        snap = IndexedPCBSnapshot(raw_dump=self.comps, tracks=self.tracks, project_id="TEST_BOARD")
        auditor = ReworkAuditEngine(session_id="rework_test_audit", project_path=self.tmp_dir)

        # Mock schematic with net mismatch
        sch_blocks = [{
            "id": "B1",
            "parts": [{
                "ref": "U1",
                "pins": {"1": "3V3", "2": "GND", "3": "MISMATCHED_NET"}
            }]
        }]

        # Mock DRC violation
        raw_drc = [{"errorType": "Clearance Violation", "message": "Track too close to pad", "pos": [10, 20]}]

        issues = auditor.run_full_audit(
            snapshot=snap,
            schematic_blocks=sch_blocks,
            raw_drc=raw_drc,
            board_dimensions_mm=(50.0, 50.0),
        )

        self.assertGreater(len(issues), 0)
        categories = {i.category for i in issues}

        # Check domain coverage
        self.assertIn(IssueCategory.REQUIREMENTS, categories)
        self.assertIn(IssueCategory.SCHEMATIC, categories)
        self.assertIn(IssueCategory.COMPONENT, categories)
        self.assertIn(IssueCategory.PLACEMENT, categories)
        self.assertIn(IssueCategory.ROUTING, categories)
        self.assertIn(IssueCategory.POWER_THERMAL, categories)
        self.assertIn(IssueCategory.COPPER, categories)
        self.assertIn(IssueCategory.DRC, categories)

        # Validate unrouted net detection
        unrouted_issues = [i for i in issues if i.category == IssueCategory.ROUTING and "SPI_MOSI" in i.title]
        self.assertGreaterEqual(len(unrouted_issues), 1)

        # Validate duplicate pad detection
        dup_pad_issues = [i for i in issues if i.category == IssueCategory.COMPONENT and "Duplicate Pad" in i.title]
        self.assertGreaterEqual(len(dup_pad_issues), 1)

        # Validate undersized power track detection
        power_issues = [i for i in issues if i.category == IssueCategory.POWER_THERMAL and "Undersized" in i.title]
        self.assertGreaterEqual(len(power_issues), 1)


if __name__ == "__main__":
    unittest.main()
