"""Subsystem Nine: True Physical Pad-to-Pad Connectivity Verification Engine.
Performs rigorous geometric copper intersection, segment-to-segment T-junction checks,
multilayer via transitions, and connected-component graph analysis.
Replaces naive net-name occurrence heuristics with physical electrical proof.
Zero external dependencies.
"""
from __future__ import annotations
import math
from typing import Dict, List, Tuple, Set, Optional, Any
from dataclasses import dataclass, field


@dataclass
class NetConnectivityReport:
    """Detailed physical connectivity assessment for a single electrical net."""
    net_name: str
    status: str  # "FULLY_CONNECTED", "PARTIALLY_CONNECTED", "MISSING_ROUTE", "UNCONNECTED_PADS", "ILLEGAL_CONNECTION"
    is_complete: bool
    expected_pad_count: int
    connected_pad_count: int
    connected_components_count: int
    unconnected_pads: List[str]
    track_count: int
    via_count: int
    total_wire_length_mil: float
    violations: List[str] = field(default_factory=list)


@dataclass
class BoardConnectivityResult:
    """Board-level physical connectivity assessment."""
    total_nets: int
    fully_connected_nets: int
    partially_connected_nets: int
    missing_nets: int
    illegal_connection_nets: int
    overall_completion_pct: float
    is_100_percent_routed: bool
    net_reports: Dict[str, NetConnectivityReport]
    summary: str


def _dist_point_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> Tuple[float, float, float]:
    """Computes minimum Euclidean distance from (px, py) to line segment (x1, y1)-(x2, y2).
    Returns (distance, nearest_x, nearest_y).
    """
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-9:
        return (math.hypot(px - x1, py - y1), x1, y1)

    # Project point onto segment parameter t
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return (math.hypot(px - proj_x, py - proj_y), proj_x, proj_y)


def _segments_overlap_or_touch(
    s1: Tuple[float, float, float, float, float],  # (x1, y1, x2, y2, width)
    s2: Tuple[float, float, float, float, float],
    tol_mil: float = 1.0
) -> bool:
    """Checks if two track segments touch, overlap, or form a T-junction within electrical tolerance."""
    x1, y1, x2, y2, w1 = s1
    x3, y3, x4, y4, w2 = s2
    thresh = (w1 + w2) / 2.0 + tol_mil

    # 1. Bounding box pre-check
    if max(x1, x2) + thresh < min(x3, x4) or max(x3, x4) + thresh < min(x1, x2):
        return False
    if max(y1, y2) + thresh < min(y3, y4) or max(y3, y4) + thresh < min(y1, y2):
        return False

    # 2. Check endpoints of s1 against segment s2
    d1, _, _ = _dist_point_to_segment(x1, y1, x3, y3, x4, y4)
    if d1 <= thresh:
        return True
    d2, _, _ = _dist_point_to_segment(x2, y2, x3, y3, x4, y4)
    if d2 <= thresh:
        return True

    # 3. Check endpoints of s2 against segment s1
    d3, _, _ = _dist_point_to_segment(x3, y3, x1, y1, x2, y2)
    if d3 <= thresh:
        return True
    d4, _, _ = _dist_point_to_segment(x4, y4, x1, y1, x2, y2)
    if d4 <= thresh:
        return True

    # 4. Standard segment-segment intersection
    def ccw(ax, ay, bx, by, cx, cy):
        return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)

    if (ccw(x1, y1, x3, y3, x4, y4) != ccw(x2, y2, x3, y3, x4, y4)) and \
       (ccw(x1, y1, x2, y2, x3, y3) != ccw(x1, y1, x2, y2, x4, y4)):
        return True

    return False


def pad_xy(comp: Dict[str, Any], pad: Dict[str, Any], base_x: Optional[float] = None, base_y: Optional[float] = None,
           rot_override: Optional[float] = None) -> Tuple[float, float]:
    """Absolute pad centre (mil) for a PCB-dump record.

    `pad["dx"]/["dy"]` are offsets in the BOARD frame at the component's current rotation
    (`tools/pcb_dump.py` stores pad.getState_X() - component.x). They must not be rotated again by the
    component's own rotation; only a rotation delta to a *planned* orientation (`rot_override`) is applied.
    Verified on the WATCH live dump 2026-11-12: 405/1130 SES track endpoints land on their pads without the
    extra rotation versus 324 with it (QA-03)."""
    cx = float(comp.get("x", 0.0)) if base_x is None else float(base_x)
    cy = float(comp.get("y", 0.0)) if base_y is None else float(base_y)
    dx, dy = float(pad.get("dx", 0.0)), float(pad.get("dy", 0.0))
    if rot_override is not None:
        delta = math.radians(float(rot_override) - float(comp.get("rot", 0.0) or 0.0))
        if abs(delta) > 1e-9:
            dx, dy = dx * math.cos(delta) - dy * math.sin(delta), dx * math.sin(delta) + dy * math.cos(delta)
    return cx + dx, cy + dy


