"""Copper and Ground Plane Intelligence Engine for DESK (Mental Model M4).
Manages:
- Reference plane allocation based on actual physical stackup
- Power distribution polygon zones and zone priority hierarchy
- Solid vs. thermal relief pad connection rules
- Grid-based ground stitching via array synthesis
- Return-path continuity verification & reference discontinuity detection
- Unconnected copper island detection and edge setback enforcement
- Polygon boundary and keepout compliance checks
- Copper zone revision tracking, caching, and invalidation.

Zero external dependencies (pure Python standard library).
"""
import math
import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.profile import DesignProfile, LayerStackup

MIL = 39.37007874

@dataclass
class ConnectionConfig:
    connection_type: str = "thermal_relief"  # "solid" | "thermal_relief"
    spoke_count: int = 4
    spoke_width_mil: float = 12.0
    clearance_mil: float = 8.0

@dataclass
class CopperZoneSpec:
    zone_id: str
    net: str
    layer: int                             # 1=Top, 2=Bottom, 3=Inner1, etc.
    layer_name: str
    points_mm: List[Tuple[float, float]]  # Polygon vertices
    priority: int = 1                     # Higher number = higher pouring precedence
    connection_type: str = "thermal_relief" # "solid" or "thermal_relief"
    clearance_mil: float = 8.0
    spoke_width_mil: float = 10.0
    spoke_count: int = 4
    min_island_area_mm2: float = 2.0
    is_ground_plane: bool = False
    poured_area_mm2: float = 0.0
    status: str = "PLANNED"               # "PLANNED", "POURED", "STALE", "NOT_LIVE_VERIFIED"

@dataclass
class StitchingViaArray:
    net: str = "GND"
    diameter_mil: float = 24.0
    drill_mil: float = 12.0
    grid_spacing_mm: float = 2.54          # 100 mil standard grid
    from_layer: int = 1
    to_layer: int = 2
    via_locations: List[Tuple[float, float]] = field(default_factory=list) # (x_mm, y_mm)

@dataclass
class ReturnPathDiscontinuity:
    net: str
    track_start_mm: Tuple[float, float]
    track_end_mm: Tuple[float, float]
    layer: int
    reference_layer: int
    discontinuity_type: str                # "plane_split", "missing_reference", "slot_crossing"
    severity: str = "ERROR"                # "ERROR", "WARNING"
    recommendation: str = ""

class ConnectionRuleResolver:
    """Resolves thermal relief vs solid copper connection rules per net, component, and pin function."""

    @staticmethod
    def resolve_connection(net: str, comp_ref: str, pin_number: str = "", current_A: float = 0.2) -> ConnectionConfig:
        net_u = net.upper()
        ref_u = comp_ref.upper()

        # High current MOSFET thermal pads, inductors, and current sense shunts use solid connections
        is_power_device = any(ref_u.startswith(pfx) for pfx in ("Q", "M", "U_MOS", "D_PWR", "L", "RS", "SHUNT"))
        is_high_current_rail = current_A >= 3.0 or any(p in net_u for p in ("SW", "PHASE", "LX", "VBAT", "VBUS", "VOUT"))

        if is_power_device and is_high_current_rail:
            return ConnectionConfig(
                connection_type="solid",
                spoke_count=0,
                spoke_width_mil=0.0,
                clearance_mil=10.0
            )

        # Standard thermal relief with width proportional to current
        spoke_w = max(10.0, min(30.0, round(current_A * 8.0, 1)))
        return ConnectionConfig(
            connection_type="thermal_relief",
            spoke_count=4,
            spoke_width_mil=spoke_w,
            clearance_mil=8.0
        )

