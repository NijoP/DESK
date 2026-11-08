"""Language-Independent Data Contracts: Computational Geometry & Spatial Indexing.
Version: 1.0.0
Authoritative Schema for Python, Rust (FFI/PyO3), and TypeScript interchange.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass(frozen=True)
class Rect2D:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    def contains_point(self, pt: Point2D) -> bool:
        return self.min_x <= pt.x <= self.max_x and self.min_y <= pt.y <= self.max_y


@dataclass
class Polygon2D:
    vertices: List[Point2D]
    layer_id: int
    net_name: Optional[str] = None
    is_closed: bool = True

    def to_points_list(self) -> List[Tuple[float, float]]:
        return [p.to_tuple() for p in self.vertices]


@dataclass
class KeepoutContract:
    name: str
    rect: Rect2D
    layer_id: Optional[int] = None
    clearance_mm: float = 0.0


@dataclass
class CollisionResult:
    has_collision: bool
    violation_type: str  # "NONE", "VERTEX_PENETRATION", "EDGE_INTERSECTION", "ENGULFED_KEEPOUT"
    details: str = ""
    penetrating_point: Optional[Point2D] = None
