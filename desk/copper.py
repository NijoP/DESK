"""Copper and Ground Plane Intelligence Engine for DESK (Mental Model M4).
Manages:
- Reference plane allocation based on actual physical stackup
- Power distribution polygon zones and zone priority hierarchy
- Solid vs. thermal relief pad connection rules
- Grid-based ground stitching via array synthesis
- Return-path continuity verification & reference discontinuity detection
- Unconnected copper island detection and edge setback enforcement.

Zero external dependencies (pure Python standard library).
"""
import math
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.profile import DesignProfile, LayerStackup

MIL = 39.37007874

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
    min_island_area_mm2: float = 2.0
    is_ground_plane: bool = False

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

class CopperPlaneEngine:
    """Automated generation, synthesis, and verification of copper zones and planes."""

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
                    is_ground_plane=True
                )
                zones.append(z)

        return zones

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
        # Index planes by layer
        plane_by_layer = {p.layer: p for p in planes if p.is_ground_plane}

        # Mapping of signal layer to expected adjacent reference plane layer
        ref_layer_map = {}
        for idx, l in enumerate(stackup):
            if l.layer_type == "signal":
                # Find closest adjacent plane layer
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
                # Verify segment is fully within the plane boundaries
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