class CopperPlaneEngine:
    """Automated generation, synthesis, polygon planning, and verification of copper zones and planes."""

    @staticmethod
    def generate_ground_planes(board_dims_mm: Tuple[float, float],
                               profile: DesignProfile,
                               ground_net: str = "GND") -> List[CopperZoneSpec]:
        """Synthesizes perimeter-conforming ground reference planes for designated plane layers."""
        W, H = board_dims_mm
        setback_mm = profile.manufacturing.copper_to_edge_mil / MIL

        # Vertices respecting copper-to-edge restriction
        x1, y1 = round(setback_mm, 2), round(setback_mm, 2)
        x2, y2 = round(W - setback_mm, 2), round(H - setback_mm, 2)
        poly = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

        zones = []
        for l in profile.stackup:
            # Allocate ground plane to dedicated plane layers or bottom layer on 2-layer boards
            is_plane_candidate = (l.layer_type == "plane" and "GND" in l.name.upper()) or \
                                 (profile.layer_count == 2 and l.index == 2)
            if is_plane_candidate:
                z = CopperZoneSpec(
                    zone_id=f"GND_PLANE_L{l.index}_{l.name}",
                    net=ground_net,
                    layer=l.index,
                    layer_name=l.name,
                    points_mm=poly,
                    priority=1,
                    connection_type="thermal_relief",
                    clearance_mil=profile.derive_clearance_mil(ground_net, "3V3"),
                    spoke_width_mil=12.0,
                    is_ground_plane=True,
                    status="PLANNED"
                )
                zones.append(z)

        return zones

    @staticmethod
    def plan_power_polygons(net_name: str,
                            layer: int,
                            layer_name: str,
                            pads: List[Dict[str, Any]],
                            board_dims_mm: Tuple[float, float],
                            profile: DesignProfile,
                            margin_mm: float = 1.5,
                            priority: int = 2) -> Optional[CopperZoneSpec]:
        """Plans a dedicated power polygon around a cluster of power / switch-node pads."""
        matching_pads = [p for p in pads if p.get("net") == net_name]
        if not matching_pads:
            return None

        W, H = board_dims_mm
        setback_mm = profile.manufacturing.copper_to_edge_mil / MIL

        # Bounding box of pads
        xs = [p["x_mm"] for p in matching_pads]
        ys = [p["y_mm"] for p in matching_pads]
        min_x = max(setback_mm, min(xs) - margin_mm)
        max_x = min(W - setback_mm, max(xs) + margin_mm)
        min_y = max(setback_mm, min(ys) - margin_mm)
        max_y = min(H - setback_mm, max(ys) + margin_mm)

        if max_x <= min_x or max_y <= min_y:
            return None

        poly = [
            (round(min_x, 2), round(min_y, 2)),
            (round(max_x, 2), round(min_y, 2)),
            (round(max_x, 2), round(max_y, 2)),
            (round(min_x, 2), round(max_y, 2))
        ]

        curr = profile.get_current_for_net(net_name)
        rule = ConnectionRuleResolver.resolve_connection(net_name, matching_pads[0].get("ref", "U1"), current_A=curr)

        return CopperZoneSpec(
            zone_id=f"PWR_ZONE_{net_name}_L{layer}",
            net=net_name,
            layer=layer,
            layer_name=layer_name,
            points_mm=poly,
            priority=priority,
            connection_type=rule.connection_type,
            clearance_mil=profile.derive_clearance_mil(net_name, "GND"),
            spoke_width_mil=rule.spoke_width_mil,
            spoke_count=rule.spoke_count,
            is_ground_plane=False,
            status="PLANNED"
        )

    @staticmethod
    def check_polygon_boundary(zone: CopperZoneSpec,
                               board_dims_mm: Tuple[float, float],
                               edge_setback_mm: float = 0.3,
                               keepouts: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """Validates that a zone strictly complies with board boundaries and keepout constraints."""
        violations = []
        W, H = board_dims_mm
        keepouts = keepouts or []

        # Check vertex containment within setback outline
        for idx, (x, y) in enumerate(zone.points_mm):
            if x < (edge_setback_mm - 1e-3) or x > (W - edge_setback_mm + 1e-3) or \
               y < (edge_setback_mm - 1e-3) or y > (H - edge_setback_mm + 1e-3):
                violations.append(
                    f"Zone {zone.zone_id} vertex {idx} ({x:.2f}, {y:.2f}) violates board edge setback of {edge_setback_mm:.2f}mm."
                )

        # Check keepout collisions
        for ko in keepouts:
            ko_rect = ko.get("rect_mm")
            ko_layer = ko.get("layer")
            if ko_layer is not None and ko_layer != zone.layer:
                continue
            if ko_rect and len(ko_rect) == 4:
                kx1, ky1, kx2, ky2 = ko_rect
                for x, y in zone.points_mm:
                    if kx1 <= x <= kx2 and ky1 <= y <= ky2:
                        violations.append(
                            f"Zone {zone.zone_id} penetrates keepout '{ko.get('name', 'KEEPOUT')}' at ({x:.2f}, {y:.2f})."
                        )
                        break

        return violations

    @staticmethod
    def calculate_polygon_area_mm2(points: List[Tuple[float, float]]) -> float:
        """Computes polygon area using the Shoelace formula."""
        n = len(points)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]
        return round(abs(area) * 0.5, 4)

    @staticmethod
    def point_in_polygon(x: float, y: float, points: List[Tuple[float, float]]) -> bool:
        """Ray-casting point in polygon containment test."""
        inside = False
        n = len(points)
        for i in range(n):
            j = (i + 1) % n
            xi, yi = points[i]
            xj, yj = points[j]
            intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi)
            if intersect:
                inside = not inside
        return inside

    @classmethod
    def detect_copper_islands(cls,
                              zone: CopperZoneSpec,
                              pads: List[Dict[str, Any]],
                              min_island_area_mm2: float = 2.0) -> Dict[str, Any]:
        """Detects unconnected copper islands or small sliver areas that must be removed."""
        area = cls.calculate_polygon_area_mm2(zone.points_mm)
        connected_pads = 0

        for pad in pads:
            p_net = pad.get("net", "")
            p_layer = pad.get("layer", zone.layer)
            if p_net == zone.net and p_layer == zone.layer:
                px = pad.get("x_mm", 0.0)
                py = pad.get("y_mm", 0.0)
                if cls.point_in_polygon(px, py, zone.points_mm):
                    connected_pads += 1

        if connected_pads == 0:
            return {
                "is_island": True,
                "connected_pad_count": 0,
                "area_mm2": area,
                "action": "remove",
                "reason": "unconnected_floating_copper"
            }

        if area < min_island_area_mm2:
            return {
                "is_island": True,
                "connected_pad_count": connected_pads,
                "area_mm2": area,
                "action": "remove",
                "reason": "below_min_island_area"
            }

        return {
            "is_island": False,
            "connected_pad_count": connected_pads,
            "area_mm2": area,
            "action": "keep",
            "reason": "valid_copper_zone"
        }

    @staticmethod
    def synthesize_stitching_vias(board_dims_mm: Tuple[float, float],
                                  obstacles: List[Tuple[float, float, float]], # (x_mm, y_mm, radius_mm)
                                  keepouts: Optional[List[Dict[str, Any]]] = None,
                                  grid_spacing_mm: float = 2.54,
                                  edge_setback_mm: float = 2.0) -> StitchingViaArray:
        """Calculates a collision-free array of ground stitching vias across plane boundaries."""
        W, H = board_dims_mm
        keepouts = keepouts or []
        vias: List[Tuple[float, float]] = []

        x_coords = []
        x = edge_setback_mm
        while x <= W - edge_setback_mm:
            x_coords.append(round(x, 2))
            x += grid_spacing_mm

        y_coords = []
        y = edge_setback_mm
        while y <= H - edge_setback_mm:
            y_coords.append(round(y, 2))
            y += grid_spacing_mm

        # Filter candidate positions against obstacles and keepouts
        for cx in x_coords:
            for cy in y_coords:
                collision = False
                for ox, oy, orad in obstacles:
                    if math.hypot(cx - ox, cy - oy) < (orad + 0.6): # 0.6mm safety clearance
                        collision = True
                        break
                if collision: continue

                for ko in keepouts:
                    rect = ko.get("rect_mm")
                    if rect:
                        rx1, ry1, rx2, ry2 = rect
                        if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
                            collision = True
                            break
                if collision: continue

                vias.append((cx, cy))

        return StitchingViaArray(
            net="GND",
            grid_spacing_mm=grid_spacing_mm,
            via_locations=vias
        )

    @staticmethod
    def evaluate_return_path_continuity(critical_tracks: List[Dict[str, Any]],
                                        planes: List[CopperZoneSpec],
                                        stackup: List[LayerStackup]) -> List[ReturnPathDiscontinuity]:
        """Verifies that high-speed / RF / differential tracks have unbroken ground planes beneath them."""
        discontinuities = []
        plane_by_layer = {p.layer: p for p in planes if p.is_ground_plane}

        ref_layer_map = {}
        for idx, l in enumerate(stackup):
            if l.layer_type == "signal":
                closest_plane = None
                for candidate in stackup:
                    if candidate.layer_type == "plane" or "GND" in candidate.name:
                        if closest_plane is None or abs(candidate.index - l.index) < abs(closest_plane.index - l.index):
                            closest_plane = candidate
                if closest_plane:
                    ref_layer_map[l.index] = closest_plane.index

        for trk in critical_tracks:
            net = trk.get("net", "")
            s_layer = trk.get("layer", 1)
            x1, y1 = trk.get("start_mm", (0.0, 0.0))
            x2, y2 = trk.get("end_mm", (0.0, 0.0))

            expected_ref = ref_layer_map.get(s_layer)
            if not expected_ref or expected_ref not in plane_by_layer:
                discontinuities.append(ReturnPathDiscontinuity(
                    net=net,
                    track_start_mm=(x1, y1),
                    track_end_mm=(x2, y2),
                    layer=s_layer,
                    reference_layer=expected_ref or 0,
                    discontinuity_type="missing_reference",
                    severity="ERROR",
                    recommendation=f"Net {net} on layer {s_layer} lacks adjacent ground reference plane."
                ))
            else:
                plane = plane_by_layer[expected_ref]
                pts = plane.points_mm
                if len(pts) >= 4:
                    px_min = min(p[0] for p in pts)
                    px_max = max(p[0] for p in pts)
                    py_min = min(p[1] for p in pts)
                    py_max = max(p[1] for p in pts)
                    if not (px_min <= x1 <= px_max and py_min <= y1 <= py_max and
                            px_min <= x2 <= px_max and py_min <= y2 <= py_max):
                        discontinuities.append(ReturnPathDiscontinuity(
                            net=net,
                            track_start_mm=(x1, y1),
                            track_end_mm=(x2, y2),
                            layer=s_layer,
                            reference_layer=expected_ref,
                            discontinuity_type="slot_crossing",
                            severity="ERROR",
                            recommendation=f"Net {net} crosses beyond ground plane boundary on layer {expected_ref}."
                        ))

        return discontinuities


