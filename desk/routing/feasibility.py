"""Routing feasibility before the engine starts: can every net's rule be met at its own pads at all?

UPS_1000 ran six engine attempts (31 minutes of a 65 minute budget) against a board whose spacing rules could not be
satisfied at the pads of two 1.27 mm-pitch packages, and the structural pre-flight said `passed: true`. This module
evaluates each pad against the clearance rule of ITS net, measures the real copper gap to the nearest pad of another
net (axis-aware rectangles, not circles), and classifies every pad:

    LEGAL_AND_ROUTABLE               gap leaves room for the rule and a trace
    ROUTABLE_WITH_PLACEMENT_CHANGE   gap below the rule only because of a neighbouring component (not the package)
    ROUTABLE_WITH_LAYER_CHANGE       through-hole / plane-net pad that escapes on another layer
    ROUTABLE_WITH_POWER_POLYGON      power net whose rule fails only against its own plane / polygon candidates
    BLOCKED_BY_CLEARANCE             the net's own rule exceeds the package pin-field gap: no trace can ever exist
    BLOCKED_BY_KEEP_OUT              pad centre inside a routing keep-out for its side
    BLOCKED_BY_PACKAGE_GEOMETRY      even the fabricator minimum does not fit between neighbouring pads
    BLOCKED_BY_STACKUP               no routable signal layer for this pad's side
    UNKNOWN                          geometry missing in the dump

The report names pad, component, net, rule (mil and mm), gap and the neighbour, so the human decision is concrete.
A BLOCKED_BY_CLEARANCE pad never lowers the rule; it produces an `EngineeringDecision` (desk.spacing) and blocks
the engine run until the Captain approves one of the options.

Zero external dependencies.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from desk.routing.connectivity import pad_xy, pad_size_mil
from desk import spacing as SP

MIL = 39.37007874
CLASSES = ("LEGAL_AND_ROUTABLE", "ROUTABLE_WITH_PLACEMENT_CHANGE", "ROUTABLE_WITH_LAYER_CHANGE", "ROUTABLE_WITH_POWER_POLYGON",
           "BLOCKED_BY_CLEARANCE", "BLOCKED_BY_KEEP_OUT", "BLOCKED_BY_PACKAGE_GEOMETRY", "BLOCKED_BY_STACKUP", "UNKNOWN")


@dataclass
class PadFeasibility:
    pad_id: str
    ref: str
    pad_num: str
    net: str
    classification: str
    rule_mil: float
    gap_mil: Optional[float]
    neighbour: str = ""
    neighbour_net: str = ""
    same_component: bool = True
    detail: str = ""

    @property
    def rule_mm(self) -> float:
        return round(self.rule_mil / MIL, 4)

    @property
    def gap_mm(self) -> Optional[float]:
        return None if self.gap_mil is None else round(self.gap_mil / MIL, 4)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["rule_mm"], d["gap_mm"] = self.rule_mm, self.gap_mm
        return d


@dataclass
class FeasibilityReport:
    feasible: bool
    pads_checked: int
    classes: Dict[str, int]
    blocked: List[PadFeasibility]
    decisions: List[SP.EngineeringDecision]
    routable_layers: List[int]
    signal_layers: List[str]
    plane_layers: List[str]
    total_connections: int
    unrouted_connections: int
    summary: str
    analysis_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"feasible": self.feasible, "pads_checked": self.pads_checked, "classes": dict(self.classes),
                "blocked": [b.to_dict() for b in self.blocked[:200]], "decisions": [d.to_dict() for d in self.decisions],
                "routable_layers": list(self.routable_layers), "signal_layers": list(self.signal_layers),
                "plane_layers": list(self.plane_layers), "total_connections": self.total_connections,
                "unrouted_connections": self.unrouted_connections, "summary": self.summary, "analysis_ms": self.analysis_ms,
                "warnings": list(self.warnings)}


@dataclass
class _Pad:
    pad_id: str
    ref: str
    num: str
    net: str
    x: float
    y: float
    w: float
    h: float
    side: str          # "T" | "B" | "TH"


def _pads(dump: Dict[str, Any], origin_mm: Tuple[float, float]) -> List[_Pad]:
    out: List[_Pad] = []
    for ref, comp in dump.items():
        if not isinstance(comp, dict):
            continue
        side = "T" if int(comp.get("layer", 1)) == 1 else "B"
        for p in comp.get("pads", []):
            ax, ay = pad_xy(comp, p)
            w, h = pad_size_mil(p)
            th = p.get("layer") in (11, 12) or bool(p.get("hole"))
            out.append(_Pad(f"{ref}.{p.get('num', '')}", ref, str(p.get("num", "")), (p.get("net") or "").strip(),
                            ax, ay, float(w), float(h), "TH" if th else side))
    return out


def rect_gap_mil(a: _Pad, b: _Pad) -> float:
    """Copper gap between two axis-aligned rectangular pads (0 when they overlap)."""
    gx = abs(a.x - b.x) - (a.w + b.w) / 2.0
    gy = abs(a.y - b.y) - (a.h + b.h) / 2.0
    if gx > 0 and gy > 0:
        return math.hypot(gx, gy)
    return max(gx, gy, 0.0)


def _in_keepout(p: _Pad, keepouts: Sequence[Dict[str, Any]], origin_mm: Tuple[float, float]) -> Optional[str]:
    ox, oy = origin_mm
    px, py = p.x / MIL - ox, p.y / MIL - oy
    for ko in keepouts or []:
        if p.ref in (ko.get("allow") or []):
            continue
        ks = ko.get("side", "both")
        if not (ks == "both" or p.side == "TH" or ks == p.side):
            continue
        r = ko.get("rect_mm")
        if r and r[0] <= px <= r[2] and r[1] <= py <= r[3]:
            return str(ko.get("name", "?"))
    return None


def evaluate(dump: Dict[str, Any], net_rules_mil: Dict[str, float], fab_min_mil: float, min_trace_mil: float = 4.0,
             stackup: Optional[Sequence[str]] = None, plane_layers: Optional[Dict[int, str]] = None,
             route_keepouts: Optional[Sequence[Dict[str, Any]]] = None, origin_mm: Tuple[float, float] = (0.0, 0.0),
             power_nets: Optional[Sequence[str]] = None, scan_radius_mil: float = 120.0,
             rule_source: str = "DesignProfile.derive_clearance_mil") -> FeasibilityReport:
    """Classify every pad whose net has a rule above the fabricator minimum (and every pad against the fab minimum)."""
    t0 = time.perf_counter()
    pads = _pads(dump, origin_mm)
    stack = list(stackup or ["Top", "Bottom"])
    planes = dict(plane_layers or {})
    routable = [i for i in range(1, len(stack) + 1) if i not in planes]
    power = set(power_nets or [])
    counts: Dict[str, int] = {c: 0 for c in CLASSES}
    blocked: List[PadFeasibility] = []
    warnings: List[str] = []
    decisions: Dict[str, SP.EngineeringDecision] = {}
    pads_by_net_conflict: Dict[str, List[Tuple[str, float, float]]] = {}

    # coarse spatial grid for neighbour queries
    cell = max(50.0, scan_radius_mil)
    grid: Dict[Tuple[int, int], List[_Pad]] = {}
    for p in pads:
        grid.setdefault((int(p.x // cell), int(p.y // cell)), []).append(p)

    def neighbours(p: _Pad):
        cx, cy = int(p.x // cell), int(p.y // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in grid.get((cx + dx, cy + dy), []):
                    if q is p or (q.net and q.net == p.net):
                        continue
                    if p.side != "TH" and q.side != "TH" and q.side != p.side:
                        continue
                    yield q

    for p in pads:
        rule = float(net_rules_mil.get(p.net, fab_min_mil) if p.net else fab_min_mil)
        rule = max(rule, fab_min_mil)
        ko = _in_keepout(p, route_keepouts or [], origin_mm)
        if ko:
            counts["BLOCKED_BY_KEEP_OUT"] += 1
            blocked.append(PadFeasibility(p.pad_id, p.ref, p.num, p.net, "BLOCKED_BY_KEEP_OUT", rule, None, detail=f"inside keep-out '{ko}'"))
            continue
        side_layer = 1 if p.side in ("T", "TH") else len(stack)
        if p.side != "TH" and side_layer not in routable:
            counts["BLOCKED_BY_STACKUP"] += 1
            blocked.append(PadFeasibility(p.pad_id, p.ref, p.num, p.net, "BLOCKED_BY_STACKUP", rule, None,
                                          detail=f"layer {stack[side_layer - 1]} is a plane; no signal layer on this side"))
            continue
        best: Optional[Tuple[float, _Pad]] = None
        for q in neighbours(p):
            if abs(q.x - p.x) > scan_radius_mil or abs(q.y - p.y) > scan_radius_mil:
                continue
            g = rect_gap_mil(p, q)
            if best is None or g < best[0]:
                best = (g, q)
        if best is None:
            counts["LEGAL_AND_ROUTABLE"] += 1
            continue
        gap, q = best
        same = q.ref == p.ref
        if gap < fab_min_mil - 1e-6:
            cls = "BLOCKED_BY_PACKAGE_GEOMETRY" if same else "ROUTABLE_WITH_PLACEMENT_CHANGE"
            counts[cls] += 1
            blocked.append(PadFeasibility(p.pad_id, p.ref, p.num, p.net, cls, rule, gap, q.pad_id, q.net, same,
                                          detail=f"copper gap {gap:.1f} mil < fabricator minimum {fab_min_mil:.2f} mil"))
            continue
        if gap < rule - 1e-6:
            if same:
                cls = "BLOCKED_BY_CLEARANCE"
                if p.net in power and p.side == "TH":
                    cls = "ROUTABLE_WITH_LAYER_CHANGE"
                elif p.net in power and planes:
                    cls = "ROUTABLE_WITH_POWER_POLYGON"
            else:
                cls = "ROUTABLE_WITH_PLACEMENT_CHANGE"
            counts[cls] += 1
            pf = PadFeasibility(p.pad_id, p.ref, p.num, p.net, cls, rule, gap, q.pad_id, q.net, same,
                                detail=f"rule {rule:.2f} mil ({rule / MIL:.3f} mm) > gap {gap:.1f} mil ({gap / MIL:.3f} mm) to {q.pad_id} [{q.net or 'no net'}]")
            blocked.append(pf)
            if cls == "BLOCKED_BY_CLEARANCE":
                pads_by_net_conflict.setdefault(p.net, []).append((p.pad_id, rule, gap))
            continue
        counts["LEGAL_AND_ROUTABLE"] += 1

    for net, items in pads_by_net_conflict.items():
        rule = max(r for _, r, _ in items)
        gap = min(g for _, _, g in items)
        d = SP.decision_for(net, rule / MIL, gap / MIL, [pid for pid, _, _ in items], rule_source)
        decisions[d.decision_id] = d

    total = sum(len([p for p in pads if p.net == n]) - 1 for n in {p.net for p in pads if p.net} if n)
    hard = counts["BLOCKED_BY_CLEARANCE"] + counts["BLOCKED_BY_KEEP_OUT"] + counts["BLOCKED_BY_PACKAGE_GEOMETRY"] + counts["BLOCKED_BY_STACKUP"]
    feasible = hard == 0
    if not routable:
        feasible = False
        warnings.append("no routable signal layer: every layer is a plane")
    if len(routable) <= 2 and len(stack) >= 4:
        warnings.append(f"{len(stack)} layers declared but only {len(routable)} routable: {', '.join(stack[i - 1] for i in planes)} are planes")
    summary = (f"{len(pads)} pads: {counts['LEGAL_AND_ROUTABLE']} legal, {hard} blocked "
               f"(clearance {counts['BLOCKED_BY_CLEARANCE']}, keep-out {counts['BLOCKED_BY_KEEP_OUT']}, "
               f"package {counts['BLOCKED_BY_PACKAGE_GEOMETRY']}, stackup {counts['BLOCKED_BY_STACKUP']}), "
               f"{counts['ROUTABLE_WITH_PLACEMENT_CHANGE']} need a placement change, {len(decisions)} engineering decision(s)")
    return FeasibilityReport(feasible=feasible, pads_checked=len(pads), classes=counts, blocked=blocked,
                             decisions=list(decisions.values()), routable_layers=routable,
                             signal_layers=[stack[i - 1] for i in routable], plane_layers=[stack[i - 1] for i in planes if 0 < i <= len(stack)],
                             total_connections=max(0, total), unrouted_connections=max(0, total), summary=summary,
                             analysis_ms=round((time.perf_counter() - t0) * 1000.0, 2), warnings=warnings)
