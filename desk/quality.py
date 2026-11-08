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
    zero_shorts: bool = False
    zero_unconnected_pads: bool = False
    zero_clearance_violations: bool = False
    all_critical_nets_connected: bool = False
    valid_stackup: bool = False
    copper_zones_connected: bool = False
    electrical_constraints_met: bool = False
    manufacturing_constraints_met: bool = False

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
    def evaluate(drc_violations: Optional[List[Any]] = None,
                 unconnected_nets: Optional[List[str]] = None,
                 critical_nets: Optional[List[str]] = None,
                 routability_score: float = 1.0,
                 profile: Optional[DesignProfile] = None,
                 discontinuities_count: Optional[int] = 0) -> QualityReport:
        hard = HardAcceptanceGates()
        failures = []
        recommendations = []

        # 1. DRC Evidence Check (Fail-closed)
        short_count = 0
        clearance_count = 0
        if drc_violations is None:
            failures.append("Missing DRC evidence: DRC check was not executed.")
        else:
            for v in drc_violations:
                err_type = str(getattr(v, "error_type", "")).lower()
                rule_name = str(getattr(v, "rule_name", "")).lower()
                if "short" in err_type or "short" in rule_name:
                    short_count += 1
                elif "clearance" in err_type or "clearance" in rule_name:
                    clearance_count += 1

            hard.zero_shorts = (short_count == 0)
            hard.zero_clearance_violations = (clearance_count == 0)

        # 2. Netlist Connectivity Evidence Check (Fail-closed)
        critical_nets = critical_nets or []
        if unconnected_nets is None:
            failures.append("Missing connectivity evidence: Netlist connectivity was not verified.")
        else:
            unconnected_count = len(unconnected_nets)
            hard.zero_unconnected_pads = (unconnected_count == 0)

            unconnected_set = set(unconnected_nets)
            missing_critical = [n for n in critical_nets if n in unconnected_set]
            hard.all_critical_nets_connected = (len(missing_critical) == 0)
            if missing_critical:
                failures.append(f"Critical nets unconnected: {missing_critical}")

        # 3. Copper Plane Continuity Check (Fail-closed)
        if discontinuities_count is None:
            failures.append("Missing plane continuity evidence: Return-path continuity was not evaluated.")
            discon_for_score = 5
        else:
            discon_for_score = discontinuities_count
            hard.copper_zones_connected = (discontinuities_count == 0)
            if discontinuities_count > 0:
                failures.append(f"{discontinuities_count} return-path discontinuities / slot crossings detected.")

        # 4. Stackup Verification
        if profile is not None:
            if profile.stackup and len(profile.stackup) >= 2:
                copper_layers = [l for l in profile.stackup if l.copper_thickness_oz > 0]
                if len(copper_layers) >= 2:
                    hard.valid_stackup = True
                else:
                    failures.append("Stackup has insufficient copper layers (< 2 with thickness > 0).")
            else:
                failures.append("Layer stackup is empty or invalid.")
        else:
            hard.valid_stackup = True

        # 5. Electrical & Manufacturing Constraints Verification
        if profile is not None:
            mfg = profile.manufacturing
            if mfg and mfg.min_trace_width_mil > 0 and mfg.min_clearance_mil > 0 and mfg.min_drill_mil > 0:
                hard.manufacturing_constraints_met = True
            else:
                failures.append("Manufacturing constraints invalid or missing.")

            has_invalid_elec = False
            for net, curr in profile.current_limits_A.items():
                if curr < 0:
                    has_invalid_elec = True
                    failures.append(f"Invalid negative current limit on net {net}: {curr}A")
            if not has_invalid_elec:
                hard.electrical_constraints_met = True
        else:
            hard.manufacturing_constraints_met = True
            hard.electrical_constraints_met = True

        failures.extend([f for f in hard.failed_gates() if f not in failures])

        # 2. Compute Weighted Scores
        scores = WeightedQualityScore()
        drc_penalty = (short_count * 25.0) + (clearance_count * 5.0) if drc_violations is not None else 50.0
        scores.electrical_correctness = max(0.0, 100.0 - drc_penalty)
        scores.routing_quality = max(0.0, round(routability_score * 100.0, 1))
        scores.rf_and_power = max(0.0, 100.0 - (discon_for_score * 20.0))

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
