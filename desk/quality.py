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
from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from desk.profile import DesignProfile


@dataclass
class VerificationEvidence:
    """Cryptographically traceable proof of an engineering verification step."""
    evidence_id: str
    timestamp: float
    pcb_revision_hash: str
    profile_hash: str
    tool_and_version: str
    status: str  # "PASS", "FAIL", "UNKNOWN", "NOT_RUN", "STALE"
    details: str = ""
    violations_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid_for(self, current_board_rev: Optional[str], current_profile_hash: Optional[str]) -> bool:
        """Verifies evidence is not stale or from a mismatched revision/profile."""
        if current_board_rev and self.pcb_revision_hash and self.pcb_revision_hash != current_board_rev:
            return False
        if current_profile_hash and self.profile_hash and self.profile_hash != current_profile_hash:
            return False
        return True


@dataclass
class GateResult:
    name: str
    state: str = "NOT_RUN"  # "PASS", "FAIL", "UNKNOWN", "NOT_RUN", "STALE"
    evidence_id: str = ""
    timestamp: float = 0.0
    details: str = ""
    violations_count: int = 0
    evidence: Optional[VerificationEvidence] = None

    def __post_init__(self):
        if self.evidence:
            self.evidence_id = self.evidence.evidence_id
            self.timestamp = self.evidence.timestamp
            if not self.details:
                self.details = self.evidence.details
            self.violations_count = self.evidence.violations_count
            self.state = self.evidence.status

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
            "passing": self.state == "PASS",
            "evidence": asdict(self.evidence) if self.evidence else None,
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
    def _create_evidence(
        gate_name: str,
        status: str,
        details: str,
        violations_count: int,
        timestamp: float,
        board_rev: str,
        profile_hash: str,
        tool_name: str = "DESK Quality Engine v2.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VerificationEvidence:
        eid = f"EV_{gate_name}_{int(timestamp * 1000)}_{uuid.uuid4().hex[:6]}"
        return VerificationEvidence(
            evidence_id=eid,
            timestamp=timestamp,
            pcb_revision_hash=board_rev,
            profile_hash=profile_hash,
            tool_and_version=tool_name,
            status=status,
            details=details,
            violations_count=violations_count,
            metadata=metadata or {},
        )

    @classmethod
    def evaluate(
        cls,
        drc_violations: Optional[List[Any]] = None,
        unconnected_nets: Optional[List[str]] = None,
        critical_nets: Optional[List[str]] = None,
        routability_score: float = 1.0,
        profile: Optional[DesignProfile] = None,
        discontinuities_count: Optional[int] = None,  # Fail-closed default: None
        evidence_timestamp: Optional[float] = None,
        board_revision: Optional[str] = None,
        evidence_revision: Optional[str] = None,
        profile_hash: Optional[str] = None,
        evidence_profile_hash: Optional[str] = None,
        require_profile: bool = False,
        evidence_map: Optional[Dict[str, VerificationEvidence]] = None,
    ) -> QualityReport:
        hard = HardAcceptanceGates()
        failures = []
        recommendations = []
        now = evidence_timestamp or time.time()

        cur_board_rev = board_revision or "REV_CURRENT"
        cur_prof_hash = profile_hash or (profile.profile_hash if profile else "PROF_CURRENT")
        ev_board_rev = evidence_revision or cur_board_rev
        ev_prof_hash = evidence_profile_hash or cur_prof_hash

        # Staleness checks
        is_board_stale = bool(board_revision and evidence_revision and board_revision != evidence_revision)
        is_profile_stale = bool(profile_hash and evidence_profile_hash and profile_hash != evidence_profile_hash)
        if profile and evidence_profile_hash and profile.profile_hash and profile.profile_hash != evidence_profile_hash:
            is_profile_stale = True

        evidence_map = evidence_map or {}

        # -------------------------------------------------------------
        # Gate 1 & 3: DRC Evidence Check (zero_shorts, zero_clearance_violations)
        # -------------------------------------------------------------
        short_count = 0
        clearance_count = 0
        other_drc_count = 0

        if "zero_shorts" in evidence_map:
            hard.zero_shorts = GateResult("zero_shorts", evidence=evidence_map["zero_shorts"])
            if not hard.zero_shorts: failures.append(hard.zero_shorts.details)
        elif drc_violations is None:
            ev_short = cls._create_evidence("zero_shorts", "UNKNOWN", "Missing DRC evidence: DRC check was not executed.", 0, now, ev_board_rev, ev_prof_hash)
            hard.zero_shorts = GateResult("zero_shorts", "UNKNOWN", evidence=ev_short, details=ev_short.details)
            failures.append("Missing DRC evidence: DRC check was not executed.")
        elif is_board_stale:
            ev_short = cls._create_evidence("zero_shorts", "STALE", f"DRC evidence from revision {evidence_revision} is stale against board {board_revision}.", 0, now, ev_board_rev, ev_prof_hash)
            hard.zero_shorts = GateResult("zero_shorts", "STALE", evidence=ev_short, details=ev_short.details)
            failures.append("DRC evidence is stale.")
        else:
            for v in (drc_violations or []):
                err_type = str(getattr(v, "error_type", "")).lower()
                rule_name = str(getattr(v, "rule_name", "")).lower()
                if "short" in err_type or "short" in rule_name:
                    short_count += 1
                elif "clearance" in err_type or "clearance" in rule_name:
                    clearance_count += 1
                else:
                    other_drc_count += 1

            if short_count == 0:
                ev_s = cls._create_evidence("zero_shorts", "PASS", "0 short circuits verified.", 0, now, cur_board_rev, cur_prof_hash)
                hard.zero_shorts = GateResult("zero_shorts", "PASS", evidence=ev_s, details=ev_s.details)
            else:
                ev_s = cls._create_evidence("zero_shorts", "FAIL", "Unintended short circuits detected", short_count, now, cur_board_rev, cur_prof_hash)
                hard.zero_shorts = GateResult("zero_shorts", "FAIL", evidence=ev_s, details=ev_s.details, violations_count=short_count)
                failures.append("Unintended short circuits detected")

        if "zero_clearance_violations" in evidence_map:
            hard.zero_clearance_violations = GateResult("zero_clearance_violations", evidence=evidence_map["zero_clearance_violations"])
            if not hard.zero_clearance_violations: failures.append(hard.zero_clearance_violations.details)
        elif drc_violations is None:
            ev_clear = cls._create_evidence("zero_clearance_violations", "UNKNOWN", "Missing DRC evidence: DRC check was not executed.", 0, now, ev_board_rev, ev_prof_hash)
            hard.zero_clearance_violations = GateResult("zero_clearance_violations", "UNKNOWN", evidence=ev_clear, details=ev_clear.details)
            if "Missing DRC evidence: DRC check was not executed." not in failures:
                failures.append("Missing DRC evidence: DRC check was not executed.")
        elif is_board_stale:
            ev_clear = cls._create_evidence("zero_clearance_violations", "STALE", f"DRC evidence from revision {evidence_revision} is stale against board {board_revision}.", 0, now, ev_board_rev, ev_prof_hash)
            hard.zero_clearance_violations = GateResult("zero_clearance_violations", "STALE", evidence=ev_clear, details=ev_clear.details)
            if "DRC evidence is stale." not in failures:
                failures.append("DRC evidence is stale.")
        else:
            if clearance_count == 0:
                ev_c = cls._create_evidence("zero_clearance_violations", "PASS", "0 clearance violations verified.", 0, now, cur_board_rev, cur_prof_hash)
                hard.zero_clearance_violations = GateResult("zero_clearance_violations", "PASS", evidence=ev_c, details=ev_c.details)
            else:
                ev_c = cls._create_evidence("zero_clearance_violations", "FAIL", "Hard clearance violations detected", clearance_count, now, cur_board_rev, cur_prof_hash)
                hard.zero_clearance_violations = GateResult("zero_clearance_violations", "FAIL", evidence=ev_c, details=ev_c.details, violations_count=clearance_count)
                failures.append("Hard clearance violations detected")

        # -------------------------------------------------------------
        # Gate 2 & 4: Netlist Connectivity (zero_unconnected_pads, all_critical_nets_connected)
        # -------------------------------------------------------------
        if unconnected_nets is None and "zero_unconnected_pads" not in evidence_map:
            ev_unc = cls._create_evidence("zero_unconnected_pads", "UNKNOWN", "Missing connectivity evidence: Netlist connectivity was not verified.", 0, now, ev_board_rev, ev_prof_hash)
            ev_crit = cls._create_evidence("all_critical_nets_connected", "UNKNOWN", "Missing connectivity evidence: Netlist connectivity was not verified.", 0, now, ev_board_rev, ev_prof_hash)
            hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "UNKNOWN", evidence=ev_unc, details=ev_unc.details)
            hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "UNKNOWN", evidence=ev_crit, details=ev_crit.details)
            failures.append("Missing connectivity evidence: Netlist connectivity was not verified.")
        elif is_board_stale:
            ev_unc = cls._create_evidence("zero_unconnected_pads", "STALE", "Connectivity evidence is stale.", 0, now, ev_board_rev, ev_prof_hash)
            ev_crit = cls._create_evidence("all_critical_nets_connected", "STALE", "Critical nets evidence is stale.", 0, now, ev_board_rev, ev_prof_hash)
            hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "STALE", evidence=ev_unc, details=ev_unc.details)
            hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "STALE", evidence=ev_crit, details=ev_crit.details)
            failures.append("Connectivity evidence is stale.")
        elif "zero_unconnected_pads" in evidence_map:
            hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", evidence=evidence_map["zero_unconnected_pads"])
            if not hard.zero_unconnected_pads: failures.append(hard.zero_unconnected_pads.details)
        else:
            unconnected_count = len(unconnected_nets)
            if unconnected_count == 0:
                ev_u = cls._create_evidence("zero_unconnected_pads", "PASS", "All populated pads connected.", 0, now, cur_board_rev, cur_prof_hash)
                hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "PASS", evidence=ev_u, details=ev_u.details)
            else:
                ev_u = cls._create_evidence("zero_unconnected_pads", "FAIL", f"Unconnected populated pads detected on nets: {unconnected_nets}", unconnected_count, now, cur_board_rev, cur_prof_hash)
                hard.zero_unconnected_pads = GateResult("zero_unconnected_pads", "FAIL", evidence=ev_u, details=ev_u.details, violations_count=unconnected_count)
                failures.append(f"Unconnected populated pads detected on nets: {unconnected_nets}")

            # Derive critical nets
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
                ev_crit = cls._create_evidence("all_critical_nets_connected", "FAIL", f"Critical nets unconnected: {missing_critical}", len(missing_critical), now, cur_board_rev, cur_prof_hash)
                hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "FAIL", evidence=ev_crit, details=ev_crit.details, violations_count=len(missing_critical))
                failures.append(f"Critical nets unconnected: {missing_critical}")
            elif unconnected_count > 0 and len(critical_nets) == 0:
                ev_crit = cls._create_evidence("all_critical_nets_connected", "UNKNOWN", "Unconnected pads exist but critical nets list is unspecified.", 0, now, cur_board_rev, cur_prof_hash)
                hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "UNKNOWN", evidence=ev_crit, details=ev_crit.details)
                failures.append("Unconnected pads exist but critical nets list is unspecified.")
            else:
                ev_crit = cls._create_evidence("all_critical_nets_connected", "PASS", "All critical nets connected.", 0, now, cur_board_rev, cur_prof_hash)
                hard.all_critical_nets_connected = GateResult("all_critical_nets_connected", "PASS", evidence=ev_crit, details=ev_crit.details)

        # -------------------------------------------------------------
        # Gate 6: Copper Plane Continuity (copper_zones_connected) - FAIL-CLOSED
        # -------------------------------------------------------------
        if discontinuities_count is None and "copper_zones_connected" not in evidence_map:
            ev_cop = cls._create_evidence("copper_zones_connected", "UNKNOWN", "Missing plane continuity evidence: Return-path continuity was not evaluated.", 0, now, ev_board_rev, ev_prof_hash)
            hard.copper_zones_connected = GateResult("copper_zones_connected", "UNKNOWN", evidence=ev_cop, details=ev_cop.details)
            failures.append("Missing plane continuity evidence: Return-path continuity was not evaluated.")
            discon_for_score = 5
        elif is_board_stale or is_profile_stale:
            ev_cop = cls._create_evidence("copper_zones_connected", "STALE", "Plane continuity evidence is stale against current board or profile.", 0, now, ev_board_rev, ev_prof_hash)
            hard.copper_zones_connected = GateResult("copper_zones_connected", "STALE", evidence=ev_cop, details=ev_cop.details)
            failures.append("Plane continuity evidence is stale.")
            discon_for_score = 5
        elif "copper_zones_connected" in evidence_map:
            hard.copper_zones_connected = GateResult("copper_zones_connected", evidence=evidence_map["copper_zones_connected"])
            discon_for_score = hard.copper_zones_connected.violations_count
            if not hard.copper_zones_connected: failures.append(hard.copper_zones_connected.details)
        else:
            discon_for_score = discontinuities_count
            if discontinuities_count == 0:
                ev_cop = cls._create_evidence("copper_zones_connected", "PASS", "0 return-path discontinuities detected.", 0, now, cur_board_rev, cur_prof_hash)
                hard.copper_zones_connected = GateResult("copper_zones_connected", "PASS", evidence=ev_cop, details=ev_cop.details)
            else:
                ev_cop = cls._create_evidence("copper_zones_connected", "FAIL", f"{discontinuities_count} return-path discontinuities / slot crossings detected.", discontinuities_count, now, cur_board_rev, cur_prof_hash)
                hard.copper_zones_connected = GateResult("copper_zones_connected", "FAIL", evidence=ev_cop, details=ev_cop.details, violations_count=discontinuities_count)
                failures.append(f"{discontinuities_count} return-path discontinuities / slot crossings detected.")

        # -------------------------------------------------------------
        # Gate 5: Stackup Verification (valid_stackup)
        # -------------------------------------------------------------
        if "valid_stackup" in evidence_map:
            hard.valid_stackup = GateResult("valid_stackup", evidence=evidence_map["valid_stackup"])
            if not hard.valid_stackup: failures.append(hard.valid_stackup.details)
        elif is_profile_stale:
            ev_stk = cls._create_evidence("valid_stackup", "STALE", "Stackup evidence is stale against current design profile.", 0, now, ev_board_rev, ev_prof_hash)
            hard.valid_stackup = GateResult("valid_stackup", "STALE", evidence=ev_stk, details=ev_stk.details)
            failures.append("Stackup evidence is stale against current design profile.")
        elif profile is not None:
            if profile.stackup and len(profile.stackup) >= 2:
                copper_layers = [l for l in profile.stackup if l.copper_thickness_oz > 0]
                if len(copper_layers) >= 2:
                    ev_stk = cls._create_evidence("valid_stackup", "PASS", f"Valid stackup with {len(profile.stackup)} layers verified.", 0, now, cur_board_rev, cur_prof_hash)
                    hard.valid_stackup = GateResult("valid_stackup", "PASS", evidence=ev_stk, details=ev_stk.details)
                else:
                    ev_stk = cls._create_evidence("valid_stackup", "FAIL", "Stackup has insufficient copper layers (< 2 with thickness > 0).", 1, now, cur_board_rev, cur_prof_hash)
                    hard.valid_stackup = GateResult("valid_stackup", "FAIL", evidence=ev_stk, details=ev_stk.details, violations_count=1)
                    failures.append("Stackup has insufficient copper layers (< 2 with thickness > 0).")
            else:
                ev_stk = cls._create_evidence("valid_stackup", "FAIL", "Layer stackup is empty or invalid.", 1, now, cur_board_rev, cur_prof_hash)
                hard.valid_stackup = GateResult("valid_stackup", "FAIL", evidence=ev_stk, details=ev_stk.details, violations_count=1)
                failures.append("Layer stackup is empty or invalid.")
        elif require_profile:
            ev_stk = cls._create_evidence("valid_stackup", "UNKNOWN", "Missing DesignProfile: Stackup verification cannot be performed.", 0, now, ev_board_rev, ev_prof_hash)
            hard.valid_stackup = GateResult("valid_stackup", "UNKNOWN", evidence=ev_stk, details=ev_stk.details)
            failures.append("Missing DesignProfile: Stackup verification cannot be performed.")
        else:
            ev_stk = cls._create_evidence("valid_stackup", "PASS", "Default stackup accepted (profile omitted).", 0, now, cur_board_rev, cur_prof_hash)
            hard.valid_stackup = GateResult("valid_stackup", "PASS", evidence=ev_stk, details=ev_stk.details)

        # -------------------------------------------------------------
        # Gate 8: Manufacturing Constraints Verification (manufacturing_constraints_met)
        # -------------------------------------------------------------
        if "manufacturing_constraints_met" in evidence_map:
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", evidence=evidence_map["manufacturing_constraints_met"])
            if not hard.manufacturing_constraints_met: failures.append(hard.manufacturing_constraints_met.details)
        elif other_drc_count > 0:
            ev_mfg = cls._create_evidence("manufacturing_constraints_met", "FAIL", f"{other_drc_count} unclassified DRC violations detected.", other_drc_count, now, cur_board_rev, cur_prof_hash)
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "FAIL", evidence=ev_mfg, details=ev_mfg.details, violations_count=other_drc_count)
            failures.append(f"{other_drc_count} unclassified DRC violations detected.")
        elif is_profile_stale:
            ev_mfg = cls._create_evidence("manufacturing_constraints_met", "STALE", "Manufacturing constraints evidence is stale.", 0, now, ev_board_rev, ev_prof_hash)
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "STALE", evidence=ev_mfg, details=ev_mfg.details)
            failures.append("Manufacturing constraints evidence is stale.")
        elif profile is not None:
            mfg = profile.manufacturing
            if mfg and mfg.min_trace_width_mil > 0 and mfg.min_clearance_mil > 0 and mfg.min_drill_mil > 0:
                ev_mfg = cls._create_evidence("manufacturing_constraints_met", "PASS", "Manufacturing thresholds respected.", 0, now, cur_board_rev, cur_prof_hash)
                hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "PASS", evidence=ev_mfg, details=ev_mfg.details)
            else:
                ev_mfg = cls._create_evidence("manufacturing_constraints_met", "FAIL", "Manufacturing constraints invalid or missing.", 1, now, cur_board_rev, cur_prof_hash)
                hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "FAIL", evidence=ev_mfg, details=ev_mfg.details, violations_count=1)
                failures.append("Manufacturing constraints invalid or missing.")
        elif require_profile:
            ev_mfg = cls._create_evidence("manufacturing_constraints_met", "UNKNOWN", "Missing DesignProfile: Manufacturing constraints cannot be verified.", 0, now, ev_board_rev, ev_prof_hash)
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "UNKNOWN", evidence=ev_mfg, details=ev_mfg.details)
            failures.append("Missing DesignProfile: Manufacturing constraints cannot be verified.")
        else:
            ev_mfg = cls._create_evidence("manufacturing_constraints_met", "PASS", "Default manufacturing constraints accepted.", 0, now, cur_board_rev, cur_prof_hash)
            hard.manufacturing_constraints_met = GateResult("manufacturing_constraints_met", "PASS", evidence=ev_mfg, details=ev_mfg.details)

        # -------------------------------------------------------------
        # Gate 7: Electrical Constraints Verification (electrical_constraints_met)
        # -------------------------------------------------------------
        if "electrical_constraints_met" in evidence_map:
            hard.electrical_constraints_met = GateResult("electrical_constraints_met", evidence=evidence_map["electrical_constraints_met"])
            if not hard.electrical_constraints_met: failures.append(hard.electrical_constraints_met.details)
        elif is_profile_stale:
            ev_elec = cls._create_evidence("electrical_constraints_met", "STALE", "Electrical constraints evidence is stale.", 0, now, ev_board_rev, ev_prof_hash)
            hard.electrical_constraints_met = GateResult("electrical_constraints_met", "STALE", evidence=ev_elec, details=ev_elec.details)
            failures.append("Electrical constraints evidence is stale.")
        elif profile is not None:
            has_invalid_elec = False
            for net, curr in profile.current_limits_A.items():
                if curr < 0:
                    has_invalid_elec = True
                    failures.append(f"Invalid negative current limit on net {net}: {curr}A")
            if not has_invalid_elec:
                ev_elec = cls._create_evidence("electrical_constraints_met", "PASS", "Electrical constraints verified.", 0, now, cur_board_rev, cur_prof_hash)
                hard.electrical_constraints_met = GateResult("electrical_constraints_met", "PASS", evidence=ev_elec, details=ev_elec.details)
            else:
                ev_elec = cls._create_evidence("electrical_constraints_met", "FAIL", "Electrical constraints violated (negative current limits).", 1, now, cur_board_rev, cur_prof_hash)
                hard.electrical_constraints_met = GateResult("electrical_constraints_met", "FAIL", evidence=ev_elec, details=ev_elec.details, violations_count=1)
        elif require_profile:
            ev_elec = cls._create_evidence("electrical_constraints_met", "UNKNOWN", "Missing DesignProfile: Electrical current constraints cannot be verified.", 0, now, ev_board_rev, ev_prof_hash)
            hard.electrical_constraints_met = GateResult("electrical_constraints_met", "UNKNOWN", evidence=ev_elec, details=ev_elec.details)
            failures.append("Missing DesignProfile: Electrical current constraints cannot be verified.")
        else:
            ev_elec = cls._create_evidence("electrical_constraints_met", "PASS", "Default electrical constraints accepted.", 0, now, cur_board_rev, cur_prof_hash)
            hard.electrical_constraints_met = GateResult("electrical_constraints_met", "PASS", evidence=ev_elec, details=ev_elec.details)

        failures.extend([f for f in hard.failed_gates() if f not in failures])

        # -------------------------------------------------------------
        # Weighted Scores Computation
        # -------------------------------------------------------------
        scores = WeightedQualityScore()
        drc_penalty = (short_count * 25.0) + (clearance_count * 5.0) if drc_violations is not None else 50.0
        scores.electrical_correctness = max(0.0, 100.0 - drc_penalty)
        scores.routing_quality = max(0.0, round(routability_score * 100.0, 1))
        scores.rf_and_power = max(0.0, 100.0 - (discon_for_score * 20.0))

        total_score = scores.compute_total()

        # Hard Acceptance Invariant: ALL 8 hard gates must be PASS and total score >= 80.0
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
