"""Subsystem Eight: Proper Trace Width, Escape Neckdown, and Safe Widening Engine.
Solves the conflict between IPC-2152 high-current power trunk widths and fine-pitch IC escapes.
Decouples router escape widths in DSN from post-routing trunk widening, verifying clearance
along the entire widened envelope before any copper is modified.
Zero external dependencies.
"""
from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field


@dataclass
class WideningCandidate:
    """Represents a track segment evaluated for heavy-copper trunk widening."""
    segment_id: str
    net: str
    layer: int
    x1: float
    y1: float
    x2: float
    y2: float
    length_mil: float
    current_width_mil: float
    target_width_mil: float
    approved_width_mil: float
    is_widened: bool
    is_escape_neckdown: bool
    restriction_reason: Optional[str] = None
    min_observed_clearance_mil: float = 0.0


@dataclass
class WidthWideningPlan:
    """Complete plan for post-routing power trace widening with clearance proofs."""
    net_name: str
    target_trunk_width_mil: float
    escape_neckdown_width_mil: float
    total_segments: int
    widened_segments: int
    preserved_escape_segments: int
    constrained_segments: int
    candidates: List[WideningCandidate]
    safety_summary: str


class TraceWidthManager:
    """Derives physical trace widths and executes clearance-safe post-routing widening."""

    @staticmethod
    def calculate_ipc2152_width(
        current_A: float,
        is_inner: bool = False,
        copper_oz: float = 1.0,
        temp_rise_C: float = 10.0
    ) -> float:
        """Calculates required trace width in mils using the IPC-2221 power-law formula.
        Note: the function name says 2152 for API compatibility; the constants below are IPC-2221
        (k = 0.048 external / 0.024 internal). IPC-2152 chart data is not implemented (roadmap H-10).
        A = (I / (k * delta_T^b))^(1 / c)
        where k = 0.048 for outer, 0.024 for inner.
        """
        if current_A <= 0.0:
            return 6.0

        k = 0.024 if is_inner else 0.048
        b = 0.44
        c = 0.725

        denom = k * (temp_rise_C ** b)
        if denom <= 0:
            return 10.0

        area_sq_mils = (current_A / denom) ** (1.0 / c)
        # Copper thickness in mils (1 oz = 1.37 mil)
        thickness_mil = copper_oz * 1.37
        width_mil = area_sq_mils / max(0.5, thickness_mil)
        return max(5.0, round(width_mil, 2))

    @staticmethod
    def calculate_max_legal_escape_width(
        pad_pitch_mil: float,
        pad_width_mil: float,
        clearance_mil: float = 4.02
    ) -> float:
        """Determines the maximum trace width that can exit a fine-pitch pad without collision."""
        if pad_pitch_mil <= 0:
            return 10.0

        # Available space between adjacent pad boundaries: pitch - pad_width
        pad_gap_mil = pad_pitch_mil - pad_width_mil
        # Trace must maintain clearance_mil on both sides to neighboring pads
        max_trace_w = pad_gap_mil - 2 * clearance_mil
        # Clamp to realistic bounds
        return max(4.0, round(max_trace_w, 2))

    @classmethod
    def plan_power_widening(
        cls,
        net_name: str,
        segments: List[Dict[str, Any]],
        target_width_mil: float,
        escape_width_mil: float = 10.0,
        fine_pitch_pads: Optional[List[Tuple[float, float, float]]] = None,  # (x, y, radius)
        obstacles: Optional[List[Tuple[float, float, float, float, int]]] = None,  # (x1, y1, x2, y2, layer)
        min_clearance_mil: float = 4.02,
        escape_radius_mil: float = 35.0
    ) -> WidthWideningPlan:
        """Evaluates every track segment of a power net, identifying trunk segments
        that can safely widen to target_width_mil without violating clearance.
        """
        fine_pitch_pads = fine_pitch_pads or []
        obstacles = obstacles or []

        candidates: List[WideningCandidate] = []
        widened_count = 0
        escape_count = 0
        constrained_count = 0

        for i, s in enumerate(segments):
            seg_id = s.get("id", f"seg_{i}")
            x1 = float(s.get("start_x", s.get("x1", 0.0)))
            y1 = float(s.get("start_y", s.get("y1", 0.0)))
            x2 = float(s.get("end_x", s.get("x2", 0.0)))
            y2 = float(s.get("end_y", s.get("y2", 0.0)))
            w_cur = float(s.get("width", escape_width_mil))
            layer = int(s.get("layer", 1))
            length = math.hypot(x2 - x1, y2 - y1)

            # Check if segment touches or is inside a fine-pitch IC escape zone
            is_near_fine_pitch = False
            for px, py, prad in fine_pitch_pads:
                d1 = math.hypot(x1 - px, y1 - py)
                d2 = math.hypot(x2 - px, y2 - py)
                if min(d1, d2) <= (prad + escape_radius_mil):
                    is_near_fine_pitch = True
                    break

            if is_near_fine_pitch:
                # Must remain narrow to prevent QFN/BGA maze collapse
                candidates.append(WideningCandidate(
                    segment_id=seg_id,
                    net=net_name,
                    layer=layer,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    length_mil=round(length, 2),
                    current_width_mil=w_cur,
                    target_width_mil=target_width_mil,
                    approved_width_mil=escape_width_mil,
                    is_widened=False,
                    is_escape_neckdown=True,
                    restriction_reason="Fine-pitch pad escape zone clearance protection"
                ))
                escape_count += 1
                continue

            # Check clearance for proposed target_width_mil
            # Proposed half-width increase:
            delta_half = (target_width_mil - w_cur) / 2.0
            required_clear_envelope = delta_half + min_clearance_mil

            min_dist_to_obstacle = float("inf")
            for ox1, oy1, ox2, oy2, olay in obstacles:
                if olay != layer:
                    continue
                # Bounding box test
                if (max(x1, x2) + required_clear_envelope < min(ox1, ox2) or
                    max(ox1, ox2) + required_clear_envelope < min(x1, x2) or
                    max(y1, y2) + required_clear_envelope < min(oy1, oy2) or
                    max(oy1, oy2) + required_clear_envelope < min(y1, y2)):
                    continue

                # Detailed segment distance
                from desk.routing.connectivity import _dist_point_to_segment
                d_a, _, _ = _dist_point_to_segment(x1, y1, ox1, oy1, ox2, oy2)
                d_b, _, _ = _dist_point_to_segment(x2, y2, ox1, oy1, ox2, oy2)
                d_c, _, _ = _dist_point_to_segment(ox1, oy1, x1, y1, x2, y2)
                d_d, _, _ = _dist_point_to_segment(ox2, oy2, x1, y1, x2, y2)
                min_obs_d = min(d_a, d_b, d_c, d_d)
                if min_obs_d < min_dist_to_obstacle:
                    min_dist_to_obstacle = min_obs_d

            # Decision: can it widen fully, partially, or not at all?
            if min_dist_to_obstacle >= required_clear_envelope:
                # Fully approved
                candidates.append(WideningCandidate(
                    segment_id=seg_id,
                    net=net_name,
                    layer=layer,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    length_mil=round(length, 2),
                    current_width_mil=w_cur,
                    target_width_mil=target_width_mil,
                    approved_width_mil=target_width_mil,
                    is_widened=True,
                    is_escape_neckdown=False,
                    min_observed_clearance_mil=round(min_dist_to_obstacle, 2)
                ))
                widened_count += 1
            else:
                # Calculate maximum safe width without violating min_clearance_mil
                available_space = min_dist_to_obstacle - min_clearance_mil
                safe_w = max(w_cur, w_cur + 2 * max(0.0, available_space))
                safe_w = round(min(target_width_mil, safe_w), 1)

                if safe_w > w_cur:
                    candidates.append(WideningCandidate(
                        segment_id=seg_id,
                        net=net_name,
                        layer=layer,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        length_mil=round(length, 2),
                        current_width_mil=w_cur,
                        target_width_mil=target_width_mil,
                        approved_width_mil=safe_w,
                        is_widened=True,
                        is_escape_neckdown=False,
                        restriction_reason=f"Partial widening: constrained to {safe_w} mil by adjacent copper",
                        min_observed_clearance_mil=round(min_dist_to_obstacle, 2)
                    ))
                    widened_count += 1
                else:
                    candidates.append(WideningCandidate(
                        segment_id=seg_id,
                        net=net_name,
                        layer=layer,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        length_mil=round(length, 2),
                        current_width_mil=w_cur,
                        target_width_mil=target_width_mil,
                        approved_width_mil=w_cur,
                        is_widened=False,
                        is_escape_neckdown=False,
                        restriction_reason=f"Clearance boundary: obstacle within {min_dist_to_obstacle:.2f} mil",
                        min_observed_clearance_mil=round(min_dist_to_obstacle, 2)
                    ))
                    constrained_count += 1

        summary = (
            f"Power Widening for '{net_name}': {widened_count}/{len(segments)} segments widened to target/safe width. "
            f"{escape_count} preserved at escape neckdown, {constrained_count} constrained by clearance."
        )

        return WidthWideningPlan(
            net_name=net_name,
            target_trunk_width_mil=target_width_mil,
            escape_neckdown_width_mil=escape_width_mil,
            total_segments=len(segments),
            widened_segments=widened_count,
            preserved_escape_segments=escape_count,
            constrained_segments=constrained_count,
            candidates=candidates,
            safety_summary=summary
        )
