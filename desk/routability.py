"""Routability-Aware Placement Evaluation Engine and Acceptance Gate for DESK.
Evaluates proposed PCB placements before routing:
- Net connectivity graph & pad-level topology
- Multi-terminal Minimum Spanning Tree (MST) and HPWL wire length estimation
- Planar ratsnest crossings calculation
- Pin escape congestion and fine-pitch fanout feasibility
- Mechanical screw terminal and connector accessibility verification
- Placement freeze snapshot and acceptance gate
"""
import math
import json
import hashlib
import re
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.models import (
    NetEndpoint,
    NetConnectivityGraph,
    PlacementValidationResult,
    PlacementPlan,
    ComponentRequirement
)
from desk.placement_intel import MechanicalEnvelope

MIL = 39.37007874

def _segments_intersect(p1: Tuple[float, float], p2: Tuple[float, float],
                        p3: Tuple[float, float], p4: Tuple[float, float]) -> bool:
    """Returns True if line segment p1-p2 strictly intersects p3-p4."""
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    # Ignore shared endpoints
    if (math.isclose(p1[0], p3[0]) and math.isclose(p1[1], p3[1])) or \
       (math.isclose(p1[0], p4[0]) and math.isclose(p1[1], p4[1])) or \
       (math.isclose(p2[0], p3[0]) and math.isclose(p2[1], p3[1])) or \
       (math.isclose(p2[0], p4[0]) and math.isclose(p2[1], p4[1])):
        return False

    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))

