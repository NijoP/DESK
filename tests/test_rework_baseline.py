"""
Unit tests for DESK Rework Mode Baseline Capture and External Modification Detection.
Zero external dependencies.
"""

import os
import shutil
import tempfile
import unittest

from desk.rework import (
    BaselineSnapshot,
    BaselineCaptureEngine,
)


class TestReworkBaseline(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.comps = {
            "R1": {"x": 100.0, "y": 200.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "3V3"}, {"num": "2", "net": "GND"}]},
            "C1": {"x": 150.0, "y": 200.0, "rot": 90, "layer": 1, "pads": [{"num": "1", "net": "3V3"}, {"num": "2", "net": "GND"}]},
        }
        self.tracks = [
            {"id": "t1", "net": "3V3", "layer": 1, "width": 10.0, "x1": 100.0, "y1": 200.0, "x2": 150.0, "y2": 200.0}
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_baseline_capture_and_serialization(self):
        """Validates that baseline snapshot computes multi-domain fingerprints and saves atomically."""
        baseline = BaselineCaptureEngine.capture_from_data(
            session_id="rework_test_01",
            project_path=self.tmp_dir,
            components_dump=self.comps,
            tracks=self.tracks,
        )
        self.assertEqual(baseline.components_count, 2)
        self.assertEqual(baseline.tracks_count, 1)
        self.assertIsNotNone(baseline.geometry_rev)
        self.assertIsNotNone(baseline.connectivity_rev)
        self.assertIsNotNone(baseline.composite_fingerprint)

        # Save and reload
        saved_path = BaselineCaptureEngine.save_baseline(baseline)
        self.assertTrue(os.path.exists(saved_path))

        loaded = BaselineCaptureEngine.load_baseline(self.tmp_dir, "rework_test_01")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.composite_fingerprint, baseline.composite_fingerprint)
        self.assertEqual(loaded.components_count, 2)

    def test_external_modification_detection(self):
        """Validates detection of changes made to the PCB outside DESK."""
        baseline = BaselineCaptureEngine.capture_from_data(
            session_id="rework_test_01",
            project_path=self.tmp_dir,
            components_dump=self.comps,
            tracks=self.tracks,
        )

        # 1. Exact match (no modification)
        has_mod, changed, diff = BaselineCaptureEngine.detect_external_modifications(
            baseline=baseline,
            current_components=self.comps,
            current_tracks=self.tracks,
        )
        self.assertFalse(has_mod)
        self.assertEqual(len(changed), 0)

        # 2. Geometric modification (moved R1)
        modified_comps = dict(self.comps)
        modified_comps["R1"] = {"x": 500.0, "y": 600.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "3V3"}, {"num": "2", "net": "GND"}]}
        has_mod, changed, diff = BaselineCaptureEngine.detect_external_modifications(
            baseline=baseline,
            current_components=modified_comps,
            current_tracks=self.tracks,
        )
        self.assertTrue(has_mod)
        self.assertIn("geometry", changed)

        # 3. Connectivity modification (changed net on pad)
        net_mod_comps = dict(self.comps)
        net_mod_comps["R1"] = {"x": 100.0, "y": 200.0, "rot": 0, "layer": 1, "pads": [{"num": "1", "net": "5V"}, {"num": "2", "net": "GND"}]}
        has_mod, changed, diff = BaselineCaptureEngine.detect_external_modifications(
            baseline=baseline,
            current_components=net_mod_comps,
            current_tracks=self.tracks,
        )
        self.assertTrue(has_mod)
        self.assertIn("connectivity", changed)


if __name__ == "__main__":
    unittest.main()
