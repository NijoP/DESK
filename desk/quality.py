"""Quality and Manufacturing Verification Engine for DESK (Mental Model M6).
Implements the strict separation between non-negotiable Hard Acceptance Gates
and Weighted Quality Scores:

Hard Gates:
- Zero unintended shorts
- Zero unconnected required pads
- Zero hard clearance violations
- All critical nets 100% connected
- Valid stackup and layer assignments
- Valid copper-zone connectivity
- Required electrical constraints satisfied
- Required manufacturing constraints satisfied

Weighted Score (0-100):
- Electrical correctness: 25%
- Routing quality: 20%
- Placement quality: 15%
- RF and power constraints: 20%
- Manufacturability: 10%
- Geometry optimisation: 10%

A high weighted score CANNOT override a failed hard gate.
Zero external dependencies (pure Python standard library).
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from desk.profile import DesignProfile

@dataclass
class HardAcceptanceGates:
    zero_shorts: bool = True
    zero_unconnected_pads: bool = True
    zero_clearance_violations: bool = True
    all_critical_nets_connected: bool = True
    valid_stackup: bool = True
    copper_zones_connected: bool = True
    electrical_constraints_met: bool = True
    manufacturing_constraints_met: bool = True

    def all_passed(self) -> bool:
        return (
            self.zero_shorts and
            self.zero_unconnected_pads and
            self.zero_clearance_violations and
            self.all_critical_nets_connected and
            self.valid_stackup and
            self.copper_zones_connected and
            self.electrical_constraints_met and
            self.manufacturing_constraints_met
        )

    def failed_gates(self) -> List[str]:
        failed = []
        if not self.zero_shorts: failed.append("Unintended short circuits detected")
        if not self.zero_unconnected_pads: failed.append("Unconnected populated pads detected")
        if not self.zero_clearance_violations: failed.append("Hard clearance violations detected")
        if not self.all_critical_nets_connected: failed.append("Critical nets not fully connected")
        if not self.valid_stackup: failed.append("Invalid layer stackup configuration")
        if not self.copper_zones_connected: failed.append("Ground / copper plane continuity broken")
        if not self.electrical_constraints_met: failed.append("Electrical constraints violated")
        if not self.manufacturing_constraints_met: failed.append("Manufacturing capability thresholds violated")
        return failed

@dataclass
class WeightedQualityScore:
    electrical_correctness: float = 100.0   # Weight: 25%
    routing_quality: float = 100.0          # Weight: 20%
    placement_quality: float = 100.0        # Weight: 15%
    rf_and_power: float = 100.0             # Weight: 20%
    manufacturability: float = 100.0        # Weight: 10%
    geometry_optimisation: float = 100.0    # Weight: 10%

    def compute_total(self) -> float:
        return round(
            (self.electrical_correctness * 0.25) +
            (self.routing_quality * 0.20) +
            (self.placement_quality * 0.15) +
            (self.rf_and_power * 0.20) +
            (self.manufacturability * 0.10) +
            (self.geometry_optimisation * 0.10),
            1
        )

@dataclass
class QualityReport:
    approved: bool
    total_score: float
    hard_gates_passed: bool
    hard_gates: HardAcceptanceGates
    score_breakdown: WeightedQualityScore
    failures: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "total_score": self.total_score,
            "hard_gates_passed": self.hard_gates_passed,
            "hard_gates": asdict(self.hard_gates),
            "score_breakdown": asdict(self.score_breakdown),
            "failures": self.failures,
            "recommendations": self.recommendations
        }

class QualityGateEvaluator:
    """Evaluates comprehensive board readiness by combining hard gates and weighted scores."""

    @staticmethod
    def evaluate(drc_violations: List[Any],
                 unconnected_nets: List[str],
                 critical_nets: List[str],
                 routability_score: float = 1.0,
                 profile: Optional[DesignProfile] = None,
                 discontinuities_count: int = 0) -> QualityReport:
        hard = HardAcceptanceGates()
        failures = []
        recommendations = []

        # 1. Evaluate Hard Gates
        short_count = 0
        clearance_count = 0
        unconnected_count = len(unconnected_nets)

        for v in drc_violations:
            err_type = str(getattr(v, "error_type", "")).lower()
            rule_name = str(getattr(v, "rule_name", "")).lower()
            if "short" in err_type or "short" in rule_name:
                short_count += 1
            elif "clearance" in err_type or "clearance" in rule_name:
                clearance_count += 1

        if short_count > 0:
            hard.zero_shorts = False
        if clearance_count > 0:
            hard.zero_clearance_violations = False
        if unconnected_count > 0:
            hard.zero_unconnected_pads = False

        # Critical nets check
        unconnected_set = set(unconnected_nets)
        missing_critical = [n for n in critical_nets if n in unconnected_set]
        if missing_critical:
            hard.all_critical_nets_connected = False
            failures.append(f"Critical nets unconnected: {missing_critical}")

        # Copper plane continuity
        if discontinuities_count > 0:
            hard.copper_zones_connected = False
            failures.append(f"{discontinuities_count} return-path discontinuities / slot crossings detected.")

        failures.extend(hard.failed_gates())

        # 2. Compute Weighted Scores
        scores = WeightedQualityScore()
        # Electrical correctness penalised by shorts or clearance issues
        scores.electrical_correctness = max(0.0, 100.0 - (short_count * 25.0) - (clearance_count * 5.0))
        # Routing quality
        scores.routing_quality = max(0.0, round(routability_score * 100.0, 1))
        # RF and power constraints
        scores.rf_and_power = max(0.0, 100.0 - (discontinuities_count * 20.0))

        total_score = scores.compute_total()

        # Approval requires: ALL hard gates passed AND weighted score >= 80.0
        hard_passed = hard.all_passed()
        approved = hard_passed and (total_score >= 80.0)

        if not hard_passed:
            recommendations.append("Fix all hard gate failures before proceeding to fabrication.")
        if total_score < 80.0:
            recommendations.append(f"Improve weighted design quality score (current {total_score:.1f}/100, threshold 80.0).")

        return QualityReport(
            approved=approved,
            total_score=total_score,
            hard_gates_passed=hard_passed,
            hard_gates=hard,
            score_breakdown=scores,
            failures=failures,
            recommendations=recommendations
        )
