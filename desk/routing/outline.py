"""Board outline helpers (rework item E; KF-20261111-007).

Verified on EasyEDA Pro 3.2.149 (INC-20261111-008):
* `pcb_PrimitivePolyline.create` with a long explicit vertex list froze the editor twice;
* only ONE polyline built from an "R" polygon spec is created (never a vertex list).

Corrected by readback in the Plotus ESP32-S3 live tests (run 1 F-008/F-009, run 2b R2-F-007, 2026-11-12):
* the "R" spec is ["R", x, y_TOP, w, h, rotation_deg, corner_radius]: (x, y) is the TOP-LEFT corner and the
  rectangle extends toward -Y. An origin used as bottom-left drew the outline below the parts (0..-44 mm).
* field 6 is the ROTATION, field 7 the corner radius. The earlier "skewed boundary with radii" came from writing the
  radius into the rotation field (a 2 mm radius = 78.74 mil rotated the board 78.7 deg). With rotation 0 and the
  radius in field 7 the rounded outline is correct (run 2b readback + render).
* the live signature is create(net, layer, polygon, lineWidth, primitiveLock); create(layer, polygon, 0, 0)
  fails with "cannot create polygon primitive".

Corner keep-outs (`corner_keepouts`) are still useful as routing / copper keep-outs inside a rounded corner.

Zero external dependencies.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

MIL = 39.37007874
OUTLINE_LAYER = 11
MAX_SAFE_VERTICES = 8   # anything longer goes through the bridge as a polygon spec, never a vertex list


def rect_outline_polygon(width_mm: float, height_mm: float, origin_mm: Tuple[float, float] = (0.0, 0.0),
                         radius_mm: float = 0.0) -> List[Any]:
    """EasyEDA "R" polygon spec (mil) for a rectangular outline whose BOTTOM-LEFT corner is `origin_mm`:
    ["R", x, y_top, w, h, rotation=0, corner_radius]."""
    ox, oy = origin_mm
    if radius_mm < 0 or 2 * radius_mm > min(width_mm, height_mm):
        raise ValueError(f"corner radius {radius_mm} mm does not fit a {width_mm} x {height_mm} mm board")
    return ["R", round(ox * MIL, 4), round((oy + height_mm) * MIL, 4), round(width_mm * MIL, 4), round(height_mm * MIL, 4),
            0, round(radius_mm * MIL, 4)]


def corner_keepouts(width_mm: float, height_mm: float, radius_mm: float) -> List[Dict[str, Any]]:
    """Routing keep-outs for the corners (square of side `radius_mm` in each corner)."""
    r = float(radius_mm)
    W, H = float(width_mm), float(height_mm)
    return [
        {"name": "corner_BL", "rect_mm": [0.0, 0.0, r, r], "side": "both", "allow": []},
        {"name": "corner_BR", "rect_mm": [W - r, 0.0, W, r], "side": "both", "allow": []},
        {"name": "corner_TL", "rect_mm": [0.0, H - r, r, H], "side": "both", "allow": []},
        {"name": "corner_TR", "rect_mm": [W - r, H - r, W, H], "side": "both", "allow": []},
    ]


def outline_create_js(width_mm: float, height_mm: float, origin_mm: Tuple[float, float] = (0.0, 0.0),
                      radius_mm: float = 0.0, line_width_mil: float = 10.0) -> str:
    """JavaScript for the bridge that creates the single outline polyline from the "R" polygon
    (live signature create(net, layer, polygon, lineWidth, primitiveLock)). It never sends a vertex list."""
    poly = rect_outline_polygon(width_mm, height_mm, origin_mm, radius_mm)
    import json
    return (f"const __poly = await eda.pcb_MathPolygon.createPolygon({json.dumps(poly)});\n"
            f"const __line = await eda.pcb_PrimitivePolyline.create('', {OUTLINE_LAYER}, __poly, {float(line_width_mil)}, false);\n"
            f"return __line ? (__line.getState_PrimitiveId ? __line.getState_PrimitiveId() : true) : false;")


def validate_outline_primitives(prims: List[Dict[str, Any]]) -> List[str]:
    """Errors for a list of outline-layer primitives read from the board ({"id","layer","closed"} or
    {"polygon": [...]})."""
    errs: List[str] = []
    on_layer = [p for p in prims if int(p.get("layer", OUTLINE_LAYER)) == OUTLINE_LAYER]
    if len(on_layer) != 1:
        errs.append(f"{len(on_layer)} outline primitives on layer {OUTLINE_LAYER}; exactly one closed polyline is required")
        return errs
    p = on_layer[0]
    polyg = p.get("polygon")
    if isinstance(polyg, list) and polyg and polyg[0] == "R" and len(polyg) >= 7:
        if polyg[5]:
            errs.append(f"outline 'R' polygon is rotated by {polyg[5]} deg (field 6 is rotation; a corner radius belongs in field 7)")
        if len(polyg) >= 7 and polyg[6] and 2 * float(polyg[6]) > min(float(polyg[3]), float(polyg[4])):
            errs.append("outline corner radius does not fit the rectangle")
    if isinstance(polyg, list) and polyg and polyg[0] != "R" and len(polyg) > 2 * MAX_SAFE_VERTICES + 1:
        errs.append(f"outline vertex list is long ({len(polyg)} values); long lists froze the editor (INC-20261111-008)")
    if p.get("closed") is False:
        errs.append("outline primitive is not closed")
    return errs
