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
        from desk import ipc
        if current_A <= 0.0:
            # Placeholder for segments whose net has no declared current. Sizing decisions for
            # such nets are blocked upstream (DesignProfile.validate_electrical_inputs, H-02).
            return 6.0
        return round(max(5.0, ipc.trace_width_mil(current_A, is_inner=is_inner, copper_oz=copper_oz,
                                                  temp_rise_c=temp_rise_C)), 2)

        k = 0.024 if is_inner else 0.048  # pragma: no cover (legacy path retained for reference)
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
        obstacles: Optional[List[Tuple[float, ...]]] = None,  # (x1, y1, x2, y2, layer[, width[, clearance]])
        min_clearance_mil: float = 4.02,
        escape_radius_mil: float = 35.0,
        default_obstacle_width_mil: Optional[float] = None,
    ) -> WidthWideningPlan:
        """Evaluates every track segment of a power net, identifying trunk segments
        that can safely widen to target_width_mil without violating clearance.

        Obstacles are other-net copper: a track (x1, y1, x2, y2, layer, width) or a pad/via given as a zero-length
        segment whose width is its enclosing diameter. The copper gap is the centreline distance minus BOTH
        half-widths, so the widened segment needs centreline distance >= target/2 + obstacle_width/2 + clearance
        (E-3: the old test compared the centreline distance with only the width increase and approved 0 mil gaps).
        An obstacle's optional 7th field is its own net's clearance; the larger of it and `min_clearance_mil`
        applies. Obstacles without a width are taken as `default_obstacle_width_mil` (default: escape_width_mil,
        the widest track the router is given for non-widened nets).
        """
        from desk.routing.padgeom import segment_segment_distance
        fine_pitch_pads = fine_pitch_pads or []
        obstacles = obstacles or []
        default_ow = float(escape_width_mil if default_obstacle_width_mil is None else default_obstacle_width_mil)

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

            # Clearance for the proposed target width: the room each obstacle leaves for the widened half-width.
            half_room = float("inf")       # largest half-width this segment may take
            edge = float("inf")            # nearest other-net copper edge from this centreline
            for ob in obstacles:
                ox1, oy1, ox2, oy2, olay = ob[:5]
                if int(olay) != layer:
                    continue
                ow = float(ob[5]) if len(ob) > 5 and ob[5] is not None else default_ow
                oclr = max(min_clearance_mil, float(ob[6])) if len(ob) > 6 and ob[6] is not None else min_clearance_mil
                reach = target_width_mil / 2.0 + ow / 2.0 + oclr
                # Bounding box test
                if (max(x1, x2) + reach < min(ox1, ox2) or
                    max(ox1, ox2) + reach < min(x1, x2) or
                    max(y1, y2) + reach < min(oy1, oy2) or
                    max(oy1, oy2) + reach < min(y1, y2)):
                    continue
                d = segment_segment_distance((x1, y1), (x2, y2), (ox1, oy1), (ox2, oy2))
                half_room = min(half_room, d - ow / 2.0 - oclr)
                edge = min(edge, d - ow / 2.0)

            max_safe_w = 2.0 * half_room
            if max_safe_w >= target_width_mil:
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
                    min_observed_clearance_mil=round(edge - target_width_mil / 2.0, 2)
                ))
                widened_count += 1
            else:
                # Largest width that keeps every gap (rounded DOWN to 0.1 mil so rounding never eats the clearance)
                safe_w = math.floor(min(target_width_mil, max_safe_w) * 10.0 + 1e-9) / 10.0

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
                        min_observed_clearance_mil=round(edge - safe_w / 2.0, 2)
                    ))
                    widened_count += 1
                else:
                    gap_now = edge - w_cur / 2.0
                    reason = f"Clearance boundary: adjacent copper leaves {max(0.0, max_safe_w):.2f} mil of width"
                    if half_room < w_cur / 2.0 - 1e-6:
                        reason += f" (routed gap already {gap_now:.2f} mil, below the clearance rule)"
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
                        restriction_reason=reason,
                        min_observed_clearance_mil=round(gap_now, 2)
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


