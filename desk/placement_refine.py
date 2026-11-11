"""Placement-routing co-optimisation: minimal, authorised refinement of movable passives.

The approved placement is preserved by default. The refiner only *proposes* small moves
(0.5-2 mm translations, 90 degree rotations) of unlocked passives that measurably reduce
the dense-board objective, and it never touches EasyEDA. Applying a proposal rewrites
`placement.json` only (atomic write, reason recorded); the live board changes only when
the operator runs `tools/pcb_place.py`.

Hard rules (never violated by a proposal):
* connectors, switches, mounting holes, modules, microphones, RF parts and any ref in the
  plan's `locked` list or any keep-out `allow` list are immovable;
* decoupling capacitors stay within `decap_max_mm` (default 2.0 mm) of the IC pad they serve
  (same net as the pad, other pad on GND);
* bodies stay inside the board with edge clearance, outside keep-outs, and do not overlap
  other bodies (0.25 mm body gap);
* identities, footprints and pin-to-net mappings are never changed.

Objective (lower is better):
    J = 100 * sum(max(0, score - 0.6) over cells) + 2 * ratsnest_crossings + mst_wirelength_mm / 10

Zero external dependencies.
"""
from __future__ import annotations
import copy
import math
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

from desk.routing.density import DensePCBIntelligence, MIL, GND_RX, POWER_RX

LOCKED_RX = re.compile(r"^(J|P|CN|USB|H|FPC|CON|X|SW|MIC|ANT|BAT|MH|TP)\d*", re.I)
PASSIVE_RX = re.compile(r"^(R|C|L|FB)\d+$", re.I)
IC_RX = re.compile(r"^(U|IC|Q)\d+", re.I)


@dataclass
class MoveProposal:
    ref: str
    from_mm: Tuple[float, float]
    to_mm: Tuple[float, float]
    from_rot: float
    to_rot: float
    objective_before: float
    objective_after: float
    hotspot_cells_before: int
    hotspot_cells_after: int
    crossings_before: int
    crossings_after: int
    reason: str

    @property
    def improvement(self) -> float:
        return round(self.objective_before - self.objective_after, 3)


@dataclass
class RefinementResult:
    objective_start: float
    objective_end: float
    proposals: List[MoveProposal]
    evaluated_candidates: int
    locked_refs: List[str]
    movable_refs: List[str]
    elapsed_ms: float
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["improvement"] = round(self.objective_start - self.objective_end, 3)
        return d


