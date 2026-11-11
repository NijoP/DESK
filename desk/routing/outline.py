"""Board outline helpers (rework item E; KF-20261111-007).

Verified on EasyEDA Pro 3.2.149 (INC-20261111-008):
* `pcb_PrimitivePolyline.create` with a long explicit vertex list froze the editor twice;
* the "R" polygon with corner radii creates but exports a skewed DSN boundary;
* only a plain `["R", x, y, w, h, 0, 0]` rectangle on the outline layer exports a correct boundary.

So the outline step creates ONE polyline from a plain "R" polygon; rounded corners are expressed as
corner routing keep-outs (`route_keepouts`) until an arc polygon format is verified by readback.

Zero external dependencies.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

MIL = 39.37007874
OUTLINE_LAYER = 11
MAX_SAFE_VERTICES = 8   # anything longer goes through the bridge as a polygon spec, never a vertex list


def rect_outline_polygon(width_mm: float, height_mm: float, origin_mm: Tuple[float, float] = (0.0, 0.0)) -> List[Any]:
    """EasyEDA polygon spec for a plain rectangular outline: ["R", x, y, w, h, 0, 0] in mil."""
    ox, oy = origin_mm
    return ["R", round(ox * MIL, 4), round(oy * MIL, 4), round(width_mm * MIL, 4), round(height_mm * MIL, 4), 0, 0]


def corner_keepouts(width_mm: float, height_mm: float, radius_mm: float) -> List[Dict[str, Any]]:
    """Routing keep-outs that stand in for rounded corners (square of side `radius_mm` in each corner)."""
    r = float(radius_mm)
    W, H = float(width_mm), float(height_mm)
    return [
        {"name": "corner_BL", "rect_mm": [0.0, 0.0, r, r], "side": "both", "allow": []},
        {"name": "corner_BR", "rect_mm": [W - r, 0.0, W, r], "side": "both", "allow": []},
        {"name": "corner_TL", "rect_mm": [0.0, H - r, r, H], "side": "both", "allow": []},
        {"name": "corner_TR", "rect_mm": [W - r, H - r, W, H], "side": "both", "allow": []},
    ]


def outline_create_js(width_mm: float, height_mm: float, origin_mm: Tuple[float, float] = (0.0, 0.0)) -> str:
    """JavaScript for the bridge that creates the single outline polyline from the "R" polygon.
    It never sends a vertex list."""
    poly = rect_outline_polygon(width_mm, height_mm, origin_mm)
    import json
    return (f"const __poly = await eda.pcb_MathPolygon.createPolygon({json.dumps(poly)});\n"
            f"const __line = await eda.pcb_PrimitivePolyline.create({OUTLINE_LAYER}, __poly, 0.0, 0.0);\n"
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
    if isinstance(polyg, list) and polyg and polyg[0] == "R" and len(polyg) >= 7 and (polyg[5] or polyg[6]):
        errs.append("outline uses an 'R' polygon with corner radii; it exports a skewed boundary (use radius 0 and corner keep-outs)")
    if isinstance(polyg, list) and polyg and polyg[0] != "R" and len(polyg) > 2 * MAX_SAFE_VERTICES + 1:
        errs.append(f"outline vertex list is long ({len(polyg)} values); long lists froze the editor (INC-20261111-008)")
    if p.get("closed") is False:
        errs.append("outline primitive is not closed")
    return errs