def plan_board_widening(
    widen_targets: Dict[str, float],
    lines: List[Dict[str, Any]],
    vias: Optional[List[Dict[str, Any]]] = None,
    pcb_dump: Optional[Dict[str, Any]] = None,
    net_clearances_mil: Optional[Dict[str, float]] = None,
    fab_min_clearance_mil: float = 4.02,
    escape_width_mil: float = 10.0,
    fine_pitch_pads: Optional[List[Tuple[float, float, float]]] = None,
    escape_radius_mil: float = 35.0,
) -> Dict[str, WidthWideningPlan]:
    """Widening plans for every target net against ALL other-net copper (E-3).

    Obstacles of net N: every other net's track at its readback width (or at the width already approved for an
    earlier widened net, so two power trunks are never widened into each other), every other-net via at its
    diameter and every other-net pad from the PCB dump as its enclosing circle. The clearance for a pair is the
    larger of the two nets' routing rules (never below the fabricator minimum), not a literal."""
    rules = dict(net_clearances_mil or {})

    def rule(net: str) -> float:
        return max(fab_min_clearance_mil, float(rules.get(net, fab_min_clearance_mil)))

    widths: Dict[str, float] = {}
    for i, l in enumerate(lines):
        widths[str(l.get("id", f"line_{i}"))] = float(l.get("width", escape_width_mil) or escape_width_mil)

    pad_obs: List[Tuple[str, float, float, float, Optional[int]]] = []   # (net, x, y, diameter, layer or None=all)
    if pcb_dump:
        from desk.routing.padgeom import pad_shape
        for comp in pcb_dump.values():
            if not isinstance(comp, dict):
                continue
            for p in comp.get("pads", []):
                g = pad_shape(comp, p)
                lay = p.get("layer", comp.get("layer", 1))
                pad_obs.append(((p.get("net") or "").strip(), g.cx, g.cy, 2.0 * g.bounding_radius,
                                None if lay in (11, 12) else int(lay)))

    plans: Dict[str, WidthWideningPlan] = {}
    for net, target in widen_targets.items():
        own = [l for l in lines if l.get("net") == net]
        layers = {int(l.get("layer", 1)) for l in own}
        obstacles: List[Tuple[float, ...]] = []
        for i, l in enumerate(lines):
            if l.get("net") == net:
                continue
            obstacles.append((float(l["start_x"]), float(l["start_y"]), float(l["end_x"]), float(l["end_y"]),
                              int(l.get("layer", 1)), widths[str(l.get("id", f"line_{i}"))], rule(l.get("net") or "")))
        for v in vias or []:
            if v.get("net") == net:
                continue
            d = float(v.get("diameter", v.get("size", 24.0)) or 24.0)
            for lay in layers:
                obstacles.append((float(v["x"]), float(v["y"]), float(v["x"]), float(v["y"]), lay, d, rule(v.get("net") or "")))
        for pnet, x, y, d, lay in pad_obs:
            if pnet == net:
                continue
            for olay in ([lay] if lay is not None else sorted(layers)):
                obstacles.append((x, y, x, y, olay, d, rule(pnet)))
        plan = TraceWidthManager.plan_power_widening(
            net_name=net, segments=own, target_width_mil=target, escape_width_mil=escape_width_mil,
            fine_pitch_pads=fine_pitch_pads, obstacles=obstacles, min_clearance_mil=rule(net),
            escape_radius_mil=escape_radius_mil)
        for c in plan.candidates:
            if c.is_widened:
                widths[c.segment_id] = c.approved_width_mil
        plans[net] = plan
    return plans


def widening_shortfall(plans: Dict[str, WidthWideningPlan]) -> Dict[str, int]:
    """Segments per net left below the target width by clearance (escape neckdowns are intentional, not counted)."""
    out: Dict[str, int] = {}
    for net, plan in plans.items():
        n = sum(1 for c in plan.candidates
                if not c.is_escape_neckdown and c.approved_width_mil + 1e-6 < c.target_width_mil)
        if n:
            out[net] = n
    return out
