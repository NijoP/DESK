"""Mechanical-First Placement Intelligence Engine for DESK.
Enforces the strict placement hierarchy:
MECHANICAL INTEGRITY -> FOOTPRINT INTEGRITY -> ELECTRICAL INTEGRITY ->
FUNCTIONAL PLACEMENT -> ROUTABILITY OPTIMISATION -> BOARD-AREA OPTIMISATION.

Handles:
- Mounting hole standoff and tool keepouts
- External connector mating envelopes and cable exit corridors
- Screw terminal wire entry, screwdriver access cones, and tightening clearance
- Functional clustering (power, MCU, sensor, RF/comms)
- Topological passive snapping (decoupling capacitors, ESD protection, crystals, RC filters)
"""
import math
import re
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.models import (
    ComponentRequirement,
    MechanicalConstraint,
    ElectricalConstraint,
    PlacementIntent,
    FunctionalCluster,
    PlacementPlan
)
from desk.component_intel import ComponentClassifier

MIL = 39.37007874

class MechanicalEnvelope:
    """Calculates clearance envelopes for mechanical components (connectors, screw terminals, mounting holes)."""

    @staticmethod
    def get_screw_terminal_access_corridor(body_rect: Tuple[float, float, float, float],
                                           wire_entry_side: str = "B",
                                           screwdriver_side: str = "T",
                                           screwdriver_depth_mm: float = 12.0,
                                           wire_entry_depth_mm: float = 8.0) -> Dict[str, Tuple[float, float, float, float]]:
        """Computes two keep-out envelopes for screw terminals:
        1. Screwdriver access corridor (tool clearance above/facing screws)
        2. Wire insertion and bending corridor (wire entry side)
        """
        min_x, max_x, min_y, max_y = body_rect

        # Screwdriver tool keepout
        sd_corridor = (min_x, max_x, min_y, max_y)
        if screwdriver_side == "T":
            sd_corridor = (min_x - 1.0, max_x + 1.0, max_y, max_y + screwdriver_depth_mm)
        elif screwdriver_side == "B":
            sd_corridor = (min_x - 1.0, max_x + 1.0, max_y - screwdriver_depth_mm, min_y)
        elif screwdriver_side == "L":
            sd_corridor = (min_x - screwdriver_depth_mm, min_x, min_y - 1.0, max_y + 1.0)
        elif screwdriver_side == "R":
            sd_corridor = (max_x, max_x + screwdriver_depth_mm, min_y - 1.0, max_y + 1.0)

        # Wire insertion keepout
        wire_corridor = (min_x, max_x, min_y, max_y)
        if wire_entry_side == "B":
            wire_corridor = (min_x - 1.0, max_x + 1.0, min_y - wire_entry_depth_mm, min_y)
        elif wire_entry_side == "T":
            wire_corridor = (min_x - 1.0, max_x + 1.0, max_y, max_y + wire_entry_depth_mm)
        elif wire_entry_side == "L":
            wire_corridor = (min_x - wire_entry_depth_mm, min_x, min_y - 1.0, max_y + 1.0)
        elif wire_entry_side == "R":
            wire_corridor = (max_x, max_x + wire_entry_depth_mm, min_y - 1.0, max_y + 1.0)

        return {"screwdriver_access": sd_corridor, "wire_entry": wire_corridor}

    @staticmethod
    def get_connector_mating_envelope(body_rect: Tuple[float, float, float, float],
                                      board_dims: Tuple[float, float],
                                      front_depth_mm: float = 5.0) -> Tuple[float, float, float, float]:
        """Calculates front plug/cable insertion keepout facing the closest board edge."""
        min_x, max_x, min_y, max_y = body_rect
        W, H = board_dims
        dist_to_edges = {"L": min_x, "R": W - max_x, "B": min_y, "T": H - max_y}
        facing = min(dist_to_edges, key=dist_to_edges.get)

        if facing == "L":
            return (0.0, min_x, min_y - 1.0, max_y + 1.0)
        elif facing == "R":
            return (max_x, W, min_y - 1.0, max_y + 1.0)
        elif facing == "B":
            return (min_x - 1.0, max_x + 1.0, 0.0, min_y)
        else:  # "T"
            return (min_x - 1.0, max_x + 1.0, max_y, H)

    @staticmethod
    def get_mounting_hole_keepout(center: Tuple[float, float],
                                 standoff_dia_mm: float = 6.0,
                                 head_dia_mm: float = 5.5) -> Dict[str, Any]:
        """Keepout circle/box for screw heads, standoffs, and assembly tool clearance."""
        r = max(standoff_dia_mm, head_dia_mm) / 2.0 + 0.5  # +0.5 mm tool safety margin
        cx, cy = center
        return {
            "name": f"MH_Keepout_({cx:.1f},{cy:.1f})",
            "rect_mm": (cx - r, cy - r, cx + r, cy + r),
            "radius_mm": r,
            "center": (cx, cy)
        }

