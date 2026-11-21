"""Pad copper geometry for connectivity, feasibility and clearance checks (pure functions, mil, board frame).

A pad is a *core* (a point, a segment or a convex polygon) grown by a radius:
- circle  (ELLIPSE/CIRCLE/ROUND with w == h): point core, radius w/2
- stadium (OVAL, or ELLIPSE with w != h):      segment along the long axis, radius = short side / 2
- rect    (RECT and every other shape):        4-corner polygon, radius 0

Frames (same conventions as desk/copper_fill.py, verified on the Plotus readback):
- the centre is `connectivity.pad_xy` (dump offsets are board-frame, QA-03);
- `shape: [TYPE, w, h, ...]` is the pad's own (unrotated) size and the pad `rot` is its board-frame rotation, so a
  RECT 80x20 pad with rot 90 covers 20 mil in x and 80 mil in y; a pad without `rot` takes its component's rotation;
- POLYGON pads are read back in absolute, already-rotated board coordinates: when their bounding box is centred on
  the pad they are used as that axis-aligned box without a further rotation.

Distances are exact for the core/radius model; a polygon pad is approximated by its bounding box.
Zero external dependencies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


@dataclass(frozen=True)
class PadShape:
    cx: float
    cy: float
    w: float                 # pad-local size (before rotation)
    h: float
    rot_deg: float           # board-frame rotation applied to (w, h)
    kind: str                # "circle" | "stadium" | "rect"
    core: Tuple[Point, ...]  # 1 point, 2 points (segment) or >= 3 points (convex polygon, closed implicitly)
    radius: float

    @property
    def bounding_radius(self) -> float:
        """Radius of the smallest centre-based circle that contains the copper."""
        return max(math.hypot(px - self.cx, py - self.cy) for px, py in self.core) + self.radius

    def extent(self) -> Tuple[float, float]:
        """Board-frame axis-aligned width and height of the copper."""
        xs = [p[0] for p in self.core]
        ys = [p[1] for p in self.core]
        return max(xs) - min(xs) + 2 * self.radius, max(ys) - min(ys) + 2 * self.radius


def _rotate(x: float, y: float, rot_deg: float) -> Point:
    if not rot_deg:
        return x, y
    a = math.radians(rot_deg)
    # snap exact quarter turns so 90-degree pads stay exactly axis-aligned
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    return x * c - y * s, x * s + y * c


def make_shape(cx: float, cy: float, w: float, h: float, rot_deg: float = 0.0, kind: str = "RECT") -> PadShape:
    """PadShape for a pad of local size w x h, rotated by rot_deg about its centre (cx, cy)."""
    k = str(kind or "RECT").upper()
    w, h = max(0.0, float(w)), max(0.0, float(h))
    if k in ("ELLIPSE", "CIRCLE", "ROUND") and abs(w - h) < 1e-6:
        return PadShape(cx, cy, w, h, rot_deg, "circle", ((cx, cy),), w / 2.0)
    if k in ("OVAL", "ELLIPSE", "OBLONG"):
        r = min(w, h) / 2.0
        half = (max(w, h) - min(w, h)) / 2.0
        ax, ay = (half, 0.0) if w >= h else (0.0, half)
        dx, dy = _rotate(ax, ay, rot_deg)
        return PadShape(cx, cy, w, h, rot_deg, "stadium", ((cx - dx, cy - dy), (cx + dx, cy + dy)), r)
    corners = tuple((cx + px, cy + py) for px, py in
                    (_rotate(sx * w / 2.0, sy * h / 2.0, rot_deg) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))))
    return PadShape(cx, cy, w, h, rot_deg, "rect", corners, 0.0)


def _numbers(o: Any, out: List[float]) -> None:
    if isinstance(o, (list, tuple)):
        for v in o:
            _numbers(v, out)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        out.append(float(o))


def pad_shape(comp: Dict[str, Any], pad: Dict[str, Any], rot_override: Optional[float] = None) -> PadShape:
    """PadShape of a PCB-dump pad record (see module docstring for the frames)."""
    from desk.routing.connectivity import pad_xy
    cx, cy = pad_xy(comp, pad, rot_override=rot_override)
    comp_rot = float(comp.get("rot", 0.0) or 0.0)
    rot = pad.get("rot")
    rot = comp_rot if rot is None else float(rot or 0.0)
    if rot_override is not None:
        rot += float(rot_override) - comp_rot
    shape = pad.get("shape")
    kind = str(shape[0]).upper() if isinstance(shape, (list, tuple)) and shape else "RECT"
    if "w" in pad or "width" in pad:
        w = float(pad.get("w", pad.get("width", 15.0)))
        h = float(pad.get("h", pad.get("height", 15.0)))
        return make_shape(cx, cy, w, h, rot, kind)
    if isinstance(shape, (list, tuple)) and len(shape) >= 3 and all(isinstance(v, (int, float)) for v in shape[1:3]):
        w, h = float(shape[1]), float(shape[2])
        if w > 0 and h > 0:
            return make_shape(cx, cy, w, h, rot, kind)
    if isinstance(shape, (list, tuple)) and len(shape) >= 2:
        nums: List[float] = []
        _numbers(shape[1:], nums)
        xs, ys = nums[0::2], nums[1::2]
        if len(xs) >= 3 and len(xs) == len(ys):
            bw, bh = max(xs) - min(xs), max(ys) - min(ys)
            bx, by = (max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0
            if bw > 0 and bh > 0:
                if abs(bx - cx) < 2.0 and abs(by - cy) < 2.0:      # absolute, already rotated (copper_fill.py)
                    return make_shape(cx, cy, bw, bh, 0.0, "RECT")
                return make_shape(cx, cy, bw, bh, rot, "RECT")
    return make_shape(cx, cy, 15.0, 15.0, rot, kind)


# --- primitive distances -------------------------------------------------------------------------------------------

def point_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    if L < 1e-18:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _orient(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    d1 = _orient(*b1, *b2, *a1)
    d2 = _orient(*b1, *b2, *a2)
    d3 = _orient(*a1, *a2, *b1)
    d4 = _orient(*a1, *a2, *b2)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    eps = 1e-9
    return ((abs(d1) < eps and point_segment_distance(*a1, *b1, *b2) < eps) or
            (abs(d2) < eps and point_segment_distance(*a2, *b1, *b2) < eps) or
            (abs(d3) < eps and point_segment_distance(*b1, *a1, *a2) < eps) or
            (abs(d4) < eps and point_segment_distance(*b2, *a1, *a2) < eps))


def segment_segment_distance(a1: Point, a2: Point, b1: Point, b2: Point) -> float:
    """Minimum distance between two segments (0 when they cross)."""
    if segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(point_segment_distance(*a1, *b1, *b2), point_segment_distance(*a2, *b1, *b2),
               point_segment_distance(*b1, *a1, *a2), point_segment_distance(*b2, *a1, *a2))


def point_in_polygon(x: float, y: float, pts: Sequence[Point]) -> bool:
    inside = False
    n = len(pts)
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[(i + 1) % n]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < xint:
                inside = not inside
    return inside


def _edges(core: Sequence[Point]) -> List[Tuple[Point, Point]]:
    if len(core) == 1:
        return [(core[0], core[0])]
    if len(core) == 2:
        return [(core[0], core[1])]
    return [(core[i], core[(i + 1) % len(core)]) for i in range(len(core))]


def core_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    """Distance between two cores (points, segments or convex polygons); 0 when they overlap."""
    if len(a) >= 3 and any(point_in_polygon(x, y, a) for x, y in b):
        return 0.0
    if len(b) >= 3 and any(point_in_polygon(x, y, b) for x, y in a):
        return 0.0
    return min(segment_segment_distance(p1, p2, q1, q2) for p1, p2 in _edges(a) for q1, q2 in _edges(b))


# --- pad queries ---------------------------------------------------------------------------------------------------

def segment_to_pad_distance(x1: float, y1: float, x2: float, y2: float, pad: PadShape) -> float:
    """Distance from a track centreline segment to the pad copper (0 when the centreline enters the pad)."""
    return max(0.0, core_distance(((x1, y1), (x2, y2)), pad.core) - pad.radius)


def point_to_pad_distance(x: float, y: float, pad: PadShape) -> float:
    return max(0.0, core_distance(((x, y),), pad.core) - pad.radius)


def pad_gap(a: PadShape, b: PadShape) -> float:
    """Copper-to-copper gap between two pads (0 when they touch or overlap)."""
    return max(0.0, core_distance(a.core, b.core) - a.radius - b.radius)
