"""Subsystem Three: Adaptive Routing Priority Engine.
Replaces static regex naming priorities with dynamic constrainedness scoring:
Priority = Criticality + EscapeDifficulty + CongestionRisk + LayerScarcity + TopologyComplexity + ConstraintUrgency
Zero external dependencies.
"""
from __future__ import annotations
import re
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from desk.routing.board import BoardIntelligenceEngine
from desk.routing.escape import PadEscapeEngine, PadEscapeAnalysis


@dataclass
class NetPriorityScore:
    """Comprehensive priority breakdown for an individual routing unit."""
    net_name: str
    total_priority: float
    stage: int  # 1 to 6
    criticality_score: float
    escape_difficulty_score: float
    congestion_risk_score: float
    layer_scarcity_score: float
    topology_complexity_score: float
    constraint_urgency_score: float
    is_differential_pair: bool = False
    is_power: bool = False
    is_ground: bool = False
    requires_plane_connection_only: bool = False
    details: str = ""


class AdaptivePriorityEngine:
    """Calculates multidimensional constrainedness scores and orders routing dispatch."""

    WEIGHTS = {
        "criticality": 3.0,
        "escape_difficulty": 2.5,
        "congestion_risk": 1.5,
        "layer_scarcity": 2.0,
        "topology_complexity": 1.0,
        "constraint_urgency": 2.0
    }

    @classmethod
    def score_all_nets(
        cls,
        board: BoardIntelligenceEngine,
        diff_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
        high_current: Optional[Dict[str, float]] = None,
        profile: Optional[Any] = None,
        custom_weights: Optional[Dict[str, float]] = None
    ) -> List[NetPriorityScore]:
        """Calculates dynamic priority score for every net on the board."""
        weights = dict(cls.WEIGHTS)
        if custom_weights:
            weights.update(custom_weights)

        diff_pairs = diff_pairs or {}
        high_current = high_current or {}
        diff_pair_nets = {p[0] for p in diff_pairs.values()} | {p[1] for p in diff_pairs.values()}

        # 1. Evaluate pad escape difficulties across the entire board
        escape_map: Dict[str, List[PadEscapeAnalysis]] = {}
        for net_name, pads in board.net_pads.items():
            escape_map[net_name] = []
            for pad in pads:
                analysis = PadEscapeEngine.evaluate_pad_escape(pad, board)
                escape_map[net_name].append(analysis)

        scores: List[NetPriorityScore] = []

        for net_name, pads in board.net_pads.items():
            if len(pads) < 2:
                continue

            is_dp = net_name in diff_pair_nets
            is_gnd = bool(re.search(r"^(GND|VSS|AGND|DGND|PGND)$", net_name, re.I))
            is_pwr = bool(re.search(r"^(VCC|VDD|3V3|5V|1V8|VBAT|VSYS|VBUS)", net_name, re.I)) or (net_name in high_current)

            # A. Criticality Score (0.0 to 10.0)
            if is_dp:
                crit = 10.0
            elif profile and hasattr(profile, "rf_nets") and net_name in profile.rf_nets:
                crit = 9.5
            elif is_gnd:
                crit = 7.0
            elif is_pwr:
                crit = 8.0
            else:
                crit = 4.0

            # B. Escape Difficulty Score (0.0 to 10.0)
            pad_analyses = escape_map.get(net_name, [])
            worst_escape = "EASY_ESCAPE"
            diff_score = 1.0
            diff_weights = {
                "NO_LEGAL_ESCAPE_FOUND": 10.0,
                "CRITICAL_ESCAPE": 8.5,
                "RESTRICTED_ESCAPE": 6.0,
                "MODERATE_ESCAPE": 3.0,
                "EASY_ESCAPE": 1.0
            }
            for pa in pad_analyses:
                sc = diff_weights.get(pa.difficulty, 1.0)
                if sc > diff_score:
                    diff_score = sc
                    worst_escape = pa.difficulty

            # C. Layer Scarcity (0.0 to 10.0)
            # If net is constrained to a specific layer
            layer_scarcity = 2.0
            if is_dp or (profile and hasattr(profile, "rf_nets") and net_name in profile.rf_nets):
                layer_scarcity = 8.0  # Must stay on reference-adjacent layer

            # D. Topology Complexity (0.0 to 10.0)
            terminal_count = len(pads)
            if terminal_count > 10:
                topo = 8.0
            elif terminal_count > 4:
                topo = 5.0
            else:
                topo = 2.0

            # E. Congestion Risk (0.0 to 10.0)
            # Higher if multiple pins are located in dense IC clusters
            congestion_risk = 3.0
            if any(pa.adjacent_pad_spacing_mil < 15.0 for pa in pad_analyses):
                congestion_risk = 7.5

            # F. Constraint Urgency (0.0 to 10.0)
            urgency = 5.0
            if net_name in high_current and high_current[net_name] > 1.5:
                urgency = 9.0

            # Compute weighted total
            total_priority = (
                weights["criticality"] * crit +
                weights["escape_difficulty"] * diff_score +
                weights["congestion_risk"] * congestion_risk +
                weights["layer_scarcity"] * layer_scarcity +
                weights["topology_complexity"] * topo +
                weights["constraint_urgency"] * urgency
            )

            # Map to 6 Priority Stages
            if is_gnd:
                stage = 1
            elif diff_score >= 8.5 or any(pa.difficulty in ("CRITICAL_ESCAPE", "NO_LEGAL_ESCAPE_FOUND") for pa in pad_analyses):
                stage = 2  # Escape-constrained nets scheduled early before exits consumed
            elif is_dp or crit >= 9.0:
                stage = 3  # Critical high-speed signals
            elif is_pwr:
                stage = 5  # Power distribution
            elif terminal_count <= 3 and diff_score <= 3.0:
                stage = 6  # Easy non-critical signals
            else:
                stage = 4  # Standard digital control signals

            scores.append(NetPriorityScore(
                net_name=net_name,
                total_priority=round(total_priority, 2),
                stage=stage,
                criticality_score=crit,
                escape_difficulty_score=diff_score,
                congestion_risk_score=congestion_risk,
                layer_scarcity_score=layer_scarcity,
                topology_complexity_score=topo,
                constraint_urgency_score=urgency,
                is_differential_pair=is_dp,
                is_power=is_pwr,
                is_ground=is_gnd,
                details=f"Worst escape: {worst_escape}, Pins: {terminal_count}"
            ))

        # Sort descending by total priority
        scores.sort(key=lambda s: s.total_priority, reverse=True)
        return scores
