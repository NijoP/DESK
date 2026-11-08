"""Unit tests for Phase 8: Hard Acceptance Gates and Weighted Quality Scoring.
"""
import unittest
from desk.quality import QualityGateEvaluator, HardAcceptanceGates, WeightedQualityScore
from desk.models import DRCViolation
from desk.profile import DesignProfile, LayerStackup, ManufacturerProfile

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

    def test_05_missing_drc_evidence_fails_closed(self):
        # If DRC was never executed, drc_violations is None -> fail-closed!
        report = QualityGateEvaluator.evaluate(
            drc_violations=None,
            unconnected_nets=[],
            critical_nets=[],
            routability_score=1.0,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.zero_shorts)
        self.assertTrue(any("Missing DRC evidence" in f for f in report.failures))

    def test_06_missing_connectivity_evidence_fails_closed(self):
        # Missing netlist connectivity check -> fail-closed!
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=None,
            critical_nets=[],
            routability_score=1.0,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.zero_unconnected_pads)
        self.assertTrue(any("Missing connectivity evidence" in f for f in report.failures))

    def test_07_missing_continuity_evidence_fails_closed(self):
        # Missing plane continuity check -> fail-closed!
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            routability_score=1.0,
            discontinuities_count=None
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.copper_zones_connected)
        self.assertTrue(any("Missing plane continuity evidence" in f for f in report.failures))

    def test_08_invalid_stackup_fails(self):
        profile = DesignProfile(project_id="INV_STACK")
        profile.stackup = []  # Empty stackup
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            profile=profile,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.valid_stackup)

    def test_09_invalid_manufacturing_limits_fails(self):
        profile = DesignProfile(project_id="INV_MFG")
        profile.manufacturing = ManufacturerProfile(min_trace_width_mil=0.0)
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            profile=profile,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.manufacturing_constraints_met)

    def test_10_negative_current_limit_fails_electrical(self):
        profile = DesignProfile(project_id="INV_ELEC", current_limits_A={"VBAT": -2.0})
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            profile=profile,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.electrical_constraints_met)

    def test_11_unclassified_drc_fails_mfg(self):
        # Violation with unclassified error type (e.g. "AnnularRing", "DrillTooClose") must fail manufacturing gate
        v = DRCViolation(violation_id="V_ANNULAR", rule_name="AnnularRing", error_type="InsufficientCopperWeb", layer="Top")
        report = QualityGateEvaluator.evaluate(
            drc_violations=[v],
            unconnected_nets=[],
            critical_nets=[],
            routability_score=1.0,
            discontinuities_count=0
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertFalse(report.hard_gates.manufacturing_constraints_met)
        self.assertEqual(report.hard_gates.manufacturing_constraints_met.state, "FAIL")

    def test_12_stale_evidence_fails_closed(self):
        # Evidence from revision 'rev_old' on board 'rev_new' must be flagged STALE
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            routability_score=1.0,
            discontinuities_count=0,
            board_revision="rev_new",
            evidence_revision="rev_old"
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertEqual(report.hard_gates.zero_shorts.state, "STALE")

    def test_13_require_profile_fails_closed_when_missing(self):
        # Strict mode requires an explicit profile
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            routability_score=1.0,
            discontinuities_count=0,
            require_profile=True
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertEqual(report.hard_gates.valid_stackup.state, "UNKNOWN")
        self.assertEqual(report.hard_gates.manufacturing_constraints_met.state, "UNKNOWN")
        self.assertEqual(report.hard_gates.electrical_constraints_met.state, "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
