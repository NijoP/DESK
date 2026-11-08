"""Unit tests for Phase 8: Hard Acceptance Gates and Weighted Quality Scoring.
"""
import unittest
from desk.quality import QualityGateEvaluator, HardAcceptanceGates, WeightedQualityScore
from desk.models import DRCViolation

class TestQualityAndMfgVerification(unittest.TestCase):

    def test_01_all_clean_approved(self):
        # 0 violations, 0 unconnected nets, 0 discontinuities -> APPROVED
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=["USB_DP", "USB_DN"],
            routability_score=0.95,
            discontinuities_count=0
        )
        self.assertTrue(report.hard_gates_passed)
        self.assertTrue(report.approved)
        self.assertGreaterEqual(report.total_score, 80.0)
        self.assertEqual(len(report.failures), 0)

    def test_02_hard_gate_failure_blocks_approval_even_with_high_score(self):
        # One short circuit detected -> hard gate fails
        v = DRCViolation(violation_id="V1", rule_name="Clearance", error_type="Short", layer="Top")
        report = QualityGateEvaluator.evaluate(
            drc_violations=[v],
            unconnected_nets=[],
            critical_nets=[],
            routability_score=0.98,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        # Even if weighted score is high, approved MUST be False
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.zero_shorts)
        self.assertIn("Unintended short circuits detected", report.failures)

    def test_03_critical_net_unconnected_blocks_approval(self):
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=["RF_ANT"],
            critical_nets=["RF_ANT", "USB_DP"],
            routability_score=0.90,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.all_critical_nets_connected)

    def test_04_weighted_score_formula(self):
        scores = WeightedQualityScore(
            electrical_correctness=100.0,
            routing_quality=80.0,
            placement_quality=90.0,
            rf_and_power=90.0,
            manufacturability=100.0,
            geometry_optimisation=100.0
        )
        # 25 + 16 + 13.5 + 18 + 10 + 10 = 92.5
        self.assertEqual(scores.compute_total(), 92.5)

if __name__ == "__main__":
    unittest.main()
