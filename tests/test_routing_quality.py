"""Automated Verification Suite for DRC Quality Acceptance and Delta Engine.
Tests baseline-aware diffing, fail-closed zero-new-violation gates, and violation classification.
"""
import unittest
from desk.routing.quality import DRCAcceptanceEngine, DRCViolationRecord


class TestRoutingQuality(unittest.TestCase):

    def test_clean_pass(self):
        baseline = []
        post_route = []
        res = DRCAcceptanceEngine.compare_drc(baseline, post_route)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "PASSED_CLEAN")

    def test_conditionally_passed_baseline_present(self):
        # Baseline has an edge setback warning (e.g. J2.1 0.04mm < 0.3mm from Project One)
        v_base = DRCViolationRecord(
            violation_id="V_01",
            category="BOARD_EDGE",
            severity="WARNING",
            layer=1,
            x_mil=100.0,
            y_mil=50.0,
            description="Pad J2.1 setback 0.04mm < 0.3mm",
            primitives=["J2.1"]
        )
        baseline = [v_base]
        post_route = [v_base]  # Still present, but NO new violations introduced

        res = DRCAcceptanceEngine.compare_drc(baseline, post_route)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "CONDITIONALLY_PASSED_BASELINE_PRESENT")
        self.assertEqual(len(res.pre_existing_unresolved), 1)
        self.assertEqual(len(res.newly_introduced_violations), 0)

    def test_rejected_new_violations(self):
        # Router accidentally introduced a short circuit
        v_new = DRCViolationRecord(
            violation_id="V_NEW",
            category="SHORT",
            severity="CRITICAL",
            layer=1,
            x_mil=350.0,
            y_mil=400.0,
            description="Short circuit between VBAT and GND",
            primitives=["T_14", "T_88"],
            nets_involved=["VBAT", "GND"]
        )
        baseline = []
        post_route = [v_new]

        res = DRCAcceptanceEngine.compare_drc(baseline, post_route)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "REJECTED_NEW_VIOLATIONS")
        self.assertEqual(len(res.newly_introduced_violations), 1)


if __name__ == "__main__":
    unittest.main()
