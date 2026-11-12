"""Deterministic copper-pour geometry for EasyEDA Pro clients whose pour engine cannot be driven by the API.

Why (Plotus run, 2026-11-12, EasyEDA Pro 3.2.149 / pro-api 0.2.53): `IPCB_PrimitivePour.rebuildCopperRegion()`
issues rpcCall("extensionApi.PCB_PrimitivePour.rebuildCopperRegion", {ids, isLast:false}) and then throws
"Cannot read properties of undefined (reading 'length')"; `getCopperRegion()` stays undefined and DRC still
reports every GND pad unconnected. A pour therefore needed a human "Rebuild all copper" click.

This module computes the poured copper itself and emits it as static `pcb_PrimitiveFill` polygons on the
plane net, so the result is fully API-driven and reproducible:

    copper(layer) = board_area(edge inset)
                    - keepouts
                    - buffer(every other-net pad / track / via on that layer, clearance)
                    - thermal-relief rings around through-hole plane-net pads (+ 4 spokes)
    -> sliver removal (opening by min_neck/2) -> island pruning (must touch a plane-net pad or via on the layer,
       and be >= min_island_mm2).

All geometry is in mm. Shapely (>= 2.0) is required; it is an optional dependency of DESK (import is lazy).
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

MIL = 39.37007874


def _sh():
    import shapely  # noqa: F401
    from shapely.geometry import Polygon, Point, LineString, box, MultiPolygon
    from shapely.ops import unary_union
    from shapely import affinity
    return Polygon, Point, LineString, box, MultiPolygon, unary_union, affinity


def pad_geometry(pad: Dict[str, Any]):
    """Shapely geometry (mm) of a pad readback dict {x,y (mil), rot (deg), shape:[TYPE,w,h,...] (mil)}."""
    Polygon, Point, LineString, box, MultiPolygon, unary_union, affinity = _sh()
    sh = pad.get("shape") or ["RECT", 20, 20]
    kind = str(sh[0]).upper() if sh else "RECT"
    nums = [v for v in sh[1:3] if isinstance(v, (int, float))]
    if len(nums) == 2:
        w, h = nums[0] / MIL, nums[1] / MIL
    elif len(nums) == 1:
        w = h = nums[0] / MIL
    else:  # polygon pads: use the bounding box of every numeric pair found
        flat = []
        def walk(o):
            if isinstance(o, (list, tuple)):
                for v in o: walk(v)
            elif isinstance(o, (int, float)):
                flat.append(float(o))
        walk(sh[1:])
        xs, ys = flat[0::2], flat[1::2]
        w = (max(xs) - min(xs)) / MIL if xs else 0.5
        h = (max(ys) - min(ys)) / MIL if ys else 0.5
    cx, cy = pad["x"] / MIL, pad["y"] / MIL
    if kind in ("ELLIPSE", "CIRCLE") and abs(w - h) < 1e-6:
        g = Point(0, 0).buffer(w / 2, quad_segs=12)
    elif kind in ("OVAL", "ELLIPSE"):
        r = min(w, h) / 2
        if w >= h:
            g = LineString([(-(w / 2 - r), 0), (w / 2 - r, 0)]).buffer(r, quad_segs=12)
        else:
            g = LineString([(0, -(h / 2 - r)), (0, h / 2 - r)]).buffer(r, quad_segs=12)
    else:
        g = box(-w / 2, -h / 2, w / 2, h / 2)
    g = affinity.rotate(g, pad.get("rot") or 0.0, origin=(0, 0))
    return affinity.translate(g, cx, cy)


def pad_on_layer(pad: Dict[str, Any], layer: int) -> bool:
    return pad.get("layer") in (layer, 12)


def compute_plane_fill(layer: int, net: str, board_poly_mm: Sequence[Tuple[float, float]],
                       pads: List[Dict[str, Any]], tracks: List[Dict[str, Any]], vias: List[Dict[str, Any]],
                       keepouts_mm: Optional[List[Sequence[float]]] = None,
                       clearance_mm: float = 0.3, edge_mm: float = 0.5,
                       thermal_gap_mm: float = 0.3, spoke_mm: float = 0.35,
                       min_neck_mm: float = 0.2, min_island_mm2: float = 2.0,
                       simplify_mm: float = 0.02) -> Dict[str, Any]:
    """Return {"polygons": [shapely Polygon], "removed_islands": n, "area_mm2": a}. Units mm.
    simplify_mm (default 0.02) bounds the vertex count (long vertex lists froze the editor, INC-20261111-008);
    it can move an edge by at most simplify_mm, so the effective clearance is >= clearance_mm - simplify_mm."""
    Polygon, Point, LineString, box, MultiPolygon, unary_union, affinity = _sh()
    area = Polygon(board_poly_mm).buffer(-edge_mm, join_style=2)
    cut = []        # everything removed from the plane
    other_net = []  # other-net copper grown by the clearance (spokes must stay out of it)
    for k in keepouts_mm or []:
        cut.append(box(*k)); other_net.append(box(*k))
    anchors = []          # plane-net copper the fill may touch
    strong = []           # plane-net vias + through-hole pads: a piece must touch one to count as connected
    thermal_add = []
    for p in pads:
        if not pad_on_layer(p, layer):
            continue
        g = pad_geometry(p)
        if p.get("net") == net:
            anchors.append(g)
            if p.get("layer") == 12:  # through-hole plane pad -> thermal relief
                strong.append(g)
                ring = g.buffer(thermal_gap_mm)
                cut.append(ring)
                c = g.centroid; r = math.sqrt(g.area / math.pi) + thermal_gap_mm + 0.05
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    thermal_add.append(LineString([(c.x, c.y), (c.x + dx * (r + 0.2), c.y + dy * (r + 0.2))]).buffer(spoke_mm / 2, cap_style=2))
            continue
        # Other-net pads: rotation-proof circumscribed circle. Pad rotation in readback is not always the absolute
        # orientation (module pads on a 270-deg part came out sideways -> 3.2 mil fill-to-pad errors), so the
        # clearance zone must not depend on it.
        b = g.minimum_rotated_rectangle if hasattr(g, "minimum_rotated_rectangle") else g
        rr = max(math.dist(b.centroid.coords[0], pt) for pt in b.exterior.coords) if b.geom_type == "Polygon" else math.sqrt(g.area / math.pi)
        cut.append(g.centroid.buffer(rr + clearance_mm, quad_segs=10)); other_net.append(cut[-1])
    for t in tracks:
        if t.get("layer") != layer or t.get("net") == net:
            continue
        seg = LineString([(t["x1"] / MIL, t["y1"] / MIL), (t["x2"] / MIL, t["y2"] / MIL)])
        cut.append(seg.buffer(t["w"] / MIL / 2 + clearance_mm, quad_segs=6)); other_net.append(cut[-1])
    for v in vias:
        c = Point(v["x"] / MIL, v["y"] / MIL)
        if v.get("net") == net:
            anchors.append(c.buffer(v["d"] / MIL / 2)); strong.append(anchors[-1])
            continue
        cut.append(c.buffer(v["d"] / MIL / 2 + clearance_mm, quad_segs=8)); other_net.append(cut[-1])
    copper = area.difference(unary_union(cut))
    if thermal_add:
        spokes = unary_union(thermal_add).intersection(area)
        # spokes must not enter any other-net clearance zone or keep-out
        copper = unary_union([copper, spokes.difference(unary_union(other_net))])
    # sliver removal (morphological opening)
    copper = copper.buffer(-min_neck_mm / 2, join_style=2).buffer(min_neck_mm / 2, join_style=2).intersection(area)
    polys = [copper] if copper.geom_type == "Polygon" else [g for g in getattr(copper, "geoms", []) if g.geom_type == "Polygon"]
    # A piece touching only SMD plane pads would be floating copper (DRC 'Connection Error' on the fill itself),
    # so connection is judged against vias and through-hole plane pads only.
    anchor_u = unary_union(strong) if strong else None
    kept, removed = [], 0
    for g in polys:
        if g.is_empty:
            continue
        if g.area < min_island_mm2 or anchor_u is None or not g.intersects(anchor_u):
            removed += 1
            continue
        kept.append(g.simplify(simplify_mm, preserve_topology=True) if simplify_mm else g)
    return {"polygons": kept, "removed_islands": removed, "area_mm2": round(sum(g.area for g in kept), 1)}


def polygon_to_easyeda_complex(poly) -> List[List[Any]]:
    """Shapely Polygon (mm) -> EasyEDA createComplexPolygon source: [[x,y,'L',x,y,...] outer, [hole], ...] in mil."""
    def ring(coords):
        pts = list(coords)
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        out = [round(pts[0][0] * MIL, 3), round(pts[0][1] * MIL, 3), "L"]
        for x, y in pts[1:]:
            out += [round(x * MIL, 3), round(y * MIL, 3)]
        out += [round(pts[0][0] * MIL, 3), round(pts[0][1] * MIL, 3)]
        return out
    from shapely.geometry.polygon import orient
    poly = orient(poly, sign=1.0)   # exterior CCW, holes CW (holes with the wrong winding were filled solid)
    return [ring(poly.exterior.coords)] + [ring(h.coords) for h in poly.interiors]


def explicit_link(start_mm: Tuple[float, float], targets_mm: Sequence[Tuple[float, float]], obstacles,
                  clearance_mm: float, width_mm: float, max_len_mm: float = 10.0,
                  skip_within_mm: float = 0.05) -> Optional[Tuple[float, float]]:
    """Nearest target reachable by one straight track of `width_mm` that keeps `clearance_mm` from `obstacles`
    (a shapely geometry of other-net copper on the track's layer), or None.

    Why: EasyEDA Pro 3.2's DRC connectivity does not reliably join a via to a static `pcb_PrimitiveFill`
    (Plotus run 2026-11-12: two vias sitting fully inside both GND fills, with copper confirmed in the
    Gerbers, still gave 'Connection Error'. The result also depended on creation order). A pad whose only
    path to the plane is a stitch via therefore also gets an explicit track to an existing plane-net via."""
    _, Point, LineString, *_ = _sh()
    sp = Point(start_mm)
    best = None
    for t in sorted(targets_mm, key=lambda q: sp.distance(Point(q))):
        d = sp.distance(Point(t))
        if d <= skip_within_mm or d > max_len_mm:
            continue
        seg = LineString([start_mm, t]).buffer(width_mm / 2)
        if obstacles is None or obstacles.is_empty or seg.distance(obstacles) >= clearance_mm:
            best = (float(t[0]), float(t[1]))
            break
    return best