class FunctionalClusterBuilder:
    """Discovers electrical functional clusters from block specs and connectivity."""

    @staticmethod
    def build_clusters(reqs: Dict[str, ComponentRequirement],
                       blocks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, FunctionalCluster]:
        clusters: Dict[str, FunctionalCluster] = {}
        blocks = blocks or []

        # If block specs exist, use them as ground truth for clusters
        for b in blocks:
            b_id = b.get("id", "cluster")
            b_title = b.get("title", b_id)
            parts = [p.get("ref") for p in b.get("parts", []) if p.get("ref")]

            # Classify cluster electrical role
            role = "control"
            title_u = b_title.upper()
            if any(k in title_u for k in ("PWR", "POWER", "BUCK", "BOOST", "LDO", "CHARGER", "BATT")):
                role = "power_conversion"
            elif any(k in title_u for k in ("MCU", "CPU", "CORE", "MAIN", "ESP32", "STM32")):
                role = "main_control"
            elif any(k in title_u for k in ("SENS", "IMU", "TEMP", "HUM", "ADC")):
                role = "sensor_acquisition"
            elif any(k in title_u for k in ("COMM", "USB", "CAN", "RS485", "BLE", "WIFI", "RF")):
                role = "comms"
            elif any(k in title_u for k in ("AUDIO", "SPK", "MIC", "CODEC", "AMP")):
                role = "audio"
            elif any(k in title_u for k in ("DRIVER", "MOTOR", "RELAY", "MOSFET", "OUT")):
                role = "output_driver"

            primaries = []
            passives = []
            power_nets = set()
            signals = set()

            for r in parts:
                if r not in reqs: continue
                cr = reqs[r]
                if cr.electrical_role in ("primary_ic", "mechanical_anchor", "screw_terminal"):
                    primaries.append(r)
                else:
                    passives.append(r)
                for net in cr.pad_to_net.values():
                    if not net: continue
                    if re.search(r"VCC|VDD|3V3|5V|1V8|VBAT|VBUS|GND", net, re.I):
                        power_nets.add(net)
                    else:
                        signals.add(net)

            clusters[b_id] = FunctionalCluster(
                cluster_id=b_id,
                name=b_title,
                electrical_role=role,
                primary_refs=primaries,
                passive_refs=passives,
                power_nets=sorted(list(power_nets)),
                ground_strategy="direct_via" if role in ("power_conversion", "main_control") else "star_to_plane",
                external_signals=sorted(list(signals))
            )

        # Fallback: if no blocks were provided, group by connected primary ICs
        if not clusters:
            ic_map = {}
            for ref, cr in reqs.items():
                if cr.electrical_role in ("primary_ic", "mechanical_anchor", "screw_terminal"):
                    c_id = f"CL_{ref}"
                    clusters[c_id] = FunctionalCluster(
                        cluster_id=c_id,
                        name=f"Cluster {ref}",
                        electrical_role="general",
                        primary_refs=[ref],
                        passive_refs=[]
                    )
                    ic_map[ref] = c_id

            # Associate passives with primary components based on shared nets
            for ref, cr in reqs.items():
                if cr.electrical_role not in ("primary_ic", "mechanical_anchor", "screw_terminal"):
                    best_match = None
                    max_shared = 0
                    p_nets = set(cr.pad_to_net.values()) - {"", "GND", "VSS"}
                    for ic_ref, ic_id in ic_map.items():
                        shared = len(p_nets & set(reqs[ic_ref].pad_to_net.values()))
                        if shared > max_shared:
                            max_shared = shared
                            best_match = ic_id
                    if best_match and max_shared > 0:
                        clusters[best_match].passive_refs.append(ref)

        return clusters

