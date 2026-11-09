"""Subsystem Two: Real Pad Escape Feasibility Engine.
Analyzes fine-pitch component pin fields, escape corridors, adjacent pad spacing,
via accessibility, and neckdown feasibility to classify pad escape difficulty.
Zero external dependencies.
"""
from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from desk.routing.board import BoardPad, BoardIntelligenceEngine


@dataclass
class PadEscapeAnalysis:
    """Detailed escape feasibility assessment for an individual component pad."""
    pad_id: str
    ref: str
    pad_num: str
    net: str
    difficulty: str  # "EASY_ESCAPE", "MODERATE_ESCAPE", "RESTRICTED_ESCAPE", "CRITICAL_ESCAPE", "NO_LEGAL_ESCAPE_FOUND"
    pitch_mil: float
    adjacent_pad_spacing_mil: float
    candidate_layers: List[int]
    legal_escape_directions: List[str]
    available_width_mil: float
    required_clearance_mil: float
    permissible_neckdown_mil: float
    via_candidates: int
    blocking_obstacles: List[str]
    confidence: str = "GEOMETRY_VERIFIED"
    details: str = ""


class PadEscapeEngine:
    """Evaluates escape feasibility for fine-pitch ICs, QFNs, and connectors."""

    CARDINAL_VECTORS = {
        "NORTH": (0.0, 1.0),
        "SOUTH": (0.0, -1.0),
        "EAST": (1.0, 0.0),
        "WEST": (-1.0, 0.0),
        "NORTHEAST": (0.7071, 0.7071),
        "NORTHWEST": (-0.7071, 0.7071),
        "SOUTHEAST": (0.7071, -0.7071),
        "SOUTHWEST": (-0.7071, -0.7071),
    }

    @classmethod
    def evaluate_pad_escape(
        cls,
        pad: BoardPad,
        board: BoardIntelligenceEngine,
        fine_pitch_clearance_mil: float = 4.02,
        min_trace_width_mil: float = 4.0,
        neckdown_min_width_mil: float = 4.0,
        scan_radius_mil: float = 50.0
    ) -> PadEscapeAnalysis:
        """Determines escape feasibility, valid corridor directions, and classifies difficulty."""
        # 1. Query neighboring pads/obstacles on the same layer
        neighbors = board.query_obstacles_near(
            pad.x_mil, pad.y_mil, radius_mil=scan_radius_mil,
            layer=pad.layer if not pad.is_through_hole else 1,
            ignore_net=pad.net
        )

        # Calculate minimum distance to adjacent neighbor (pitch & gap)
        min_edge_gap = float("inf")
        min_center_dist = float("inf")
        for nb in neighbors:
            if isinstance(nb, BoardPad):
                cdist = math.hypot(nb.x_mil - pad.x_mil, nb.y_mil - pad.y_mil)
                if cdist < min_center_dist:
                    min_center_dist = cdist
                # Approximate pad edge gap
                edge_gap = cdist - (max(pad.width_mil, pad.height_mil) / 2.0 + max(nb.width_mil, nb.height_mil) / 2.0)
                if edge_gap < min_edge_gap:
                    min_edge_gap = edge_gap

        if min_center_dist == float("inf"):
            min_center_dist = 100.0  # Isolated pad
            min_edge_gap = 100.0

        pitch_mil = round(min_center_dist, 2)
        spacing_mil = round(max(0.0, min_edge_gap), 2)

        # 2. Test escape corridor in 8 directions
        legal_directions: List[str] = []
        blocking_obs: List[str] = []
        probe_dist = 40.0  # Probe 40 mils outward

        for dname, (vx, vy) in cls.CARDINAL_VECTORS.items():
            probe_x = pad.x_mil + vx * probe_dist
            probe_y = pad.y_mil + vy * probe_dist

            # Check if corridor hits any obstacle within (width/2 + clearance)
            corridor_blocked = False
            for nb in neighbors:
                if isinstance(nb, BoardPad):
                    from desk.routing.connectivity import _dist_point_to_segment
                    d, _, _ = _dist_point_to_segment(nb.x_mil, nb.y_mil, pad.x_mil, pad.y_mil, probe_x, probe_y)
                    nb_radius = max(nb.width_mil, nb.height_mil) / 2.0
                    required_margin = nb_radius + (min_trace_width_mil / 2.0) + fine_pitch_clearance_mil
                    if d < required_margin:
                        corridor_blocked = True
                        if nb.pad_id not in blocking_obs:
                            blocking_obs.append(nb.pad_id)
                        break

            if not corridor_blocked:
                legal_directions.append(dname)

        # 3. Via access evaluation
        via_candidates = 0
        via_diameter = 24.0
        via_radius = via_diameter / 2.0
        # Check if an escape via can be dropped near pad
        for vx, vy in [(-30, 0), (30, 0), (0, -30), (0, 30)]:
            via_x = pad.x_mil + vx
            via_y = pad.y_mil + vy
            can_drop_via = True
            for nb in neighbors:
                if isinstance(nb, BoardPad):
                    d = math.hypot(nb.x_mil - via_x, nb.y_mil - via_y)
                    if d < (max(nb.width_mil, nb.height_mil) / 2.0 + via_radius + fine_pitch_clearance_mil):
                        can_drop_via = False
                        break
            if can_drop_via:
                via_candidates += 1

        # 4. Available width calculation
        max_legal_w = max(0.0, spacing_mil - 2 * fine_pitch_clearance_mil)
        avail_w = round(max(min_trace_width_mil, max_legal_w), 2)

        # 5. Classify escape difficulty
        num_legal = len(legal_directions)
        candidate_layers = list(range(1, len(board.stackup) + 1)) if pad.is_through_hole else [pad.layer]
        if via_candidates > 0 and len(board.stackup) > 1 and not pad.is_through_hole:
            # Can hop to bottom or inner layers
            candidate_layers = list(range(1, len(board.stackup) + 1))

        if num_legal == 0 and via_candidates == 0 and max_legal_w < min_trace_width_mil:
            difficulty = "NO_LEGAL_ESCAPE_FOUND"
            details = f"All 8 directions blocked by neighboring pads {blocking_obs[:4]}. Gap {spacing_mil} mil < required {2*fine_pitch_clearance_mil + min_trace_width_mil} mil."
        elif num_legal <= 1 and via_candidates == 0:
            difficulty = "CRITICAL_ESCAPE"
            details = f"Only {num_legal} legal exit direction ({legal_directions}). No via access."
        elif num_legal <= 2 or spacing_mil < 12.0:
            difficulty = "RESTRICTED_ESCAPE"
            details = f"{num_legal} legal directions. Tight pad spacing ({spacing_mil} mil)."
        elif num_legal <= 4:
            difficulty = "MODERATE_ESCAPE"
            details = f"{num_legal} legal directions available."
        else:
            difficulty = "EASY_ESCAPE"
            details = f"{num_legal} legal exit directions. Ample corridor clearance."

        return PadEscapeAnalysis(
            pad_id=pad.pad_id,
            ref=pad.ref,
            pad_num=pad.pad_num,
            net=pad.net,
            difficulty=difficulty,
            pitch_mil=pitch_mil,
            adjacent_pad_spacing_mil=spacing_mil,
            candidate_layers=candidate_layers,
            legal_escape_directions=legal_directions,
            available_width_mil=avail_w,
            required_clearance_mil=fine_pitch_clearance_mil,
            permissible_neckdown_mil=neckdown_min_width_mil,
            via_candidates=via_candidates,
            blocking_obstacles=blocking_obs,
            confidence="GEOMETRY_VERIFIED",
            details=details
        )