class RoutabilityEvaluator:
    """Constructs NetConnectivityGraph and analyzes routing feasibility."""

    @staticmethod
    def build_connectivity_graph(dump: Dict[str, Any],
                                 placement_target: Optional[Dict[str, List[Any]]] = None) -> NetConnectivityGraph:
        """Extracts pad endpoints for every populated net in absolute mil coordinates."""
        nets: Dict[str, List[NetEndpoint]] = {}
        target = placement_target or {}

        for ref, comp in dump.items():
            if not ref or not isinstance(comp, dict): continue
            pads = comp.get("pads", [])
            # If target coordinates exist in placement_target, compute transformed pad positions
            if ref in target:
                tx_mm, ty_mm, rot_deg, side = target[ref][:4]
                base_x_mil = tx_mm * MIL
                base_y_mil = ty_mm * MIL
                rot_rad = math.radians(rot_deg)
                layer = 1 if side == "T" else 2
            else:
                base_x_mil = comp.get("x", 0.0)
                base_y_mil = comp.get("y", 0.0)
                rot_deg = comp.get("rot", 0.0) or 0.0
                rot_rad = math.radians(rot_deg)
                layer = comp.get("layer", 1)

            cos_a = math.cos(rot_rad)
            sin_a = math.sin(rot_rad)

            for p in pads:
                net = p.get("net")
                if not net or net.strip() == "": continue
                dx = p.get("dx", 0.0)
                dy = p.get("dy", 0.0)
                px = base_x_mil + dx * cos_a - dy * sin_a
                py = base_y_mil + dx * sin_a + dy * cos_a
                pad_num = str(p.get("num", ""))
                is_smd = p.get("layer") not in (11, 12)

                endpoint = NetEndpoint(
                    ref=ref,
                    pad_num=pad_num,
                    net=net,
                    x_mil=px,
                    y_mil=py,
                    layer=layer if is_smd else 11,
                    is_smd=is_smd
                )
                if net not in nets:
                    nets[net] = []
                nets[net].append(endpoint)

        # Build Minimum Spanning Tree for multi-terminal nets
        mst_trees: Dict[str, List[Tuple[NetEndpoint, NetEndpoint]]] = {}
        total_hpwl = 0.0
        total_mst = 0.0
        mst_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

        for net_name, endpoints in nets.items():
            if len(endpoints) < 2: continue
            # HPWL
            xs = [ep.x_mil for ep in endpoints]
            ys = [ep.y_mil for ep in endpoints]
            hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
            total_hpwl += hpwl

            # MST using Prim's algorithm
            unvisited = set(range(1, len(endpoints)))
            visited = {0}
            edges = []

            while unvisited:
                best_dist = float("inf")
                best_edge = None
                best_target = None
                for u in visited:
                    p_u = endpoints[u]
                    for v in unvisited:
                        p_v = endpoints[v]
                        d = math.hypot(p_u.x_mil - p_v.x_mil, p_u.y_mil - p_v.y_mil)
                        if d < best_dist:
                            best_dist = d
                            best_edge = (p_u, p_v)
                            best_target = v
                if best_target is not None:
                    visited.add(best_target)
                    unvisited.remove(best_target)
                    edges.append(best_edge)
                    total_mst += best_dist
                    # Filter out power/ground nets from ratsnest crossing count to avoid noise
                    if not re.search(r"GND|VSS|VCC|VDD|3V3|5V|1V8|VBAT|VBUS", net_name, re.I):
                        mst_segments.append(((best_edge[0].x_mil, best_edge[0].y_mil),
                                            (best_edge[1].x_mil, best_edge[1].y_mil)))

            mst_trees[net_name] = edges

        # Compute signal ratsnest crossings
        crossings = 0
        n_segs = len(mst_segments)
        for i in range(n_segs):
            for j in range(i + 1, min(i + 200, n_segs)):  # capped window for fast evaluation
                if _segments_intersect(mst_segments[i][0], mst_segments[i][1],
                                        mst_segments[j][0], mst_segments[j][1]):
                    crossings += 1

        return NetConnectivityGraph(
            nets=nets,
            multi_terminal_trees=mst_trees,
            ratsnest_crossings=crossings,
            hpwl_wirelength_mil=round(total_hpwl, 1),
            mst_wirelength_mil=round(total_mst, 1)
        )

    @staticmethod
    def evaluate_pin_escape_congestion(dump: Dict[str, Any],
                                       target: Optional[Dict[str, List[Any]]] = None) -> float:
        """Scores pin escape density around high-pin-count components (0.0=free, 1.0=congested)."""
        congestions = []
        for ref, comp in dump.items():
            pads = comp.get("pads", [])
            if len(pads) < 8: continue
            # Bounding box perimeter
            bb = comp.get("bbox", [-50, 50, -50, 50])
            w_mil = max(10.0, bb[1] - bb[0])
            h_mil = max(10.0, bb[3] - bb[2])
            perimeter_mil = 2 * (w_mil + h_mil)
            # Standard pad escape requires at least 15 mil perimeter per signal pad
            signal_pads = [p for p in pads if p.get("net") and not re.search(r"GND|VSS", p.get("net"), re.I)]
            req_perimeter = len(signal_pads) * 15.0
            ratio = req_perimeter / perimeter_mil if perimeter_mil > 0 else 1.0
            congestions.append(ratio)

        return round(max(congestions) if congestions else 0.2, 3)

    @staticmethod
    def verify_mechanical_access(dump: Dict[str, Any],
                                 target: Dict[str, List[Any]],
                                 reqs: Dict[str, ComponentRequirement],
                                 board_dims_mm: Tuple[float, float]) -> List[str]:
        """Ensures screwdriver access to screw terminals and plug insertion to connectors are not blocked."""
        errs = []
        W, H = board_dims_mm

        for ref, cr in reqs.items():
            if cr.electrical_role == "screw_terminal" and ref in target:
                x_mm, y_mm = target[ref][0], target[ref][1]
                half_w = cr.width_mm / 2.0
                half_h = cr.height_mm / 2.0
                body = (x_mm - half_w, x_mm + half_w, y_mm - half_h, y_mm + half_h)

                # Screwdriver and wire corridors
                corridors = MechanicalEnvelope.get_screw_terminal_access_corridor(body)
                sd_box = corridors["screwdriver_access"]
                wire_box = corridors["wire_entry"]

                # Check if any other component intrudes into the screwdriver or wire corridor
                for other_ref, other_target in target.items():
                    if other_ref == ref: continue
                    ox, oy = other_target[0], other_target[1]
                    # Check intrusion
                    if (sd_box[0] <= ox <= sd_box[1]) and (sd_box[2] <= oy <= sd_box[3]):
                        errs.append(f"{other_ref}: blocks screwdriver access corridor for screw terminal {ref}")
                    if (wire_box[0] <= ox <= wire_box[1]) and (wire_box[2] <= oy <= wire_box[3]):
                        errs.append(f"{other_ref}: blocks wire entry corridor for screw terminal {ref}")

            elif cr.electrical_role == "mechanical_anchor" and "CONN" in cr.footprint_id.upper() and ref in target:
                x_mm, y_mm = target[ref][0], target[ref][1]
                half_w = cr.width_mm / 2.0
                half_h = cr.height_mm / 2.0
                body = (x_mm - half_w, x_mm + half_w, y_mm - half_h, y_mm + half_h)
                mating_box = MechanicalEnvelope.get_connector_mating_envelope(body, board_dims_mm)

                for other_ref, other_target in target.items():
                    if other_ref == ref: continue
                    ox, oy = other_target[0], other_target[1]
                    if (mating_box[0] <= ox <= mating_box[1]) and (mating_box[2] <= oy <= mating_box[3]):
                        errs.append(f"{other_ref}: blocks connector mating plug envelope for {ref}")

        return errs