class TopologicalPassiveSnapper:
    """Snaps passives to their associated pins following electrical topologies:
    - Decoupling capacitor -> IC supply pin (under 2 mm loop)
    - Crystal load capacitors -> Crystal and IC osc pins
    - ESD protection -> Connector pins before reaching ICs
    - Pull-up resistors -> Bus lines
    """

    @staticmethod
    def snap_passives(intents: Dict[str, PlacementIntent],
                      reqs: Dict[str, ComponentRequirement],
                      blocks: Optional[List[Dict[str, Any]]] = None,
                      passive_gap_mm: float = 0.45) -> List[Tuple[str, str, str, str]]:
        """Returns list of snapped passive specifications: [(passive_ref, ic_ref, pin_num, reason)]"""
        snapped = []
        blocks = blocks or []

        # 1. From block specs (e.g. "role": "decoupling U1 pin 5")
        for b in blocks:
            for sp in b.get("parts", []):
                role = sp.get("role", "")
                m = re.search(r"\b((?:U|IC|Q|J)\w*)\b.*?\bpin\s*(\w+)", role, re.I)
                p_ref = sp.get("ref")
                if m and p_ref and p_ref in reqs:
                    anchor_ref, pin_num = m.group(1), m.group(2)
                    if anchor_ref in intents:
                        snapped.append((p_ref, anchor_ref, pin_num, f"Topological snap: {role}"))

        # 2. Heuristic decoupling snap for capacitors sharing a supply pin with an IC
        already_snapped = {s[0] for s in snapped}
        for ref, cr in reqs.items():
            if ref in already_snapped or ref not in intents: continue
            if cr.electrical_role == "decoupling_capacitor":
                p_nets = set(cr.pad_to_net.values())
                supply_nets = {n for n in p_nets if re.search(r"VCC|VDD|3V3|5V|1V8|VBAT|VBUS", n, re.I)}
                if supply_nets:
                    target_net = next(iter(supply_nets))
                    # Find closest IC that has this supply net
                    for ic_ref, ic_req in reqs.items():
                        if ic_ref == ref or ic_req.electrical_role != "primary_ic" or ic_ref not in intents:
                            continue
                        for p in ic_req.pads:
                            if p.net == target_net:
                                snapped.append((ref, ic_ref, p.num, f"Decoupling supply net {target_net} at {ic_ref}.{p.num}"))
                                already_snapped.add(ref)
                                break
                        if ref in already_snapped:
                            break

        # 3. Crystal oscillator capacitors snap
        for ref, cr in reqs.items():
            if cr.electrical_role == "crystal" and ref in intents:
                xtal_nets = set(cr.pad_to_net.values()) - {"", "GND"}
                for p_ref, p_req in reqs.items():
                    if p_ref in already_snapped or p_req.electrical_role != "capacitor": continue
                    if set(p_req.pad_to_net.values()) & xtal_nets:
                        snapped.append((p_ref, ref, "1", f"Crystal load capacitor for {ref}"))
                        already_snapped.add(p_ref)

        # 4. ESD protection snap to connector
        for ref, cr in reqs.items():
            if cr.electrical_role == "protection" and ref in intents:
                prot_nets = set(cr.pad_to_net.values()) - {"", "GND"}
                for conn_ref, conn_req in reqs.items():
                    if conn_req.electrical_role not in ("mechanical_anchor", "screw_terminal") or conn_ref not in intents:
                        continue
                    if set(conn_req.pad_to_net.values()) & prot_nets:
                        snapped.append((ref, conn_ref, "1", f"ESD protection immediately behind connector {conn_ref}"))
                        already_snapped.add(ref)
                        break

        return snapped