class CopperZoneRevisionTracker:
    """Revision tracking, fingerprinting, and targeted invalidation for copper zones."""

    def __init__(self):
        self._zones: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def compute_fingerprint(zone: CopperZoneSpec, profile_hash: str) -> str:
        payload = {
            "zone_id": zone.zone_id,
            "net": zone.net,
            "layer": zone.layer,
            "priority": zone.priority,
            "points": zone.points_mm,
            "connection_type": zone.connection_type,
            "clearance_mil": zone.clearance_mil,
            "spoke_width_mil": zone.spoke_width_mil,
            "profile_hash": profile_hash
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:16]

    def register_zone(self, zone: CopperZoneSpec, profile_hash: str) -> str:
        fp = self.compute_fingerprint(zone, profile_hash)
        self._zones[zone.zone_id] = {
            "fingerprint": fp,
            "zone": zone,
            "net": zone.net,
            "layer": zone.layer,
            "is_stale": False,
            "poured": False,
            "updated_ts": time.time()
        }
        return fp

    def mark_poured(self, zone_id: str, poured_area_mm2: float):
        if zone_id in self._zones:
            self._zones[zone_id]["poured"] = True
            self._zones[zone_id]["is_stale"] = False
            self._zones[zone_id]["zone"].poured_area_mm2 = poured_area_mm2
            self._zones[zone_id]["zone"].status = "NOT_LIVE_VERIFIED"  # Offline poured model only

    def invalidate_zones(self, affected_nets: Set[str], affected_layers: Optional[Set[int]] = None):
        """Invalidates zones matching affected nets or layers."""
        for zid, record in self._zones.items():
            net_match = record["net"] in affected_nets
            layer_match = (affected_layers is not None) and (record["layer"] in affected_layers)
            if net_match or layer_match:
                record["is_stale"] = True
                record["zone"].status = "STALE"

    def get_stale_zones(self) -> List[str]:
        return [zid for zid, rec in self._zones.items() if rec.get("is_stale", False)]

    def is_zone_stale(self, zone_id: str) -> bool:
        if zone_id not in self._zones:
            return True
        return self._zones[zone_id].get("is_stale", False)
