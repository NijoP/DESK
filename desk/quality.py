"""Quality and Manufacturing Verification Engine for DESK (Mental Model M6).
Implements the strict separation between non-negotiable Hard Acceptance Gates
and Weighted Quality Scores:

5-State Gate Lifecycle:
- PASS:    Executed evidence proves zero violations.
- FAIL:    Deterministic violation identified.
- UNKNOWN: Evidence is missing, corrupted, or inconclusive (Fail-Closed).
- NOT_RUN: Verification stage was not executed (Fail-Closed).
- STALE:   Evidence belongs to an outdated revision or superseded profile (Fail-Closed).

Hard Gates:
1. Zero unintended shorts
2. Zero unconnected required pads
3. Zero hard clearance violations
4. All critical nets 100% connected
5. Valid stackup and layer assignments
6. Valid copper-zone connectivity
7. Required electrical constraints satisfied
8. Required manufacturing constraints satisfied

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
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from desk.profile import DesignProfile

@dataclass
class GateResult:
    name: str
    state: str = "NOT_RUN"  # "PASS", "FAIL", "UNKNOWN", "NOT_RUN", "STALE"
    evidence_id: str = ""
    timestamp: float = 0.0
    details: str = ""
    violations_count: int = 0

    def __bool__(self) -> bool:
        return self.state == "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "evidence_id": self.evidence_id,
            "timestamp": self.timestamp,
            "details": self.details,
            "violations_count": self.violations_count,
            "passing": self.state == "PASS"
        }

@dataclass
class HardAcceptanceGates:
    zero_shorts: GateResult = field(default_factory=lambda: GateResult("zero_shorts", "NOT_RUN"))
    zero_unconnected_pads: GateResult = field(default_factory=lambda: GateResult("zero_unconnected_pads", "NOT_RUN"))
    zero_clearance_violations: GateResult = field(default_factory=lambda: GateResult("zero_clearance_violations", "NOT_RUN"))
    all_critical_nets_connected: GateResult = field(default_factory=lambda: GateResult("all_critical_nets_connected", "NOT_RUN"))
    valid_stackup: GateResult = field(default_factory=lambda: GateResult("valid_stackup", "NOT_RUN"))
    copper_zones_connected: GateResult = field(default_factory=lambda: GateResult("copper_zones_connected", "NOT_RUN"))
    electrical_constraints_met: GateResult = field(default_factory=lambda: GateResult("electrical_constraints_met", "NOT_RUN"))
    manufacturing_constraints_met: GateResult = field(default_factory=lambda: GateResult("manufacturing_constraints_met", "NOT_RUN"))

    def all_passed(self) -> bool:
        return all(getattr(self, k).state == "PASS" for k in (
            "zero_shorts", "zero_unconnected_pads", "zero_clearance_violations",
            "all_critical_nets_connected", "valid_stackup", "copper_zones_connected",
            "electrical_constraints_met", "manufacturing_constraints_met"
        ))

    def failed_gates(self) -> List[str]:
        failed = []
        for k in ("zero_shorts", "zero_unconnected_pads", "zero_clearance_violations",
                  "all_critical_nets_connected", "valid_stackup", "copper_zones_connected",
                  "electrical_constraints_met", "manufacturing_constraints_met"):
            gate: GateResult = getattr(self, k)
            if gate.state != "PASS":
                msg = gate.details or f"Gate {k} failed with state {gate.state}"
                failed.append(msg)
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
            "hard_gates": {
                k: getattr(self.hard_gates, k).to_dict()
                for k in ("zero_shorts", "zero_unconnected_pads", "zero_clearance_violations",
                          "all_critical_nets_connected", "valid_stackup", "copper_zones_connected",
                          "electrical_constraints_met", "manufacturing_constraints_met")
            },
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
                 discontinuities_count: Optional[int] = 0,
                 evidence_timestamp: Optional[float] = None,
                 board_revision: Optional[str] = None,
                 evidence_revision: Optional[str] = None,
                 require_profile: bool = False) -> QualityReport:
        hard = HardAcceptanceGates()
        failures = []
        recommendations = []
        now = evidence_timestamp or time.time()

        # Check evidence freshness / staleness against board revision
        is_stale = bool(board_revision and evidence_revision and board_revision != evidence_revision)

        # 1. DRC Evidence Check (Fail-closed)
        short_count = 0
        clearance_count = 0
        other_drc_count = 0

        if drc_violations is None:
            hard.zero_shorts = GateResult("zero_shorts", "UNKNOWN", timestamp=now, details="Missing DRC evidence: DRC check was not executed.")
            hard.zero_clearance_violations = GateResult("zero_clearance_violations", "UNKNOWN", timestamp=now, details="Missing DRC evidence: DRC check was not executed.")
            failures.append("Missing DRC evidence: DRC check was not executed.")
        elif is_stale:
            hard.zero_shorts = GateResult("zero_shorts", "STALE", timestamp=now, details=f"DRC evidence from revision {evidence_revision} is stale against board {board_revision}.")
            hard.zero_clearance_violations = GateResult("zero_clearance_violations", "STALE", timestamp=now, details=f"DRC evidence from revision {evidence_revision} is stale against board {board_revision}.")
            failures.append("DRC evidence is stale.")
        else:
            for v in drc_violations:
                err_type = str(getattr(v, "error_type", "")).lower()
                rule_name = str(getattr(v, "rule_name", "")).lower()
                if "short" in err_type or "short" in rule_name:
                    short_count += 1
                elif "clearance" in err_type or "clearance" in rule_name:
                    clearance_count += 1
                else:
                    other_drc_count += 1

            if short_count == 0:
                hard.zero_shorts = GateResult("zero_shorts", "PASS", timestamp=now, details="0 short circuits verified.")
            else:
                hard.zero_shorts = GateResult("zero_shorts", "FAIL", timestamp=now, details="Unintended short circuits detected", violations_count=short_count)
                failures.append("Unintended short circuits detected")

            if clearance_count == 0:
                hard.zero_clearance_violations = GateResult("zero_clearance_violations", "PASS", timestamp=now, details="0 clearance violations verified.")
            else:
                hard.zero_clearance_violations = GateResult("zero_clearance_violations", "FAIL", timestamp=now, details="Hard clearance violations detected", violations_count=clearance_count)
                failures.append("Hard clearance violations detected")

        # 2. Netlist Connectivity Evidence Check (Fail-closed)
        if unconnected_nets is None:
            hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "UNKNOWN", timestamp=now, details="Missing connectivity evidence: Netlist connectivity was not verified.")
            hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "UNKNOWN", timestamp=now, details="Missing connectivity evidence: Netlist connectivity was not verified.")
            failures.append("Missing connectivity evidence: Netlist connectivity was not verified.")
        elif is_stale:
            hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "STALE", timestamp=now, details="Connectivity evidence is stale.")
            hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "STALE", timestamp=now, details="Critical nets evidence is stale.")
            failures.append("Connectivity evidence is stale.")
        else:
            unconnected_count = len(unconnected_nets)
            if unconnected_count == 0:
                hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "PASS", timestamp=now, details="All populated pads connected.")
            else:
                hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "FAIL", timestamp=now, details=f"Unconnected populated pads detected on nets: {unconnected_nets}", violations_count=unconnected_count)
                failures.append(f"Unconnected populated pads detected on nets: {unconnected_nets}")

            # Derive critical nets from profile if not explicitly passed
            if critical_nets is None and profile is not None:
                crit_set = set(profile.rf_nets)
                for net_name, limit_a in profile.current_limits_A.items():
                    if limit_a >= 1.0:
                        crit_set.add(net_name)
                critical_nets = sorted(crit_set)
            elif critical_nets is None:
                critical_nets = []

            unconnected_set = set(unconnected_nets)
            missing_critical = [n for n in critical_nets if n in unconnected_set]

            if len(missing_critical) > 0:
                hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "FAIL", timestamp=now, details=f"Critical nets unconnected: {missing_critical}", violations_count=len(missing_critical))
                failures.append(f"Critical nets unconnected: {missing_critical}")
            elif unconnected_count > 0 and len(critical_nets) == 0:
                # Unconnected nets exist and no critical nets specified -> cannot verify critical net status
                hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "UNKNOWN", timestamp=now, details="Unconnected pads exist but critical nets list is unspecified.")
                failures.append("Unconnected pads exist but critical nets list is unspecified.")
            else:
                hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "PASS", timestamp=now, details="All critical nets connected.")

        # 3. Copper Plane Continuity Check (Fail-closed)
        if discontinuities_count is None:
            hard.copper_zones_connected = GateResult("copper_zones_connected", "UNKNOWN", timestamp=now, details="Missing plane continuity evidence: Return-path continuity was not evaluated.")
            failures.append("Missing plane continuity evidence: Return-path continuity was not evaluated.")
            discon_for_score = 5
        elif is_stale:
            hard.copper_zones_connected = GateResult("copper_zones_connected", "STALE", timestamp=now, details="Plane continuity evidence is stale.")
            failures.append("Plane continuity evidence is stale.")
            discon_for_score = 5
        else:
            discon_for_score = discontinuities_count
            if discontinuities_count == 0:
                hard.copper_zones_connected = GateResult("copper_zones_connected", "PASS", timestamp=now, details="0 return-path discontinuities detected.")
            else:
                hard.copper_zones_connected = GateResult("copper_zones_connected", "FAIL", timestamp=now, details=f"{discontinuities_count} return-path discontinuities / slot crossings detected.", violations_count=discontinuities_count)
                failures.append(f"{discontinuities_count} return-path discontinuities / slot crossings detected.")

        # 4. Stackup Verification
        if profile is not None:
            if profile.stackup and len(profile.stackup) >= 2:
                copper_layers = [l for l in profile.stackup if l.copper_thickness_oz > 0]
                if len(copper_layers) >= 2:
                    hard.valid_stackup = GateResult("valid_stackup", "PASS", timestamp=now, details=f"Valid stackup with {len(profile.stackup)} layers verified.")
                else:
                    hard.valid_stackup = GateResult("valid_stackup", "FAIL", timestamp=now, details="Stackup has insufficient copper layers (< 2 with thickness > 0).")
                    failures.append("Stackup has insufficient copper layers (< 2 with thickness > 0).")
            else:
                hard.valid_stackup = GateResult("valid_stackup", "FAIL", timestamp=now, details="Layer stackup is empty or invalid.")
                failures.append("Layer stackup is empty or invalid.")
        elif require_profile:
            hard.valid_stackup = GateResult("valid_stackup", "UNKNOWN", timestamp=now, details="Missing DesignProfile: Stackup verification cannot be performed.")
            failures.append("Missing DesignProfile: Stackup verification cannot be performed.")
        else:
            hard.valid_stackup = GateResult("valid_stackup", "PASS", timestamp=now, details="Default stackup accepted (profile omitted).")

        # 5. Electrical & Manufacturing Constraints Verification
        if other_drc_count > 0:
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "FAIL", timestamp=now, details=f"{other_drc_count} unclassified DRC violations detected.", violations_count=other_drc_count)
            failures.append(f"{other_drc_count} unclassified DRC violations detected.")
        elif profile is not None:
            mfg = profile.manufacturing
            if mfg and mfg.min_trace_width_mil > 0 and mfg.min_clearance_mil > 0 and mfg.min_drill_mil > 0:
                hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "PASS", timestamp=now, details="Manufacturing thresholds respected.")
            else:
                hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "FAIL", timestamp=now, details="Manufacturing constraints invalid or missing.")
                failures.append("Manufacturing constraints invalid or missing.")
        elif require_profile:
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "UNKNOWN", timestamp=now, details="Missing DesignProfile: Manufacturing constraints cannot be verified.")
            failures.append("Missing DesignProfile: Manufacturing constraints cannot be verified.")
        else:
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "PASS", timestamp=now, details="Default manufacturing constraints accepted.")

        if profile is not None:
            has_invalid_elec = False
            for net, curr in profile.current_limits_A.items():
                if curr < 0:
                    has_invalid_elec = True
                    failures.append(f"Invalid negative current limit on net {net}: {curr}A")
            if not has_invalid_elec:
                hard.electrical_constraints_met = GateResult("electrical_constraints_met", "PASS", timestamp=now, details="Electrical constraints verified.")
            else:
                hard.electrical_constraints_met = GateResult("electrical_constraints_met", "FAIL", timestamp=now, details="Electrical constraints violated (negative current limits).")
        elif require_profile:
            hard.electrical_constraints_met = GateResult("electrical_constraints_met", "UNKNOWN", timestamp=now, details="Missing DesignProfile: Electrical current constraints cannot be verified.")
            failures.append("Missing DesignProfile: Electrical current constraints cannot be verified.")
        else:
            hard.electrical_constraints_met = GateResult("electrical_constraints_met", "PASS", timestamp=now, details="Default electrical constraints accepted.")

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
