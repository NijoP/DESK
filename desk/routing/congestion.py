"""Subsystem Four: Congestion-Aware Layer-Specific Global Routing Planner.
Models layer capacity, corridor reservations, and routing density across a 2D spatial grid.
Supports incremental congestion updates after routing passes.
Zero external dependencies.
"""
from __future__ import annotations
import math
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from desk.routing.board import BoardIntelligenceEngine


@dataclass
class CongestionCell:
    """Represents a spatial region on a specific routing layer."""
    cx: int
    cy: int
    layer: int
    x_min_mil: float
    x_max_mil: float
    y_min_mil: float
    y_max_mil: float
    capacity_mil: float
    occupied_mil: float = 0.0
    reserved_mil: float = 0.0
    obstacle_count: int = 0
    nets_passing: Set[str] = field(default_factory=set)

    @property
    def utilization_pct(self) -> float:
        tot = self.capacity_mil
        if tot <= 0: return 100.0
        used = self.occupied_mil + self.reserved_mil
        return round(min(100.0, (used / tot) * 100.0), 1)

    @property
    def congestion_cost(self) -> float:
        """Non-linear penalty for routing through congested cells."""
        u = self.utilization_pct / 100.0
        if u >= 0.95:
            return 100.0
        elif u >= 0.80:
            return 10.0 + 40.0 * (u - 0.80)
        elif u >= 0.50:
            return 1.0 + 5.0 * (u - 0.50)
        return 1.0


class CongestionMap:
    """Layer-aware spatial congestion grid for the entire PCB."""

    def __init__(
        self,
        board: BoardIntelligenceEngine,
        grid_cell_size_mil: float = 100.0
    ):
        self.board = board
        self.cell_size = grid_cell_size_mil
        self.nx = max(1, int(math.ceil(board.width_mil / grid_cell_size_mil)))
        self.ny = max(1, int(math.ceil(board.height_mil / grid_cell_size_mil)))
        self.layers = list(range(1, len(board.stackup) + 1))
        self.cells: Dict[Tuple[int, int, int], CongestionCell] = {}
        self._initialize_grid()

    def _initialize_grid(self) -> None:
        """Initializes cells and indexes initial pad/keepout obstacles."""
        for lay in self.layers:
            for cx in range(self.nx):
                for cy in range(self.ny):
                    x1 = cx * self.cell_size
                    x2 = min(self.board.width_mil, (cx + 1) * self.cell_size)
                    y1 = cy * self.cell_size
                    y2 = min(self.board.height_mil, (cy + 1) * self.cell_size)
                    # Baseline cell routing capacity: width * 10 tracks max per 100 mil cell
                    cap = (x2 - x1) * 8.0

                    cell = CongestionCell(
                        cx=cx, cy=cy, layer=lay,
                        x_min_mil=x1, x_max_mil=x2,
                        y_min_mil=y1, y_max_mil=y2,
                        capacity_mil=cap
                    )
                    self.cells[(cx, cy, lay)] = cell

        # Account for static obstacles from board pads and keepouts
        for pad in self.board.pads.values():
            cxs = int(pad.x_mil / self.cell_size)
            cys = int(pad.y_mil / self.cell_size)
            target_layers = self.layers if pad.is_through_hole else [pad.layer]
            for lay in target_layers:
                key = (cxs, cys, lay)
                if key in self.cells:
                    self.cells[key].obstacle_count += 1
                    # Obstacle occupies capacity
                    self.cells[key].occupied_mil += max(pad.width_mil, pad.height_mil)

    def reserve_corridor(
        self,
        net_name: str,
        path_segments: List[Tuple[float, float, float, float]],
        layer: int,
        width_mil: float = 10.0
    ) -> None:
        """Softly reserves corridor capacity for high-priority or differential-pair nets."""
        for x1, y1, x2, y2 in path_segments:
            cx1 = int(min(x1, x2) / self.cell_size)
            cx2 = int(max(x1, x2) / self.cell_size)
            cy1 = int(min(y1, y2) / self.cell_size)
            cy2 = int(max(y1, y2) / self.cell_size)
            for cx in range(cx1, cx2 + 1):
                for cy in range(cy1, cy2 + 1):
                    key = (cx, cy, layer)
                    if key in self.cells:
                        self.cells[key].reserved_mil += width_mil
                        self.cells[key].nets_passing.add(net_name)

    def add_routed_track(
        self,
        net_name: str,
        x1: float, y1: float,
        x2: float, y2: float,
        width_mil: float,
        layer: int
    ) -> None:
        """Incrementally updates occupied capacity after a track is routed."""
        cx1 = int(min(x1, x2) / self.cell_size)
        cx2 = int(max(x1, x2) / self.cell_size)
        cy1 = int(min(y1, y2) / self.cell_size)
        cy2 = int(max(y1, y2) / self.cell_size)
        for cx in range(cx1, cx2 + 1):
            for cy in range(cy1, cy2 + 1):
                key = (cx, cy, layer)
                if key in self.cells:
                    self.cells[key].occupied_mil += width_mil
                    self.cells[key].nets_passing.add(net_name)

    def get_highest_congestion_hotspots(self, top_n: int = 5) -> List[CongestionCell]:
        """Returns cells with highest utilization / congestion risk."""
        sorted_cells = sorted(self.cells.values(), key=lambda c: c.utilization_pct, reverse=True)
        return sorted_cells[:top_n]