class PlacementAcceptanceGate:
    """Enforces strict placement acceptance criteria and produces freeze snapshots."""

    @staticmethod
    def evaluate(dump: Dict[str, Any],
                 placement_target: Dict[str, List[Any]],
                 reqs: Dict[str, ComponentRequirement],
                 board_dims_mm: Tuple[float, float],
                 standard_errors: Optional[List[str]] = None,
                 standard_warnings: Optional[List[str]] = None) -> PlacementValidationResult:
        errs = list(standard_errors or [])
        warns = list(standard_warnings or [])

        # 1. Footprint Invariants
        for ref, cr in reqs.items():
            if cr.invariants and ref in dump:
                inv_errs = cr.invariants.validate_invariance(
                    len(dump[ref].get("pads", [])),
                    [str(p.get("num", "")) for p in dump[ref].get("pads", [])],
                    {str(p.get("num", "")): (float(p.get("dx", 0.0)), float(p.get("dy", 0.0))) for p in dump[ref].get("pads", [])}
                )
                errs.extend(inv_errs)

        # 2. Mechanical Access (Screwdriver, Connectors)
        mech_errs = RoutabilityEvaluator.verify_mechanical_access(dump, placement_target, reqs, board_dims_mm)
        errs.extend(mech_errs)

        # 3. Routability Connectivity Analysis
        net_graph = RoutabilityEvaluator.build_connectivity_graph(dump, placement_target)
        escape_congestion = RoutabilityEvaluator.evaluate_pin_escape_congestion(dump, placement_target)

        # Score routability: based on ratsnest crossings and escape congestion
        # 0.0 to 1.0 (1.0 = ideal)
        crossings_penalty = min(0.4, net_graph.ratsnest_crossings * 0.002)
        congestion_penalty = min(0.4, max(0.0, escape_congestion - 0.5) * 0.8)
        routability_score = round(max(0.1, 1.0 - crossings_penalty - congestion_penalty), 2)

        if escape_congestion > 1.2:
            warns.append(f"Escape congestion high ({escape_congestion:.2f}): some IC pads may require microvias or layer hopping")

        passed = (len(errs) == 0)

        return PlacementValidationResult(
            passed=passed,
            errors=errs,
            warnings=warns,
            metrics={
                "ratsnest_crossings": net_graph.ratsnest_crossings,
                "mst_length_mm": round(net_graph.mst_wirelength_mil / MIL, 1),
                "hpwl_length_mm": round(net_graph.hpwl_wirelength_mil / MIL, 1),
                "escape_congestion": escape_congestion,
                "populated_nets": len(net_graph.nets)
            },
            routability_score=routability_score,
            ratsnest_crossings=net_graph.ratsnest_crossings,
            estimated_total_wirelength_mm=round(net_graph.mst_wirelength_mil / MIL, 1),
            escape_congestion_score=escape_congestion
        )

    @staticmethod
    def freeze_placement(placement_target: Dict[str, List[Any]],
                         result: PlacementValidationResult) -> Dict[str, Any]:
        """Creates an immutable placement snapshot dictionary with SHA-1 hash."""
        if not result.passed:
            raise ValueError(f"Cannot freeze placement: validation failed with {len(result.errors)} errors")

        target_json = json.dumps(placement_target, sort_keys=True)
        snap_hash = hashlib.sha1(target_json.encode()).hexdigest()[:12]

        return {
            "frozen": True,
            "snapshot_hash": snap_hash,
            "target": placement_target,
            "metrics": result.metrics,
            "routability_score": result.routability_score
        }