def pad_size_mil(p: Dict[str, Any]) -> Tuple[float, float]:
    """Pad width/height in mil from a PCB-dump pad record. EasyEDA dumps carry the size inside
    `shape: ["RECT"|"ELLIPSE"|..., w, h, ...]`; explicit w/h keys win when present. Falling back to
    15 mil for every pad (the previous behaviour) made track endpoints miss real 30-40 mil pads and
    produced false "partially connected" verdicts (QA-03)."""
    if "w" in p or "width" in p:
        return float(p.get("w", p.get("width", 15.0))), float(p.get("h", p.get("height", 15.0)))
    shape = p.get("shape")
    if isinstance(shape, (list, tuple)) and len(shape) >= 3:
        try:
            w, h = float(shape[1]), float(shape[2])
            if w > 0 and h > 0:
                return w, h
        except (TypeError, ValueError):
            pass
    return 15.0, 15.0


def _layer_rank(layer: int) -> int:
    """Physical stacking order for EasyEDA layer ids: 1 Top, 15..46 Inner1..Inner32, 2 Bottom.
    Through-hole markers (11/12) and unknown ids rank as 'all layers' (-1)."""
    if layer == 1:
        return 0
    if 15 <= layer <= 46:
        return layer - 14
    if layer == 2:
        return 1000
    return -1


def _span_covers(start_layer: int, end_layer: int, layer: int) -> bool:
    a, b, l = _layer_rank(start_layer), _layer_rank(end_layer), _layer_rank(layer)
    if l < 0 or a < 0 or b < 0:
        return True
    return min(a, b) <= l <= max(a, b)


def _point_in_polygon(x: float, y: float, pts) -> bool:
    inside = False
    n = len(pts)
    for i in range(n):
        xi, yi = pts[i][0], pts[i][1]
        xj, yj = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < xint:
                inside = not inside
    return inside


class DisjointSet:
    """Union-Find data structure with path compression."""
    def __init__(self):
        self.parent: Dict[Any, Any] = {}

    def find(self, x: Any) -> Any:
        if x not in self.parent:
            self.parent[x] = x
            return x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: Any, y: Any) -> None:
        rx = self.find(x)
        ry = self.find(y)
        if rx != ry:
            self.parent[rx] = ry


