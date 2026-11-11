"""Routing pre-flight gate (LSN-20261111-004, rework item A). Fail-closed.

Three structural conditions that made WATCH rev B unroutable are checked before any engine run:

1. PLANES     every pour-backed net declared in placement.json "planes" is present in the DSN as
              (plane NET (polygon LAYER ...)) with the same vertex count and matching coordinates
              (the engine routes plane-net pins as traces otherwise: KF-20261111-004).
2. OUTLINE    exactly one closed outline primitive exists on the board-outline layer and the DSN
              boundary is a closed path (KF-20261111-007).
3. KEEP-OUTS  no pad centre lies inside a routing keep-out for its side (KF-20261111-005: pads inside
              all-layer keep-outs are unreachable, "maze search algorithm could not be created").

Inputs are plain data so the gate is unit-testable without EasyEDA: the tuned DSN text, the
placement plan dict, the PCB dump dict and the list of outline primitives read from the board
(each {"id", "layer", "closed": bool} or a raw polygon string that starts with "R").

Zero external dependencies.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

MIL = 39.37007874
OUTLINE_LAYER = 11


@dataclass
class PreflightReport:
    passed: bool
    planes_declared: int
    planes_in_dsn: int
    plane_mismatches: List[str]
    outline_primitives: int
    outline_closed: bool
    dsn_boundary_closed: bool
    pads_checked: int
    pads_in_router_keepouts: List[str]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- DSN helpers
_PLANE_RX = re.compile(r"\(plane\s+(\S+)\s+\(polygon\s+(\S+)\s+\S+\s+([^)]*)\)", re.S)


def dsn_planes(dsn_text: str) -> Dict[Tuple[str, str], List[Tuple[float, float]]]:
    """{(net, layer): [(x, y) in DSN units]} for every (plane ...) in the DSN."""
    out: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}
    for m in _PLANE_RX.finditer(dsn_text):
        nums = [float(v) for v in m.group(3).split()]
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
        out[(m.group(1), m.group(2))] = pts
    return out


def dsn_boundary_closed(dsn_text: str) -> bool:
    m = re.search(r"\(boundary\s*\(path\s+\S+\s+\S+\s+([^)]*)\)", dsn_text, re.S)
    if not m:
        return False
    nums = [float(v) for v in m.group(1).split()]
    if len(nums) < 8:
        return False
    return abs(nums[0] - nums[-2]) < 1e-6 and abs(nums[1] - nums[-1]) < 1e-6


def _plane_matches(declared_mm: List[List[float]], dsn_pts: List[Tuple[float, float]], tol: float = 0.05) -> Optional[str]:
    """Compare a placement polygon (mm) with a DSN plane polygon (mil). Returns a mismatch reason or None."""
    exp = [(x * MIL, y * MIL) for x, y in declared_mm]
    if len(exp) != len(dsn_pts):
        return f"vertex count {len(dsn_pts)} in DSN vs {len(exp)} declared"
    for (ex, ey), (dx, dy) in zip(exp, dsn_pts):
        if abs(ex - dx) > tol * MIL or abs(ey - dy) > tol * MIL:
            return f"vertex ({dx:.2f},{dy:.2f}) mil in DSN vs declared ({ex:.2f},{ey:.2f})"
    return None


# ----------------------------------------------------------------------------- keep-outs
def pads_inside_keepouts(dump: Dict[str, Any], route_keepouts: List[Dict[str, Any]],
                         origin_mm: Tuple[float, float] = (0.0, 0.0)) -> List[str]:
    """Pad ids whose centre lies inside a routing keep-out that applies to the pad's side and does not
    allow the pad's component."""
    import math
    hits: List[str] = []
    ox, oy = origin_mm
    for ref, comp in dump.items():
        if not isinstance(comp, dict):
            continue
        from desk.routing.connectivity import pad_xy
        side = "T" if int(comp.get("layer", 1)) == 1 else "B"
        for p in comp.get("pads", []):
            ax, ay = pad_xy(comp, p)
            px, py = ax / MIL - ox, ay / MIL - oy
            th = p.get("layer") in (11, 12)
            for ko in route_keepouts or []:
                if ref in (ko.get("allow") or []):
                    continue
                ks = ko.get("side", "both")
                if not (ks == "both" or th or ks == side):
                    continue
                r = ko.get("rect_mm")
                if r and r[0] <= px <= r[2] and r[1] <= py <= r[3]:
                    hits.append(f"{ref}.{p.get('num')} in keep-out '{ko.get('name', '?')}'")
                    break
    return hits


# ----------------------------------------------------------------------------- gate
def run_preflight(dsn_text: str, plan: Dict[str, Any], dump: Dict[str, Any],
                  outline_primitives: Optional[List[Dict[str, Any]]] = None) -> PreflightReport:
    errors: List[str] = []
    warnings: List[str] = []

    # 1. planes
    declared = plan.get("planes", []) or []
    found = dsn_planes(dsn_text)
    mismatches: List[str] = []
    for pl in declared:
        key = (pl.get("net"), str(pl.get("layer")))
        if key not in found:
            mismatches.append(f"{key[0]} on {key[1]}: missing from DSN")
            continue
        why = _plane_matches(pl.get("polygon_mm", []), found[key])
        if why:
            mismatches.append(f"{key[0]} on {key[1]}: {why}")
    if mismatches:
        errors.append("planes: " + "; ".join(mismatches))
    if not declared:
        warnings.append("no planes declared in placement.json; every GND/power pin will be routed as a trace")

    # 2. outline
    prims = outline_primitives if outline_primitives is not None else []
    n_outline = len([p for p in prims if int(p.get("layer", OUTLINE_LAYER)) == OUTLINE_LAYER])
    closed = n_outline == 1 and bool(prims[0].get("closed", True)) if n_outline == 1 else False
    if outline_primitives is not None:
        if n_outline != 1:
            errors.append(f"outline: {n_outline} primitives on layer {OUTLINE_LAYER}; exactly one closed outline is required")
        elif not closed:
            errors.append("outline: the single outline primitive is not closed")
    bnd = dsn_boundary_closed(dsn_text)
    if not bnd:
        errors.append("outline: DSN boundary path is missing or not closed")

    # 3. keep-outs
    hits = pads_inside_keepouts(dump, plan.get("route_keepouts") or [], tuple(plan.get("origin_mm", [0.0, 0.0])))
    if hits:
        errors.append(f"keep-outs: {len(hits)} pad(s) inside routing keep-outs: {hits[:6]}")
    if "route_keepouts" not in plan and plan.get("keepouts"):
        warnings.append("placement.json has 'keepouts' but no 'route_keepouts'; placement keep-outs are not routing keep-outs")

    pads_checked = sum(len(c.get("pads", [])) for c in dump.values() if isinstance(c, dict))
    return PreflightReport(
        passed=not errors, planes_declared=len(declared), planes_in_dsn=len(found), plane_mismatches=mismatches,
        outline_primitives=n_outline, outline_closed=closed, dsn_boundary_closed=bnd,
        pads_checked=pads_checked, pads_in_router_keepouts=hits, errors=errors, warnings=warnings)
