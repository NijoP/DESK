"""Subsystem Five: Routing Strategy and Topology Selection Engine.
Selects optimal routing strategies per net:
- Strategy A: Two-terminal point-to-point routing
- Strategy B: Multi-terminal Steiner/MST tree routing
- Strategy C: Fine-pitch IC escape-first routing
- Strategy D: Coupled differential-pair routing (impedance & skew matched)
- Strategy E: High-current power trunk routing with neckdowns
- Strategy F: Plane and copper-pour zone stitching
- Strategy G: RF / sensitive analog isolated routing
Zero external dependencies.
"""
from __future__ import annotations
import re
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from desk.routing.board import BoardIntelligenceEngine
from desk.routing.escape import PadEscapeEngine, PadEscapeAnalysis


@dataclass
class NetStrategyAssignment:
    """Strategy assigned to an electrical net with configuration parameters."""
    net_name: str
    strategy_code: str  # "A_TWO_TERMINAL", "B_MULTI_TERMINAL", "C_ESCAPE_FIRST", "D_DIFF_PAIR", "E_POWER_TRUNK", "F_PLANE_STITCH", "G_RF_ISOLATED"
    target_layers: List[int]
    min_width_mil: float
    clearance_mil: float
    is_differential: bool = False
    diff_pair_partner: Optional[str] = None
    target_impedance_ohms: Optional[float] = None
    max_skew_mil: Optional[float] = None
    rationale: str = ""


class RoutingStrategyEngine:
    """Classifies and assigns execution strategies based on physical and electrical constraints."""

    @classmethod
    def assign_strategy(
        cls,
        net_name: str,
        board: BoardIntelligenceEngine,
        diff_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
        high_current: Optional[Dict[str, float]] = None,
        profile: Optional[Any] = None
    ) -> NetStrategyAssignment:
        """Determines the appropriate routing strategy for a specific net."""
        diff_pairs = diff_pairs or {}
        high_current = high_current or {}

        pads = board.net_pads.get(net_name, [])
        pin_count = len(pads)

        # 1. Check Differential Pair (Strategy D)
        for dp_name, (pos_net, neg_net) in diff_pairs.items():
            if net_name == pos_net:
                return NetStrategyAssignment(
                    net_name=net_name,
                    strategy_code="D_DIFF_PAIR",
                    target_layers=[1, len(board.stackup)],  # Outer microstrip preferred
                    min_width_mil=6.0,
                    clearance_mil=6.0,
                    is_differential=True,
                    diff_pair_partner=neg_net,
                    target_impedance_ohms=90.0,
                    max_skew_mil=5.0,
                    rationale=f"Coupled differential pair '{dp_name}' (positive leg)"
                )
            elif net_name == neg_net:
                return NetStrategyAssignment(
                    net_name=net_name,
                    strategy_code="D_DIFF_PAIR",
                    target_layers=[1, len(board.stackup)],
                    min_width_mil=6.0,
                    clearance_mil=6.0,
                    is_differential=True,
                    diff_pair_partner=pos_net,
                    target_impedance_ohms=90.0,
                    max_skew_mil=5.0,
                    rationale=f"Coupled differential pair '{dp_name}' (negative leg)"
                )

        # 2. Check RF / Sensitive Analog (Strategy G)
        if profile and hasattr(profile, "rf_nets") and net_name in profile.rf_nets:
            rf_cfg = profile.rf_nets[net_name]
            return NetStrategyAssignment(
                net_name=net_name,
                strategy_code="G_RF_ISOLATED",
                target_layers=[1],  # Top layer only over unbroken ground plane
                min_width_mil=rf_cfg.trace_width_mil,
                clearance_mil=rf_cfg.ground_clearance_mil,
                rationale="RF high-frequency transmission line with continuous reference plane"
            )

        # 3. Check Ground / Plane Connectivity (Strategy F)
        if re.search(r"^(GND|VSS|AGND|DGND|PGND)$", net_name, re.I):
            return NetStrategyAssignment(
                net_name=net_name,
                strategy_code="F_PLANE_STITCH",
                target_layers=[2] if len(board.stackup) >= 4 else [1, 2],
                min_width_mil=12.0,
                clearance_mil=6.0,
                rationale="System ground return: prioritize plane access vias and thermal relief"
            )

        # 4. Check High-Current Power (Strategy E)
        is_pwr = bool(re.search(r"^(VCC|VDD|3V3|5V|1V8|VBAT|VSYS|VBUS)", net_name, re.I)) or (net_name in high_current)
        if is_pwr:
            cur_A = high_current.get(net_name, 1.0)
            from desk.routing.width import TraceWidthManager
            trunk_w = TraceWidthManager.calculate_ipc2152_width(cur_A, is_inner=False)
            return NetStrategyAssignment(
                net_name=net_name,
                strategy_code="E_POWER_TRUNK",
                target_layers=[1, 2] if len(board.stackup) <= 2 else [1, 4, 3],
                min_width_mil=trunk_w,
                clearance_mil=6.0,
                rationale=f"Power delivery trunk ({cur_A}A) requiring decoupled escape and post-import widening"
            )

        # 5. Check Fine-Pitch Escape Constrained (Strategy C)
        has_critical_escape = False
        for p in pads:
            analysis = PadEscapeEngine.evaluate_pad_escape(p, board)
            if analysis.difficulty in ("CRITICAL_ESCAPE", "NO_LEGAL_ESCAPE_FOUND", "RESTRICTED_ESCAPE"):
                has_critical_escape = True
                break

        if has_critical_escape:
            return NetStrategyAssignment(
                net_name=net_name,
                strategy_code="C_ESCAPE_FIRST",
                target_layers=list(range(1, len(board.stackup) + 1)),
                min_width_mil=5.0,
                clearance_mil=4.02,
                rationale="Fine-pitch IC pad escape required before routing channels are congested"
            )

        # 6. Check Multi-Terminal (Strategy B) vs Simple Two-Terminal (Strategy A)
        if pin_count > 2:
            return NetStrategyAssignment(
                net_name=net_name,
                strategy_code="B_MULTI_TERMINAL",
                target_layers=list(range(1, len(board.stackup) + 1)),
                min_width_mil=5.0,
                clearance_mil=4.02,
                rationale=f"Multi-terminal net ({pin_count} pins) routed via Minimum Spanning Tree"
            )

        return NetStrategyAssignment(
            net_name=net_name,
            strategy_code="A_TWO_TERMINAL",
            target_layers=[1, len(board.stackup)],
            min_width_mil=5.0,
            clearance_mil=4.02,
            rationale="Standard point-to-point signal"
        )