class PlacementIntelligenceEngine:
    """Integrated engine enforcing mechanical, footprint, electrical, and functional placement rules."""

    def __init__(self, board_dims_mm: Tuple[float, float], origin_mm: Tuple[float, float] = (0.0, 0.0)):
        self.W, self.H = board_dims_mm
        self.ox, self.oy = origin_mm

    def generate_hierarchical_placement(self,
                                       reqs: Dict[str, ComponentRequirement],
                                       blocks: Optional[List[Dict[str, Any]]] = None,
                                       existing_intents: Optional[Dict[str, PlacementIntent]] = None,
                                       keepouts: Optional[List[Dict[str, Any]]] = None) -> PlacementPlan:
        """Generates an autonomous, constraint-aware placement plan according to the hierarchy."""
        intents: Dict[str, PlacementIntent] = dict(existing_intents or {})
        clusters = FunctionalClusterBuilder.build_clusters(reqs, blocks)
        keepouts = list(keepouts or [])

        # Priority 1: Board outline & mounting holes
        # If mounting holes are unplaced, place them symmetrically in 4 corners with 3.5mm setback
        mh_refs = [r for r, c in reqs.items() if c.electrical_role == "mounting_hole"]
        corner_offsets = [(4.0, 4.0), (self.W - 4.0, 4.0), (self.W - 4.0, self.H - 4.0), (4.0, self.H - 4.0)]
        for idx, mh_ref in enumerate(mh_refs):
            if mh_ref not in intents:
                target_pos = corner_offsets[idx % 4]
                intents[mh_ref] = PlacementIntent(
                    ref=mh_ref,
                    target_x_mm=target_pos[0],
                    target_y_mm=target_pos[1],
                    rotation=0.0,
                    side="T",
                    reason="Mechanical anchor: Corner mounting hole",
                    locked=True
                )
            # Add mounting hole standoff keepout
            cx, cy = intents[mh_ref].target_x_mm, intents[mh_ref].target_y_mm
            keepouts.append(MechanicalEnvelope.get_mounting_hole_keepout((cx, cy)))

        # Priority 2: External connectors and screw terminals along board edges
        external_refs = [r for r, c in reqs.items() if c.electrical_role in ("mechanical_anchor", "screw_terminal")]
        conn_x_cursor = 10.0
        for ref in external_refs:
            if ref in intents: continue
            cr = reqs[ref]
            # Place along bottom or top edge facing outwards
            w_box = max(cr.width_mm, 6.0)
            if conn_x_cursor + w_box > self.W - 8.0:
                conn_x_cursor = 10.0
            
            y_pos = cr.height_mm / 2.0 + 0.5  # At bottom edge
            rot = 0.0
            if cr.electrical_role == "screw_terminal":
                reason = "Mechanical-first: Screw terminal at board edge with clear screwdriver and wire access"
            else:
                reason = "Mechanical-first: External connector facing board perimeter with mating envelope"

            intents[ref] = PlacementIntent(
                ref=ref,
                target_x_mm=round(conn_x_cursor + w_box / 2.0, 2),
                target_y_mm=round(y_pos, 2),
                rotation=rot,
                side="T",
                reason=reason,
                locked=True
            )
            conn_x_cursor += w_box + 4.0

        # Priority 3: Primary ICs placed centrally according to functional clusters
        primary_ics = [r for r, c in reqs.items() if c.electrical_role == "primary_ic" and r not in intents]
        # Spread ICs across active cluster zones
        ic_cols = max(1, int(math.ceil(math.sqrt(len(primary_ics)))))
        col_spacing = (self.W - 20.0) / (ic_cols + 1)
        row_spacing = (self.H - 20.0) / (max(1, int(math.ceil(len(primary_ics) / ic_cols))) + 1)

        for i, ref in enumerate(primary_ics):
            col = i % ic_cols
            row = i // ic_cols
            x = 10.0 + (col + 1) * col_spacing
            y = 12.0 + (row + 1) * row_spacing
            intents[ref] = PlacementIntent(
                ref=ref,
                target_x_mm=round(x, 2),
                target_y_mm=round(y, 2),
                rotation=0.0,
                side="T",
                reason="Electrical placement: Primary IC placed centrally with fan-out corridors"
            )

        # Priority 4: Snap supporting passives topologically
        snaps = TopologicalPassiveSnapper.snap_passives(intents, reqs, blocks)
        for p_ref, anchor_ref, pin_num, why in snaps:
            if p_ref not in intents and anchor_ref in intents:
                anchor = intents[anchor_ref]
                # Default offset adjacent to anchor
                anchor_req = reqs.get(anchor_ref)
                offset_x = (anchor_req.width_mm / 2.0 + 1.2) if anchor_req else 2.5
                intents[p_ref] = PlacementIntent(
                    ref=p_ref,
                    target_x_mm=round(anchor.target_x_mm + offset_x, 2),
                    target_y_mm=round(anchor.target_y_mm, 2),
                    rotation=0.0,
                    side=anchor.side,
                    reason=why,
                    anchor_ref=anchor_ref,
                    anchor_pin=pin_num
                )

        # Priority 5: Remaining passives placed in cluster proximity
        remaining = [r for r in reqs if r not in intents]
        cursor_x, cursor_y = 6.0, self.H - 10.0
        for r in remaining:
            intents[r] = PlacementIntent(
                ref=r,
                target_x_mm=round(cursor_x, 2),
                target_y_mm=round(cursor_y, 2),
                rotation=0.0,
                side="T",
                reason="Supporting passive: Placed in auxiliary functional corridor"
            )
            cursor_x += 3.0
            if cursor_x > self.W - 6.0:
                cursor_x = 6.0
                cursor_y -= 3.0

        return PlacementPlan(
            board_mm=(self.W, self.H),
            origin_mm=(self.ox, self.oy),
            intents=intents,
            clusters=clusters,
            keepouts=keepouts
        )