class SESParser:
    """Extracts physical track segments and vias from Specctra SES files."""

    @classmethod
    def parse_ses_copper(cls, ses_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parses Specctra SES text into normalized track segment and via dictionaries."""
        from desk.routing.dsn import SExprParser
        tree = SExprParser.parse(ses_text)
        if not tree or not isinstance(tree, list):
            return ([], [])

        tracks: List[Dict[str, Any]] = []
        vias: List[Dict[str, Any]] = []

        # Find routes node
        routes_node = None
        for item in tree[1:]:
            if isinstance(item, list) and item and str(item[0]).lower() == "routes":
                routes_node = item
                break

        if not routes_node:
            return ([], [])

        # Check resolution
        resolution_scale = 1000.0
        for item in routes_node[1:]:
            if isinstance(item, list) and item and str(item[0]).lower() == "resolution":
                if len(item) > 2 and str(item[1]).lower() == "mil":
                    resolution_scale = float(item[2])

        # Find network or network_out node inside routes
        network_node = None
        for item in routes_node[1:]:
            if isinstance(item, list) and item and str(item[0]).lower() in ("network", "network_out"):
                network_node = item
                break

        if not network_node:
            return ([], [])

        # EasyEDA layer ids: 1 top, 2 bottom, 15.. inner (same ids as the PCB dump, vias and declared zones)
        layer_map = {"toplayer": 1, "top": 1, "bottomlayer": 2, "bottom": 2}
        layer_map.update({f"inner{i}": 14 + i for i in range(1, 33)})

        for item in network_node[1:]:
            if isinstance(item, list) and item and str(item[0]).lower() == "net":
                net_name = str(item[1]).strip("'\"")
                for sub in item[2:]:
                    if isinstance(sub, list) and sub:
                        sub_tag = str(sub[0]).lower()
                        if sub_tag == "wire" and len(sub) > 1 and isinstance(sub[1], list):
                            path_node = sub[1]
                            if str(path_node[0]).lower() == "path" and len(path_node) > 3:
                                lay_str = str(path_node[1]).lower()
                                lay_num = layer_map.get(lay_str, 1)
                                width = float(path_node[2]) / resolution_scale
                                coords = [float(c) / resolution_scale for c in path_node[3:]]
                                for i in range(0, len(coords) - 3, 2):
                                    tracks.append({
                                        "net": net_name,
                                        "start_x": coords[i],
                                        "start_y": coords[i + 1],
                                        "end_x": coords[i + 2],
                                        "end_y": coords[i + 3],
                                        "width": width,
                                        "layer": lay_num
                                    })
                        elif sub_tag == "via" and len(sub) >= 4:
                            via_x = float(sub[2]) / resolution_scale
                            via_y = float(sub[3]) / resolution_scale
                            vias.append({
                                "net": net_name,
                                "x": via_x,
                                "y": via_y,
                                "diameter": 24.0,
                                "start_layer": 1,
                                "end_layer": 2
                            })

        return (tracks, vias)


class PhysicalConnectivityVerifier:
    """Verifies true physical copper continuity and pad reachability across all PCB layers."""

    @classmethod
    def verify_board(
        cls,
        pcb_dump: Dict[str, Any],
        tracks: List[Dict[str, Any]],
        vias: Optional[List[Dict[str, Any]]] = None,
        zones: Optional[List[Dict[str, Any]]] = None,
        tolerance_mil: float = 1.0
    ) -> BoardConnectivityResult:
        """Evaluates pad-to-pad physical continuity for every net on the board."""
        vias = vias or []
        zones = zones or []

        # 1. Gather all pads per net from pcb_dump
        # Pads: ref.pad -> {x, y, layer, net, width, height}
        net_pads: Dict[str, List[Dict[str, Any]]] = {}
        for ref, comp in pcb_dump.items():
            if not isinstance(comp, dict): continue
            comp_layer = int(comp.get("layer", 1))

            for p in comp.get("pads", []):
                net = (p.get("net") or "").strip()
                if not net: continue

                px, py = pad_xy(comp, p)
                pad_num = str(p.get("num", ""))
                pad_layer = int(p.get("layer", comp_layer))
                pad_w, pad_h = pad_size_mil(p)

                pad_id = f"{ref}.{pad_num}"
                pad_data = {
                    "id": pad_id,
                    "ref": ref,
                    "pad": pad_num,
                    "net": net,
                    "x": px,
                    "y": py,
                    "layer": pad_layer,
                    "width": pad_w,
                    "height": pad_h,
                    "radius": max(pad_w, pad_h) / 2.0
                }
                if net not in net_pads:
                    net_pads[net] = []
                net_pads[net].append(pad_data)

        # 2. Gather tracks and vias per net
        net_tracks: Dict[str, List[Dict[str, Any]]] = {}
        for trk in tracks:
            net = (trk.get("net") or "").strip()
            if not net: continue
            if net not in net_tracks:
                net_tracks[net] = []
            net_tracks[net].append(trk)

        net_vias: Dict[str, List[Dict[str, Any]]] = {}
        for v in vias:
            net = (v.get("net") or "").strip()
            if not net: continue
            if net not in net_vias:
                net_vias[net] = []
            net_vias[net].append(v)

        # Poured copper: {"net", "layer", "polygon": [[x_mil, y_mil], ...]} per zone. A zone is a conductor:
        # pads on its layer inside it, vias penetrating its layer inside it and tracks on its layer touching it
        # are all connected through the zone (previously ignored -> false "partially connected" for plane nets).
        net_zones: Dict[str, List[Dict[str, Any]]] = {}
        for z in zones:
            net = (z.get("net") or "").strip()
            poly = z.get("polygon") or z.get("points") or []
            if not net or len(poly) < 3: continue
            net_zones.setdefault(net, []).append(z)

        # 3. Evaluate each populated net
        net_reports: Dict[str, NetConnectivityReport] = {}
        fully_connected_count = 0
        partially_connected_count = 0
        missing_count = 0
        illegal_count = 0

        for net_name, pads in net_pads.items():
            report = cls.verify_single_net(
                net_name=net_name,
                expected_pads=pads,
                tracks=net_tracks.get(net_name, []),
                vias=net_vias.get(net_name, []),
                tolerance_mil=tolerance_mil,
                zones=net_zones.get(net_name, []),
            )
            net_reports[net_name] = report

            if report.status == "FULLY_CONNECTED":
                fully_connected_count += 1
            elif report.status == "PARTIALLY_CONNECTED":
                partially_connected_count += 1
            elif report.status == "MISSING_ROUTE":
                missing_count += 1
            elif report.status == "ILLEGAL_CONNECTION":
                illegal_count += 1

        total = len(net_pads)
        pct = round((fully_connected_count / max(1, total)) * 100.0, 1)
        is_100 = (fully_connected_count == total and total > 0)

        summary = (
            f"Physical Connectivity: {fully_connected_count}/{total} nets fully connected ({pct}%). "
            f"Partially routed: {partially_connected_count}, Unrouted: {missing_count}, Illegal: {illegal_count}."
        )

        return BoardConnectivityResult(
            total_nets=total,
            fully_connected_nets=fully_connected_count,
            partially_connected_nets=partially_connected_count,
            missing_nets=missing_count,
            illegal_connection_nets=illegal_count,
            overall_completion_pct=pct,
            is_100_percent_routed=is_100,
            net_reports=net_reports,
            summary=summary
        )

    @classmethod
    def verify_single_net(
        cls,
        net_name: str,
        expected_pads: List[Dict[str, Any]],
        tracks: List[Dict[str, Any]],
        vias: List[Dict[str, Any]],
        tolerance_mil: float = 1.0,
        zones: Optional[List[Dict[str, Any]]] = None,
    ) -> NetConnectivityReport:
        """Computes connected components for a single net across all physical conductors
        (tracks, vias and poured copper zones)."""
        zones = zones or []
        pad_count = len(expected_pads)
        if pad_count == 0:
            return NetConnectivityReport(
                net_name=net_name,
                status="FULLY_CONNECTED",
                is_complete=True,
                expected_pad_count=0,
                connected_pad_count=0,
                connected_components_count=0,
                unconnected_pads=[],
                track_count=0,
                via_count=0,
                total_wire_length_mil=0.0
            )

        if len(tracks) == 0 and len(vias) == 0 and len(zones) == 0:
            # Zero routing has occurred for this net
            unconn = [p["id"] for p in expected_pads]
            return NetConnectivityReport(
                net_name=net_name,
                status="MISSING_ROUTE" if pad_count > 1 else "FULLY_CONNECTED",
                is_complete=(pad_count <= 1),
                expected_pad_count=pad_count,
                connected_pad_count=1 if pad_count == 1 else 0,
                connected_components_count=pad_count,
                unconnected_pads=unconn if pad_count > 1 else [],
                track_count=0,
                via_count=0,
                total_wire_length_mil=0.0
            )

        dsu = DisjointSet()
        total_len = 0.0

        # Register every pad node in DSU
        for p in expected_pads:
            dsu.find(p["id"])

        # Normalize track segments
        # Format: (x1, y1, x2, y2, width, layer, seg_id)
        segments: List[Tuple[float, float, float, float, float, int, str]] = []
        for i, trk in enumerate(tracks):
            x1 = float(trk.get("start_x", trk.get("x1", 0.0)))
            y1 = float(trk.get("start_y", trk.get("y1", 0.0)))
            x2 = float(trk.get("end_x", trk.get("x2", 0.0)))
            y2 = float(trk.get("end_y", trk.get("y2", 0.0)))
            w = float(trk.get("width", 10.0))
            lay = int(trk.get("layer", 1))
            seg_id = f"T_{i}"
            segments.append((x1, y1, x2, y2, w, lay, seg_id))
            dsu.find(seg_id)
            total_len += math.hypot(x2 - x1, y2 - y1)

        # Normalize vias
        # Format: (x, y, diameter, start_lay, end_lay, via_id)
        via_nodes: List[Tuple[float, float, float, int, int, str]] = []
        for i, v in enumerate(vias):
            vx = float(v.get("x", 0.0))
            vy = float(v.get("y", 0.0))
            vd = float(v.get("diameter", v.get("size", 24.0)))
            v_start = int(v.get("start_layer", 1))
            v_end = int(v.get("end_layer", 2))
            via_id = f"V_{i}"
            via_nodes.append((vx, vy, vd, v_start, v_end, via_id))
            dsu.find(via_id)

        # Zones as conductors
        zone_nodes: List[Tuple[int, list, str]] = []
        for i, z in enumerate(zones):
            poly = [(float(pt[0]), float(pt[1])) for pt in (z.get("polygon") or z.get("points") or [])]
            if len(poly) < 3:
                continue
            zid = f"Z_{i}"
            zone_nodes.append((int(z.get("layer", 1)), poly, zid))
            dsu.find(zid)
        for z_lay, poly, zid in zone_nodes:
            for s in segments:
                if s[5] == z_lay and (_point_in_polygon(s[0], s[1], poly) or _point_in_polygon(s[2], s[3], poly)):
                    dsu.union(zid, s[6])
            for vx, vy, vd, v_start, v_end, via_id in via_nodes:
                if _span_covers(v_start, v_end, z_lay) and _point_in_polygon(vx, vy, poly):
                    dsu.union(zid, via_id)
            for p in expected_pads:
                if (p["layer"] in (11, 12) or p["layer"] == z_lay) and _point_in_polygon(p["x"], p["y"], poly):
                    dsu.union(zid, p["id"])

        # Connect track segment to track segment on same layer
        n_segs = len(segments)
        for i in range(n_segs):
            s1 = segments[i]
            for j in range(i + 1, n_segs):
                s2 = segments[j]
                if s1[5] == s2[5]:  # Same layer check
                    if _segments_overlap_or_touch(s1[:5], s2[:5], tol_mil=tolerance_mil):
                        dsu.union(s1[6], s2[6])

        # Connect vias to track segments across active via layer span
        for v in via_nodes:
            vx, vy, vd, v_start, v_end, via_id = v
            v_radius = vd / 2.0
            min_lay = min(v_start, v_end)
            max_lay = max(v_start, v_end)

            for s in segments:
                s_lay = s[5]
                # Via penetrates every layer between its start and end in physical stacking order
                if _span_covers(v_start, v_end, s_lay):
                    d, _, _ = _dist_point_to_segment(vx, vy, s[0], s[1], s[2], s[3])
                    touch_thresh = v_radius + s[4] / 2.0 + tolerance_mil
                    if d <= touch_thresh:
                        dsu.union(via_id, s[6])

        # Connect pads to track segments and vias
        for p in expected_pads:
            pid = p["id"]
            px, py = p["x"], p["y"]
            p_lay = p["layer"]
            p_rad = p["radius"]

            # Connect pad to tracks
            for s in segments:
                s_lay = s[5]
                # Multi-layer through-hole pad (11 or 12) connects on any copper layer
                is_layer_match = (p_lay in (11, 12)) or (p_lay == s_lay)
                if is_layer_match:
                    d, _, _ = _dist_point_to_segment(px, py, s[0], s[1], s[2], s[3])
                    touch_thresh = p_rad + s[4] / 2.0 + tolerance_mil
                    if d <= touch_thresh:
                        dsu.union(pid, s[6])

            # Connect pad to vias
            for v in via_nodes:
                vx, vy, vd, v_start, v_end, via_id = v
                is_layer_match = (p_lay in (11, 12)) or _span_covers(v_start, v_end, p_lay)
                if is_layer_match:
                    d = math.hypot(px - vx, py - vy)
                    if d <= (p_rad + vd / 2.0 + tolerance_mil):
                        dsu.union(pid, via_id)

        # Check connected components among expected pads
        pad_roots = {}
        for p in expected_pads:
            pid = p["id"]
            root = dsu.find(pid)
            if root not in pad_roots:
                pad_roots[root] = []
            pad_roots[root].append(pid)

        # Find pads that are not connected to any track or via
        unconnected = []
        for p in expected_pads:
            pid = p["id"]
            root = dsu.find(pid)
            # If the root is itself and no tracks/vias share its root
            has_copper = False
            for s in segments:
                if dsu.find(s[6]) == root:
                    has_copper = True; break
            if not has_copper:
                for v in via_nodes:
                    if dsu.find(v[5]) == root:
                        has_copper = True; break
            if not has_copper:
                for _, _, zid in zone_nodes:
                    if dsu.find(zid) == root:
                        has_copper = True; break
            if not has_copper:
                unconnected.append(pid)

        unique_components = len(pad_roots)
        if unique_components == 1 and len(unconnected) == 0:
            status = "FULLY_CONNECTED"
            is_complete = True
            conn_pads = pad_count
        elif len(unconnected) == pad_count:
            status = "MISSING_ROUTE"
            is_complete = False
            conn_pads = 0
        else:
            status = "PARTIALLY_CONNECTED"
            is_complete = False
            conn_pads = pad_count - len(unconnected)

        return NetConnectivityReport(
            net_name=net_name,
            status=status,
            is_complete=is_complete,
            expected_pad_count=pad_count,
            connected_pad_count=conn_pads,
            connected_components_count=unique_components,
            unconnected_pads=unconnected,
            track_count=len(tracks),
            via_count=len(vias),
            total_wire_length_mil=round(total_len, 1)
        )