class PlacementRefiner:
    def __init__(self, dump: Dict[str, Any], plan: Dict[str, Any], stackup: Optional[List[str]] = None,
                 plane_layers: Optional[Dict[int, str]] = None, profile: Optional[Any] = None,
                 locked_refs: Optional[List[str]] = None, step_mm: float = 0.5, max_steps: int = 2,
                 decap_max_mm: float = 2.0, body_gap_mm: float = 0.25, edge_mm: float = 0.3):
        self.dump = copy.deepcopy({r: c for r, c in dump.items() if isinstance(c, dict)})
        self.plan = plan
        self.board_mm = tuple(plan.get("board_mm", [50.0, 50.0]))
        self.origin_mm = tuple(plan.get("origin_mm", [0.0, 0.0]))
        self.stackup = stackup or (["Top", "Inner1", "Inner2", "Bottom"] if plan.get("layers", 2) == 4 else ["Top", "Bottom"])
        self.plane_layers = plane_layers or {}
        self.profile = profile
        self.step = step_mm
        self.max_steps = max_steps
        self.decap_max = decap_max_mm
        self.body_gap = body_gap_mm
        self.edge = edge_mm
        self.keepouts = plan.get("keepouts", [])
        roles = plan.get("roles", {}) or {}
        self.locked: Set[str] = set(locked_refs or []) | set(plan.get("locked", [])) | set(roles.get("connectors", []))
        for ko in self.keepouts:
            self.locked |= set(ko.get("allow", []))
        for ref in self.dump:
            if LOCKED_RX.match(ref) or IC_RX.match(ref) or ref in roles.get("rf", []):
                self.locked.add(ref)
        self.engine = DensePCBIntelligence(self.dump, self.board_mm, self.origin_mm, stackup=self.stackup,
                                           plane_layers=self.plane_layers, keepouts_mm=plan.get("route_keepouts") or self.keepouts,
                                           profile=profile)
        self._decap_anchor: Dict[str, Tuple[float, float]] = self._find_decap_anchors()

    # ------------------------------------------------------------------ helpers
    def _mm(self, ref: str) -> Tuple[float, float]:
        c = self.dump[ref]
        return (c["x"] / MIL - self.origin_mm[0], c["y"] / MIL - self.origin_mm[1])

    def _body_rect_mm(self, comp: Dict[str, Any], x_mm: float, y_mm: float, rot: float) -> Tuple[float, float, float, float]:
        b = comp.get("bbox") or [-20, 20, -20, 20]
        x0, x1, y0, y1 = b[0] / MIL, b[1] / MIL, b[2] / MIL, b[3] / MIL
        if abs(((rot - (comp.get("rot") or 0)) % 180)) == 90:
            x0, x1, y0, y1 = y0, y1, x0, x1
        return (x_mm + x0, x_mm + x1, y_mm + y0, y_mm + y1)

    @staticmethod
    def _rect_overlap(a, b, gap=0.0) -> bool:
        return not (a[1] + gap <= b[0] or b[1] + gap <= a[0] or a[3] + gap <= b[2] or b[3] + gap <= a[2])

    def _find_decap_anchors(self) -> Dict[str, Tuple[float, float]]:
        """For each 2-pad capacitor between a power net and GND, the nearest IC pad on that power net."""
        anchors = {}
        ic_pads = []
        for ref, comp in self.dump.items():
            if not IC_RX.match(ref):
                continue
            from desk.routing.connectivity import pad_xy
            for p in comp.get("pads", []):
                if p.get("net") and POWER_RX.match(p["net"]) and not GND_RX.match(p["net"]):
                    px, py = pad_xy(comp, p)
                    ic_pads.append((p["net"], px / MIL - self.origin_mm[0], py / MIL - self.origin_mm[1]))
        for ref, comp in self.dump.items():
            if not ref.upper().startswith("C") or len(comp.get("pads", [])) != 2:
                continue
            nets = [p.get("net") or "" for p in comp["pads"]]
            if not any(GND_RX.match(n) for n in nets):
                continue
            pwr = [n for n in nets if POWER_RX.match(n) and not GND_RX.match(n)]
            if not pwr:
                continue
            x, y = self._mm(ref)
            cands = [(math.hypot(px - x, py - y), (px, py)) for n, px, py in ic_pads if n == pwr[0]]
            if cands:
                anchors[ref] = min(cands)[1]
        return anchors

    def _violates_hard_rules(self, ref: str, x_mm: float, y_mm: float, rot: float) -> Optional[str]:
        comp = self.dump[ref]
        body = self._body_rect_mm(comp, x_mm, y_mm, rot)
        W, H = self.board_mm
        if body[0] < self.edge or body[2] < self.edge or body[1] > W - self.edge or body[3] > H - self.edge:
            return "outside board edge clearance"
        side = "T" if comp.get("layer", 1) == 1 else "B"
        for ko in self.keepouts:
            if ref in ko.get("allow", []):
                continue
            if ko.get("side", "both") not in ("both", side):
                continue
            r = ko.get("rect_mm")
            if r and self._rect_overlap(body, (r[0], r[2], r[1], r[3])):
                return f"inside keep-out {ko.get('name')}"
        for other, oc in self.dump.items():
            if other == ref or oc.get("layer", 1) != comp.get("layer", 1):
                continue
            ox, oy = self._mm(other)
            if self._rect_overlap(body, self._body_rect_mm(oc, ox, oy, oc.get("rot") or 0), self.body_gap):
                return f"overlaps {other}"
        anchor = self._decap_anchor.get(ref)
        if anchor and math.hypot(anchor[0] - x_mm, anchor[1] - y_mm) > self.decap_max:
            return "breaks decoupling proximity"
        return None

    def objective(self) -> Tuple[float, int, int]:
        rep = self.engine.analyze()
        hot = sum(max(0.0, c.score - 0.6) for c in self.engine.cells.values())
        J = 100.0 * hot + 2.0 * rep.ratsnest_crossings + rep.mst_wirelength_mm / 10.0
        return round(J, 3), rep.hotspot_cells, rep.ratsnest_crossings

    def _moved_record(self, ref: str, x_mm: float, y_mm: float, rot: float) -> Dict[str, Any]:
        """New dump record for a moved/rotated part. Pad offsets are board-frame, so a rotation change
        rotates them (and swaps rectangular pad shapes) by the delta only."""
        comp = copy.deepcopy(self.dump[ref])
        delta = math.radians(float(rot) - float(comp.get("rot") or 0))
        if abs(delta) > 1e-9:
            c, s = math.cos(delta), math.sin(delta)
            for p in comp.get("pads", []):
                dx, dy = float(p.get("dx", 0.0)), float(p.get("dy", 0.0))
                p["dx"], p["dy"] = dx * c - dy * s, dx * s + dy * c
                shape = p.get("shape")
                if isinstance(shape, list) and len(shape) >= 3 and abs(abs(math.degrees(delta)) % 180 - 90) < 1e-6:
                    shape[1], shape[2] = shape[2], shape[1]
            b = comp.get("bbox")
            if b and abs(abs(math.degrees(delta)) % 180 - 90) < 1e-6:
                comp["bbox"] = [b[2], b[3], b[0], b[1]]
        comp["x"] = (x_mm + self.origin_mm[0]) * MIL
        comp["y"] = (y_mm + self.origin_mm[1]) * MIL
        comp["rot"] = rot
        return comp

    # ------------------------------------------------------------------ main loop
    def refine(self, max_moves: int = 5, min_improvement: float = 1.0, candidates: Optional[List[str]] = None) -> RefinementResult:
        t0 = time.perf_counter()
        J0, hot0, x0 = self.objective()
        J, hot, xings = J0, hot0, x0
        notes: List[str] = []
        proposals: List[MoveProposal] = []
        evaluated = 0

        movable = [r for r in self.dump if PASSIVE_RX.match(r) and r not in self.locked]
        if candidates:
            movable = [r for r in movable if r in candidates]
        # parts inside or next to hotspot regions first
        rep = self.engine.last_report
        hot_refs = {c for h in (rep.hotspots if rep else []) for c in h.components}
        movable.sort(key=lambda r: (0 if r in hot_refs else 1, r))
        if not movable:
            notes.append("no movable passives (all locked or none present)")

        for _ in range(max_moves):
            best: Optional[Tuple[float, str, float, float, float, int, int]] = None
            for ref in movable:
                x, y = self._mm(ref)
                rot = self.dump[ref].get("rot") or 0
                cands = [(x, y, (rot + 90) % 360)]
                for k in range(1, self.max_steps + 1):
                    d = k * self.step
                    cands += [(x + d, y, rot), (x - d, y, rot), (x, y + d, rot), (x, y - d, rot)]
                for nx, ny, nrot in cands:
                    evaluated += 1
                    if self._violates_hard_rules(ref, nx, ny, nrot):
                        continue
                    original = self.dump[ref]
                    trial = self._moved_record(ref, nx, ny, nrot)
                    self.engine.update_components({ref: trial})
                    self.dump[ref] = trial
                    Jt, hott, xt = self.objective()
                    # revert
                    self.engine.update_components({ref: original})
                    self.dump[ref] = original
                    if Jt < J - min_improvement and (best is None or Jt < best[0]):
                        best = (Jt, ref, nx, ny, nrot, hott, xt)
            if best is None:
                break
            Jt, ref, nx, ny, nrot, hott, xt = best
            fx, fy = self._mm(ref)
            frot = self.dump[ref].get("rot") or 0
            new = self._moved_record(ref, nx, ny, nrot)
            self.engine.update_components({ref: new})
            self.dump[ref] = new
            reason = ("rotate 90 deg to expose a better escape direction" if (nx, ny) == (fx, fy)
                      else f"move {math.hypot(nx - fx, ny - fy):.1f} mm away from a congested corridor")
            proposals.append(MoveProposal(ref, (round(fx, 2), round(fy, 2)), (round(nx, 2), round(ny, 2)), frot, nrot,
                                          J, Jt, hot, hott, xings, xt, reason))
            J, hot, xings = Jt, hott, xt
            movable.remove(ref)

        return RefinementResult(objective_start=J0, objective_end=J, proposals=proposals, evaluated_candidates=evaluated,
                                locked_refs=sorted(self.locked), movable_refs=sorted(movable),
                                elapsed_ms=round((time.perf_counter() - t0) * 1000, 1), notes=notes)

    # ------------------------------------------------------------------ apply (placement.json only)
    def apply_to_plan(self, result: RefinementResult, plan_path: str, authorised_by: str) -> int:
        """Write accepted proposals into placement.json (parts list) atomically. Never touches EasyEDA.
        Returns the number of parts updated. Requires an explicit authoriser string."""
        if not authorised_by:
            raise ValueError("placement refinement must be authorised (authorised_by is empty)")
        from desk.fsutil import atomic_write_json, read_json
        plan = read_json(plan_path, default=None)
        if plan is None:
            raise FileNotFoundError(plan_path)
        by_ref = {p.ref: p for p in result.proposals}
        updated = 0
        for part in plan.get("parts", []):
            if part and part[0] in by_ref:
                p = by_ref[part[0]]
                part[1], part[2], part[3] = p.to_mm[0], p.to_mm[1], p.to_rot
                part[5] = f"{part[5]} [refined {time.strftime('%Y-%m-%d')} by {authorised_by}: {p.reason}; dJ={p.improvement}]"
                updated += 1
        plan.setdefault("refinement_log", []).append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "authorised_by": authorised_by,
            "objective_start": result.objective_start, "objective_end": result.objective_end,
            "moves": [asdict(p) for p in result.proposals]})
        atomic_write_json(plan_path, plan, indent=2)
        return updated
