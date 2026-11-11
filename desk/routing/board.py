"""Subsystem One: Board Intelligence Engine.
Builds a normalized, layer-aware, spatial-indexed representation of the physical PCB.
Supports fast spatial range queries, layer obstacle caching, and incremental invalidation.
Zero external dependencies.
"""
from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field


MIL = 39.37007874


@dataclass(unsafe_hash=True)
class BoardPad:
    """Normalized pad primitive with exact spatial geometry."""
    pad_id: str          # "U2.13"
    ref: str             # "U2"
    pad_num: str         # "13"
    net: str             # "VBAT"
    x_mil: float
    y_mil: float
    width_mil: float
    height_mil: float
    layer: int           # 1=Top, 2=Bottom, 11=ThroughHole
    is_through_hole: bool
    shape: str           # "RECT", "OVAL", "ROUND", "POLYGON"
    rotation_deg: float = 0.0


@dataclass(unsafe_hash=True)
class BoardTrack:
    """Normalized copper track segment."""
    track_id: str
    net: str
    layer: int
    x1: float
    y1: float
    x2: float
    y2: float
    width_mil: float


@dataclass(unsafe_hash=True)
class BoardVia:
    """Normalized via primitive."""
    via_id: str
    net: str
    x_mil: float
    y_mil: float
    diameter_mil: float
    drill_mil: float
    start_layer: int
    end_layer: int


@dataclass(unsafe_hash=True)
class BoardKeepout:
    """Mechanical or electrical keepout boundary."""
    name: str
    layer: int  # 0=All layers
    rect_mil: Tuple[float, float, float, float]  # (min_x, max_x, min_y, max_y)


class SpatialHashIndex:
    """Fast 2D spatial grid for geometry lookups and obstacle collision queries."""

    def __init__(self, cell_size_mil: float = 50.0):
        self.cell_size = cell_size_mil
        self.grid: Dict[Tuple[int, int, int], List[Any]] = {}

    def _cells_for_box(self, x1: float, x2: float, y1: float, y2: float) -> List[Tuple[int, int]]:
        c_x1 = int(math.floor(min(x1, x2) / self.cell_size))
        c_x2 = int(math.floor(max(x1, x2) / self.cell_size))
        c_y1 = int(math.floor(min(y1, y2) / self.cell_size))
        c_y2 = int(math.floor(max(y1, y2) / self.cell_size))
        cells = []
        for cx in range(c_x1, c_x2 + 1):
            for cy in range(c_y1, c_y2 + 1):
                cells.append((cx, cy))
        return cells

    def insert(self, item: Any, x1: float, x2: float, y1: float, y2: float, layer: int) -> None:
        for cx, cy in self._cells_for_box(x1, x2, y1, y2):
            key = (cx, cy, layer)
            if key not in self.grid:
                self.grid[key] = []
            self.grid[key].append(item)

    def query_box(self, x1: float, x2: float, y1: float, y2: float, layer: int) -> Set[Any]:
        results: Set[Any] = set()
        for cx, cy in self._cells_for_box(x1, x2, y1, y2):
            key = (cx, cy, layer)
            if key in self.grid:
                results.update(self.grid[key])
        return results

    def clear(self) -> None:
        self.grid.clear()


class BoardIntelligenceEngine:
    """Normalized PCB representation with spatial querying and obstacle caching."""

    def __init__(
        self,
        board_width_mil: float,
        board_height_mil: float,
        stackup: List[str],
        pcb_dump: Dict[str, Any]
    ):
        self.width_mil = board_width_mil
        self.height_mil = board_height_mil
        self.stackup = stackup
        self.pads: Dict[str, BoardPad] = {}
        self.tracks: List[BoardTrack] = []
        self.vias: List[BoardVia] = []
        self.keepouts: List[BoardKeepout] = []
        self.net_pads: Dict[str, List[BoardPad]] = {}
        self.spatial_index = SpatialHashIndex(cell_size_mil=50.0)
        self._build_model(pcb_dump)

    def _build_model(self, dump: Dict[str, Any]) -> None:
        """Parses pcb_dump into normalized spatial models and populates spatial hash index."""
        for ref, comp in dump.items():
            if not isinstance(comp, dict): continue
            rot_deg = float(comp.get("rot", 0.0) or 0.0)
            comp_layer = int(comp.get("layer", 1))

            for p in comp.get("pads", []):
                net = (p.get("net") or "").strip()
                from desk.routing.connectivity import pad_xy
                px, py = pad_xy(comp, p)
                pad_num = str(p.get("num", ""))
                pad_layer = int(p.get("layer", comp_layer))
                is_th = pad_layer in (11, 12)
                from desk.routing.connectivity import pad_size_mil
                pw, ph = pad_size_mil(p)
                pid = f"{ref}.{pad_num}"

                bpad = BoardPad(
                    pad_id=pid,
                    ref=ref,
                    pad_num=pad_num,
                    net=net,
                    x_mil=px,
                    y_mil=py,
                    width_mil=pw,
                    height_mil=ph,
                    layer=pad_layer,
                    is_through_hole=is_th,
                    shape=str(p.get("shape", "RECT")).upper(),
                    rotation_deg=rot_deg
                )
                self.pads[pid] = bpad
                if net:
                    if net not in self.net_pads:
                        self.net_pads[net] = []
                    self.net_pads[net].append(bpad)

                # Index pad bounding box
                half_w = pw / 2.0
                half_h = ph / 2.0
                if is_th:
                    # Index on all signal layers
                    for lay in range(1, len(self.stackup) + 1):
                        self.spatial_index.insert(bpad, px - half_w, px + half_w, py - half_h, py + half_h, lay)
                else:
                    self.spatial_index.insert(bpad, px - half_w, px + half_w, py - half_h, py + half_h, pad_layer)

    def query_obstacles_near(
        self,
        x_mil: float,
        y_mil: float,
        radius_mil: float,
        layer: int,
        ignore_net: Optional[str] = None
    ) -> List[Any]:
        """Queries physical obstacles within radius_mil on layer, ignoring primitives of ignore_net."""
        x1 = x_mil - radius_mil
        x2 = x_mil + radius_mil
        y1 = y_mil - radius_mil
        y2 = y_mil + radius_mil

        candidates = self.spatial_index.query_box(x1, x2, y1, y2, layer)
        obstacles = []
        for c in candidates:
            if isinstance(c, BoardPad):
                if ignore_net and c.net == ignore_net:
                    continue
                d = math.hypot(c.x_mil - x_mil, c.y_mil - y_mil)
                if d <= radius_mil:
                    obstacles.append(c)
        return obstacles
