"""Adversarial and Comprehensive Tests for Fail-Closed Quality Verification."""

import unittest
from desk.quality import (
    QualityGateEvaluator,
    VerificationEvidence,
    GateResult,
    HardAcceptanceGates,
    WeightedQualityScore,
)
from desk.models import DRCViolation
from desk.profile import DesignProfile, LayerStackup, ManufacturerProfile


class TestQualityFailClosed(unittest.TestCase):
    def setUp(self):
        self.profile = DesignProfile(project_id="TEST_PROJ")

    def test_omitted_discontinuities_fails_closed(self):
        """Calling evaluate without discontinuities_count must fail closed with UNKNOWN."""
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            profile=self.profile,
            # discontinuities_count is omitted!
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertEqual(report.hard_gates.copper_zones_connected.state, "UNKNOWN")
        self.assertIn("Missing plane continuity evidence", report.failures[0])

    def test_all_eight_gates_have_independent_evidence(self):
        """All 8 hard gates must produce traceable VerificationEvidence objects."""
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=["USB_DP"],
            profile=self.profile,
            discontinuities_count=0,
            board_revision="REV_A",
            profile_hash="HASH_123",
        )
        self.assertTrue(report.hard_gates_passed)
        self.assertTrue(report.approved)

        for gate_name in (
            "zero_shorts", "zero_unconnected_pads", "zero_clearance_violations",
            "all_critical_nets_connected", "valid_stackup", "copper_zones_connected",
            "electrical_constraints_met", "manufacturing_constraints_met"
        ):
            gate = getattr(report.hard_gates, gate_name)
            self.assertIsNotNone(gate.evidence, f"Gate {gate_name} missing VerificationEvidence")
            self.assertTrue(gate.evidence.evidence_id.startswith(f"EV_{gate_name}"))
            self.assertEqual(gate.evidence.status, "PASS")
            self.assertEqual(gate.evidence.pcb_revision_hash, "REV_A")

    def test_profile_hash_mismatch_flags_stale(self):
        """Evidence produced with a superseded design profile must fail closed as STALE."""
        report = QualityGateEvaluator.evaluate(
            drc_violations=[],
            unconnected_nets=[],
            critical_nets=[],
            profile=self.profile,
            discontinuities_count=0,
            profile_hash="HASH_NEW",
            evidence_profile_hash="HASH_OLD",
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertEqual(report.hard_gates.valid_stackup.state, "STALE")
        self.assertEqual(report.hard_gates.manufacturing_constraints_met.state, "STALE")
        self.assertEqual(report.hard_gates.electrical_constraints_met.state, "STALE")

    def test_high_score_never_overrides_hard_gate_failure(self):
        """A 99.5% weighted score must never approve a board with a single failed hard gate."""
        v = DRCViolation(violation_id="V1", rule_name="Clearance", error_type="Short", layer="Top")
        report = QualityGateEvaluator.evaluate(
            drc_violations=[v],
            unconnected_nets=[],
            critical_nets=[],
            profile=self.profile,
            discontinuities_count=0,
            routability_score=1.0,
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertFalse(report.approved)
        self.assertEqual(report.hard_gates.zero_shorts.state, "FAIL")

    def test_direct_evidence_injection_validation(self):
        """Pre-generated evidence map is properly evaluated and verified."""
        ev_short = VerificationEvidence(
            evidence_id="EV_CUSTOM_1",
            timestamp=1000.0,
            pcb_revision_hash="REV_1",
            profile_hash="P_1",
            tool_and_version="EasyEDA DRC 2.0",
            status="FAIL",
            details="Custom short detected in copper pour",
            violations_count=2,
        )
        report = QualityGateEvaluator.evaluate(
            profile=self.profile,
            discontinuities_count=0,
            evidence_map={"zero_shorts": ev_short},
        )
        self.assertFalse(report.hard_gates_passed)
        self.assertEqual(report.hard_gates.zero_shorts.state, "FAIL")
        self.assertEqual(report.hard_gates.zero_shorts.evidence_id, "EV_CUSTOM_1")


if __name__ == "__main__":
    unittest.main()
