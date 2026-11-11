"""Dense PCB Intelligence Engine.

Understands a placed board as a physical routing ecosystem before any router runs:
where routing demand will exceed supply, why, and what engineering action resolves
it. Everything here is deterministic geometry on the PCB dump; nothing calls a model
or EasyEDA.

Model
-----
The board is divided into square cells (default 50 mil, adaptive to board size).
For every cell and routable signal layer:

* supply  = cell width x (1 - fraction of the cell blocked by pads / keep-outs)
            [mil of track-plus-clearance that can cross the cell on that layer]
* demand  = sum over ratsnest (MST) edges whose Manhattan L-route crosses the cell
            of (track width + clearance) for that net, each of the two L-routes
            weighted 0.5

congestion score = demand / sum(supply over routable layers)
  < 0.5 comfortable, 0.5-0.8 busy, >= 0.8 hotspot, >= 1.0 overloaded (cannot route
  without detours, vias or placement change).

Hotspot regions are 8-connected clusters of hotspot cells. Each region carries the
measured causes (fine-pitch escape, crossing hotspot, power trunk through a signal
corridor, layer scarcity, pad blocking) and the recommended strategy, so the
routing plan and the placement refiner can act on it. Corridors are contiguous
low-demand channels that should be reserved for constrained nets.

Incremental: `update_components()` recomputes only the nets and cells touched by
moved parts, which is what the placement-routing co-optimisation loop needs.

Zero external dependencies.
"""
from __future__ import annotations
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

from desk.routing.board import BoardIntelligenceEngine, BoardPad
from desk.routing.escape import PadEscapeEngine, PadEscapeAnalysis
from desk.routability import RoutabilityEvaluator, _compute_fast_mst, _segments_intersect
from desk.models import NetEndpoint

MIL = 39.37007874
POWER_RX = re.compile(r"^(GND|VSS|AGND|DGND|PGND|VCC|VDD|3V3|5V|1V8|VBAT|VBUS|VSYS|VIN|12V|PWR)", re.I)
GND_RX = re.compile(r"^(GND|VSS|AGND|DGND|PGND)$", re.I)
ESCAPE_WEIGHT = {"NO_LEGAL_ESCAPE_FOUND": 10.0, "CRITICAL_ESCAPE": 8.5, "RESTRICTED_ESCAPE": 6.0,
                 "MODERATE_ESCAPE": 3.0, "EASY_ESCAPE": 1.0}
FINE_PITCH_MIL = 25.6  # 0.65 mm pitch and below


@dataclass
class CellMetrics:
    cx: int
    cy: int
    x0: float
    y0: float
    x1: float
    y1: float
    pad_count: int = 0
    fine_pitch_pads: int = 0
    blocked: Dict[int, float] = field(default_factory=dict)   # layer -> blocked fraction 0..1
    demand_mil: float = 0.0
    supply_mil: float = 0.0
    score: float = 0.0
    nets: Set[str] = field(default_factory=set)
    crossings: int = 0
    power_demand_mil: float = 0.0


@dataclass
class HotspotRegion:
    region_id: str
    cells: List[Tuple[int, int]]
    bbox_mm: Tuple[float, float, float, float]
    max_score: float
    mean_score: float
    pad_count: int
    fine_pitch_pads: int
    net_count: int
    nets: List[str]
    crossings: int
    free_layers: List[int]
    preferred_escape_directions: List[str]
    power_nets_passing: List[str]
    causes: List[str]
    recommended_strategy: str
    recommended_actions: List[str]
    components: List[str]


@dataclass
class Corridor:
    corridor_id: str
    orientation: str  # "H" or "V"
    bbox_mm: Tuple[float, float, float, float]
    length_mm: float
    width_mm: float
    mean_score: float
    adjacent_regions: List[str]


@dataclass
class DenseBoardReport:
    board_mm: Tuple[float, float]
    grid_mil: float
    nx: int
    ny: int
    layers: List[str]
    routable_layers: List[int]
    total_components: int
    total_pads: int
    total_nets: int
    ratsnest_crossings: int
    mst_wirelength_mm: float
    overall_congestion: float        # mean score of the busiest 10 % of cells
    overloaded_cells: int            # score >= 1.0
    hotspot_cells: int               # score >= hot threshold
    hotspots: List[HotspotRegion]
    corridors: List[Corridor]
    escape_summary: Dict[str, int]
    priority_net_order: List[str]
    plane_nets: List[str]
    power_conflicts: List[str]
    recommendations: List[str]
    analysis_ms: float
    cells: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self, include_cells: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if not include_cells:
            d.pop("cells", None)
        return d

    def to_mission_control(self) -> Dict[str, Any]:
        """Compact payload for the dashboard: metrics plus hotspot/corridor rectangles."""
        return {
            "overall_congestion": self.overall_congestion,
            "overloaded_cells": self.overloaded_cells,
            "hotspot_cells": self.hotspot_cells,
            "ratsnest_crossings": self.ratsnest_crossings,
            "hotspots": [{"id": h.region_id, "bbox_mm": h.bbox_mm, "score": h.max_score, "causes": h.causes,
                          "strategy": h.recommended_strategy, "nets": h.nets[:6]} for h in self.hotspots],
            "corridors": [{"id": c.corridor_id, "bbox_mm": c.bbox_mm, "orientation": c.orientation} for c in self.corridors],
            "escape_summary": self.escape_summary,
            "priority_nets": self.priority_net_order[:20],
        }


class DensePCBIntelligence:
    HOT_THRESHOLD = 0.8
    CORRIDOR_THRESHOLD = 0.3

    def __init__(self,
                 dump: Dict[str, Any],
                 board_mm: Tuple[float, float],
                 origin_mm: Tuple[float, float] = (0.0, 0.0),
                 stackup: Optional[List[str]] = None,
                 plane_layers: Optional[Dict[int, str]] = None,     # layer index -> net occupying it as a plane
                 keepouts_mm: Optional[List[Dict[str, Any]]] = None, # {"rect_mm":[x0,y0,x1,y1], "side":...}
                 net_widths_mil: Optional[Dict[str, float]] = None,
                 default_width_mil: float = 5.0,
                 default_clearance_mil: float = 4.02,
                 grid_mil: Optional[float] = None,
                 profile: Optional[Any] = None):
        self.dump = {r: c for r, c in dump.items() if isinstance(c, dict)}
        self.board_mm = (float(board_mm[0]), float(board_mm[1]))
        self.origin_mil = (origin_mm[0] * MIL, origin_mm[1] * MIL)
        self.w_mil = self.board_mm[0] * MIL
        self.h_mil = self.board_mm[1] * MIL
        self.stackup = list(stackup or ["Top", "Bottom"])
        self.n_layers = len(self.stackup)
        self.plane_layers = dict(plane_layers or {})
        self.routable_layers = [l for l in range(1, self.n_layers + 1) if l not in self.plane_layers]
        if not self.routable_layers:
            self.routable_layers = [1]
        self.keepouts_mm = list(keepouts_mm or [])
        self.net_widths = dict(net_widths_mil or {})
        self.default_width = default_width_mil
        self.default_clearance = default_clearance_mil
        self.profile = profile
        min_dim = min(self.w_mil, self.h_mil)
        self.grid = float(grid_mil) if grid_mil else max(25.0, min(50.0, min_dim / 30.0))
        self.nx = max(1, int(math.ceil(self.w_mil / self.grid)))
        self.ny = max(1, int(math.ceil(self.h_mil / self.grid)))

        self.board = BoardIntelligenceEngine(self.w_mil, self.h_mil, self.stackup, self.dump)
        self.graph = RoutabilityEvaluator.build_connectivity_graph(self.dump)
        self.cells: Dict[Tuple[int, int], CellMetrics] = {}
        self._net_contrib: Dict[str, List[Tuple[Tuple[int, int], float, bool]]] = defaultdict(list)
        self._escape: Dict[str, PadEscapeAnalysis] = {}
        self._pad_cells: Dict[str, Tuple[int, int]] = {}
        self.last_report: Optional[DenseBoardReport] = None
        self._build()

    # ------------------------------------------------------------------ geometry helpers
    def _cell_of(self, x_mil: float, y_mil: float) -> Tuple[int, int]:
        cx = int((x_mil - self.origin_mil[0]) // self.grid)
        cy = int((y_mil - self.origin_mil[1]) // self.grid)
        return (min(max(cx, 0), self.nx - 1), min(max(cy, 0), self.ny - 1))

    def _cell_rect_mm(self, cx: int, cy: int) -> Tuple[float, float, float, float]:
        g = self.grid / MIL
        return (round(cx * g, 2), round(cy * g, 2), round((cx + 1) * g, 2), round((cy + 1) * g, 2))

    def _net_track_mil(self, net: str) -> float:
        w = self.net_widths.get(net)
        if w is None and self.profile is not None and hasattr(self.profile, "derive_trace_width_mil"):
            try:
                w = float(self.profile.derive_trace_width_mil(net))
            except Exception:
                w = None
        if w is None:
            w = self.default_width if not POWER_RX.match(net) else max(self.default_width, 10.0)
        return float(w) + self.default_clearance

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        t0 = time.perf_counter()
        for cx in range(self.nx):
            for cy in range(self.ny):
                x0 = self.origin_mil[0] + cx * self.grid
                y0 = self.origin_mil[1] + cy * self.grid
                self.cells[(cx, cy)] = CellMetrics(cx, cy, x0, y0, x0 + self.grid, y0 + self.grid,
                                                   blocked={l: 0.0 for l in range(1, self.n_layers + 1)})
        self._apply_keepouts()
        for pad in self.board.pads.values():
            self._add_pad(pad)
        for net in self.graph.nets:
            self._add_net_demand(net)
        self._recompute_scores(self.cells.keys())
        self._build_ms = (time.perf_counter() - t0) * 1000.0

    def _apply_keepouts(self) -> None:
        for ko in self.keepouts_mm:
            r = ko.get("rect_mm")
            if not r or len(r) < 4:
                continue
            side = ko.get("side", "both")
            layers = [1] if side == "T" else ([self.n_layers] if side == "B" else list(range(1, self.n_layers + 1)))
            x0, y0, x1, y1 = [v * MIL + (self.origin_mil[0] if i % 2 == 0 else self.origin_mil[1]) for i, v in enumerate(r)]
            for key, cell in self.cells.items():
                ov = self._overlap_fraction(cell, x0, y0, x1, y1)
                if ov > 0:
                    for l in layers:
                        cell.blocked[l] = min(1.0, cell.blocked[l] + ov)

    @staticmethod
    def _overlap_fraction(cell: CellMetrics, x0: float, y0: float, x1: float, y1: float) -> float:
        ox = max(0.0, min(cell.x1, x1) - max(cell.x0, x0))
        oy = max(0.0, min(cell.y1, y1) - max(cell.y0, y0))
        area = (cell.x1 - cell.x0) * (cell.y1 - cell.y0)
        return (ox * oy) / area if area > 0 else 0.0

    def _pad_layers(self, pad: BoardPad) -> List[int]:
        if pad.is_through_hole:
            return list(range(1, self.n_layers + 1))
        # EasyEDA: layer 1 = top, 2 = bottom. Map bottom to the last stackup index.
        if pad.layer == 2 and self.n_layers > 2:
            return [self.n_layers]
        return [min(max(pad.layer, 1), self.n_layers)]

    def _add_pad(self, pad: BoardPad, sign: float = 1.0) -> None:
        key = self._cell_of(pad.x_mil, pad.y_mil)
        cell = self.cells[key]
        hw, hh = pad.width_mil / 2.0, pad.height_mil / 2.0
        # pads blur across neighbouring cells they overlap
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k2 = (key[0] + dx, key[1] + dy)
                c2 = self.cells.get(k2)
                if not c2:
                    continue
                ov = self._overlap_fraction(c2, pad.x_mil - hw - self.default_clearance, pad.y_mil - hh - self.default_clearance,
                                            pad.x_mil + hw + self.default_clearance, pad.y_mil + hh + self.default_clearance)
                if ov <= 0:
                    continue
                for l in self._pad_layers(pad):
                    c2.blocked[l] = min(1.0, max(0.0, c2.blocked[l] + sign * ov))
        cell.pad_count = max(0, cell.pad_count + int(sign))
        if sign > 0:
            self._pad_cells[pad.pad_id] = key
            if pad.net:
                cell.nets.add(pad.net)
        else:
            self._pad_cells.pop(pad.pad_id, None)

    def _escape_of(self, pad: BoardPad) -> PadEscapeAnalysis:
        a = self._escape.get(pad.pad_id)
        if a is None:
            a = PadEscapeEngine.evaluate_pad_escape(pad, self.board, fine_pitch_clearance_mil=self.default_clearance,
                                                    min_trace_width_mil=self.default_width)
            self._escape[pad.pad_id] = a
        return a

    def _l_route_cells(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> List[Tuple[Tuple[int, int], float]]:
        """Cells crossed by the two Manhattan L-routes between p1 and p2, weighted 0.5 each."""
        (x1, y1), (x2, y2) = p1, p2
        c1, c2 = self._cell_of(x1, y1), self._cell_of(x2, y2)
        out: Dict[Tuple[int, int], float] = defaultdict(float)
        xa, xb = sorted((c1[0], c2[0]))
        ya, yb = sorted((c1[1], c2[1]))
        # Route A: horizontal at y1 then vertical at x2
        for cx in range(xa, xb + 1):
            out[(cx, c1[1])] += 0.5
        for cy in range(ya, yb + 1):
            out[(c2[0], cy)] += 0.5
        # Route B: vertical at x1 then horizontal at y2
        for cy in range(ya, yb + 1):
            out[(c1[0], cy)] += 0.5
        for cx in range(xa, xb + 1):
            out[(cx, c2[1])] += 0.5
        # Corner cells counted twice within one route are fine (they carry a bend); cap at 1 per route.
        return [(k, min(v, 1.0)) for k, v in out.items()]

    def _add_net_demand(self, net: str, sign: float = 1.0) -> None:
        edges = self.graph.multi_terminal_trees.get(net) or []
        if not edges:
            return
        is_power = bool(POWER_RX.match(net))
        is_plane = net in self.plane_layers.values()
        if is_plane:
            return  # a plane net needs pad-to-plane vias, not corridors
        tw = self._net_track_mil(net)
        for e in edges:
            # The cells holding the two pads themselves are never corridor demand: the track starts and ends
            # inside copper that belongs to this net. Counting them made every pad-blocked cell look like a
            # "detour required" hotspot once real pad sizes were used (2026-11-12).
            end_cells = {self._cell_of(e[0].x_mil, e[0].y_mil), self._cell_of(e[1].x_mil, e[1].y_mil)}
            for key, w in self._l_route_cells((e[0].x_mil, e[0].y_mil), (e[1].x_mil, e[1].y_mil)):
                cell = self.cells.get(key)
                if not cell or key in end_cells:
                    continue
                amount = sign * w * tw
                cell.demand_mil += amount
                if is_power:
                    cell.power_demand_mil += amount
                if sign > 0:
                    cell.nets.add(net)
                    self._net_contrib[net].append((key, w * tw, is_power))
        if sign < 0:
            self._net_contrib.pop(net, None)

    BLOCKED_SCORE_CAP = 2.0  # a fully blocked cell with demand means "detour required"; capped so detours do not outrank real hotspots

    def _recompute_scores(self, keys) -> None:
        for key in keys:
            cell = self.cells[key]
            supply = 0.0
            for l in self.routable_layers:
                supply += self.grid * max(0.0, 1.0 - cell.blocked.get(l, 0.0))
            cell.supply_mil = supply
            if supply > self.grid * 0.05:
                cell.score = round(min(cell.demand_mil / supply, self.BLOCKED_SCORE_CAP), 3)
            else:
                cell.score = self.BLOCKED_SCORE_CAP if cell.demand_mil > 0 else 0.0

    # ------------------------------------------------------------------ incremental update
    def update_components(self, moved: Dict[str, Dict[str, Any]]) -> Set[Tuple[int, int]]:
        """Apply new component records (same schema as the PCB dump) and recompute only what they touch.
        Returns the set of cells whose score changed."""
        affected_nets: Set[str] = set()
        touched: Set[Tuple[int, int]] = set()
        # 1. remove old pads and demand
        for ref in moved:
            old = self.dump.get(ref)
            if not old:
                continue
            for pad in [p for p in self.board.pads.values() if p.ref == ref]:
                touched.add(self._pad_cells.get(pad.pad_id, self._cell_of(pad.x_mil, pad.y_mil)))
                self._add_pad(pad, sign=-1.0)
                self._escape.pop(pad.pad_id, None)
                if pad.net:
                    affected_nets.add(pad.net)
        for net in affected_nets:
            for key, amt, is_power in self._net_contrib.get(net, []):
                cell = self.cells[key]
                cell.demand_mil -= amt
                if is_power:
                    cell.power_demand_mil -= amt
                cell.nets.discard(net)
                touched.add(key)
            self._net_contrib.pop(net, None)
        # 2. replace records and rebuild the board model for those refs
        for ref, comp in moved.items():
            self.dump[ref] = comp
        self.board = BoardIntelligenceEngine(self.w_mil, self.h_mil, self.stackup, self.dump)
        self._escape = {k: v for k, v in self._escape.items() if k.split(".")[0] not in moved}
        self.graph = RoutabilityEvaluator.build_connectivity_graph(self.dump)
        # 3. re-add pads and demand
        for pad in [p for p in self.board.pads.values() if p.ref in moved]:
            self._add_pad(pad)
            touched.add(self._cell_of(pad.x_mil, pad.y_mil))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    k2 = (touched and self._cell_of(pad.x_mil, pad.y_mil)[0] + dx, self._cell_of(pad.x_mil, pad.y_mil)[1] + dy)
                    if k2 in self.cells:
                        touched.add(k2)
        for net in affected_nets | {p.net for p in self.board.pads.values() if p.ref in moved and p.net}:
            self._add_net_demand(net)
            touched.update(k for k, _, _ in self._net_contrib.get(net, []))
        self._recompute_scores(touched)
        return touched

    # ------------------------------------------------------------------ analysis
    def analyze(self, include_cells: bool = False) -> DenseBoardReport:
        t0 = time.perf_counter()
        # Escape analysis for every pad (cached)
        esc_counter: Counter = Counter()
        fine_pitch_cells: Counter = Counter()
        for pad in self.board.pads.values():
            a = self._escape_of(pad)
            esc_counter[a.difficulty] += 1
            if a.pitch_mil <= FINE_PITCH_MIL or a.difficulty in ("RESTRICTED_ESCAPE", "CRITICAL_ESCAPE", "NO_LEGAL_ESCAPE_FOUND"):
                fine_pitch_cells[self._cell_of(pad.x_mil, pad.y_mil)] += 1
        for key, n in fine_pitch_cells.items():
            self.cells[key].fine_pitch_pads = n

        # Crossings per cell
        self._attribute_crossings()

        scores = sorted((c.score for c in self.cells.values()), reverse=True)
        top = scores[:max(1, len(scores) // 10)]
        overall = round(sum(top) / len(top), 3)
        overloaded = sum(1 for c in self.cells.values() if c.score >= 1.0)
        hot_cells = [k for k, c in self.cells.items() if c.score >= self.HOT_THRESHOLD]

        hotspots = self._cluster_hotspots(hot_cells)
        corridors = self._find_corridors(hotspots)
        priority = self._priority_order(hotspots)
        power_conflicts = [f"{h.region_id}: power nets {h.power_nets_passing} share a signal corridor "
                           f"(score {h.max_score})" for h in hotspots if h.power_nets_passing]
        recs = self._recommendations(hotspots, corridors, esc_counter, overloaded)

        report = DenseBoardReport(
            board_mm=self.board_mm, grid_mil=self.grid, nx=self.nx, ny=self.ny, layers=self.stackup,
            routable_layers=self.routable_layers, total_components=len(self.dump),
            total_pads=len(self.board.pads), total_nets=len(self.graph.nets),
            ratsnest_crossings=self.graph.ratsnest_crossings,
            mst_wirelength_mm=round(self.graph.mst_wirelength_mil / MIL, 1),
            overall_congestion=overall, overloaded_cells=overloaded, hotspot_cells=len(hot_cells),
            hotspots=hotspots, corridors=corridors, escape_summary=dict(esc_counter),
            priority_net_order=priority, plane_nets=sorted(set(self.plane_layers.values())),
            power_conflicts=power_conflicts, recommendations=recs,
            analysis_ms=round(self._build_ms + (time.perf_counter() - t0) * 1000.0, 2),
            cells=[{"cx": c.cx, "cy": c.cy, "score": c.score, "pads": c.pad_count, "crossings": c.crossings}
                   for c in self.cells.values() if c.score > 0 or c.pad_count > 0] if include_cells else [],
        )
        self.last_report = report
        return report

    def _attribute_crossings(self) -> None:
        for c in self.cells.values():
            c.crossings = 0
        segs = []
        for net, edges in self.graph.multi_terminal_trees.items():
            if POWER_RX.match(net):
                continue
            for e in edges:
                p1, p2 = (e[0].x_mil, e[0].y_mil), (e[1].x_mil, e[1].y_mil)
                segs.append((p1, p2, min(p1[0], p2[0]), max(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[1], p2[1])))
        segs.sort(key=lambda s: s[2])
        n = len(segs)
        for i in range(n):
            a = segs[i]
            for j in range(i + 1, min(i + 400, n)):
                b = segs[j]
                if b[2] > a[3]:
                    break
                if a[5] < b[4] or b[5] < a[4]:
                    continue
                if _segments_intersect(a[0], a[1], b[0], b[1]):
                    # attribute to the cell at the overlap-box centre (cheap and adequate at 50 mil cells)
                    cx = (max(a[2], b[2]) + min(a[3], b[3])) / 2.0
                    cy = (max(a[4], b[4]) + min(a[5], b[5])) / 2.0
                    self.cells[self._cell_of(cx, cy)].crossings += 1

    def _cluster_hotspots(self, hot_cells: List[Tuple[int, int]]) -> List[HotspotRegion]:
        hot = set(hot_cells)
        seen: Set[Tuple[int, int]] = set()
        regions: List[HotspotRegion] = []
        for start in sorted(hot, key=lambda k: -self.cells[k].score):
            if start in seen:
                continue
            stack, comp = [start], []
            seen.add(start)
            while stack:
                k = stack.pop()
                comp.append(k)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        q = (k[0] + dx, k[1] + dy)
                        if q in hot and q not in seen:
                            seen.add(q)
                            stack.append(q)
            regions.append(self._describe_region(len(regions) + 1, comp))
        regions.sort(key=lambda r: (-(r.max_score if r.pad_count else min(r.max_score, 1.0)), -r.pad_count, -len(r.cells)))
        for i, r in enumerate(regions, 1):
            r.region_id = f"H{i}"
        return regions

    def _describe_region(self, idx: int, comp: List[Tuple[int, int]]) -> HotspotRegion:
        cells = [self.cells[k] for k in comp]
        xs0 = min(c.cx for c in cells); xs1 = max(c.cx for c in cells)
        ys0 = min(c.cy for c in cells); ys1 = max(c.cy for c in cells)
        g = self.grid / MIL
        bbox = (round(xs0 * g, 2), round(ys0 * g, 2), round((xs1 + 1) * g, 2), round((ys1 + 1) * g, 2))
        nets: Counter = Counter()
        for c in cells:
            for n in c.nets:
                nets[n] += 1
        pad_count = sum(c.pad_count for c in cells)
        fine = sum(c.fine_pitch_pads for c in cells)
        crossings = sum(c.crossings for c in cells)
        # free layers: routable layers with mean blocked fraction < 0.5 across the region
        free_layers = []
        for l in self.routable_layers:
            mean_blocked = sum(c.blocked.get(l, 0.0) for c in cells) / len(cells)
            if mean_blocked < 0.5:
                free_layers.append(l)
        # escape directions of pads inside the region
        dirs: Counter = Counter()
        comps: Set[str] = set()
        for pad in self.board.pads.values():
            if self._cell_of(pad.x_mil, pad.y_mil) in comp:
                comps.add(pad.ref)
                a = self._escape.get(pad.pad_id)
                if a and a.pitch_mil <= FINE_PITCH_MIL:
                    for d in a.legal_escape_directions:
                        dirs[d] += 1
        power_passing = sorted({n for n in nets if POWER_RX.match(n) and not GND_RX.match(n)})
        total_demand = sum(c.demand_mil for c in cells) or 1.0
        power_share = sum(c.power_demand_mil for c in cells) / total_demand
        mean_blocked_all = sum(sum(c.blocked.get(l, 0.0) for l in self.routable_layers) / len(self.routable_layers)
                               for c in cells) / len(cells)
        max_score = max(c.score for c in cells)
        mean_score = round(sum(c.score for c in cells) / len(cells), 3)

        causes, actions = [], []
        fully_blocked = sum(1 for c in cells if c.supply_mil <= self.grid * 0.05 and c.demand_mil > 0)
        if fully_blocked:
            causes.append("keep-out or pad crossing (detour required)")
            actions.append("ratsnest passes through a keep-out or solid pad field; the router must detour around it, "
                           "so reserve the neighbouring corridor")
        if fine >= 6:
            causes.append("fine-pitch escape")
            actions.append("schedule the fine-pitch nets first (stage 2) with neckdown to the pad width; keep "
                           f"escapes toward {[d for d, _ in dirs.most_common(2)] or 'the open side'}")
        if crossings >= 4:
            causes.append("signal crossing hotspot")
            actions.append("assign crossing nets to alternating layers (H on one, V on the other) or reserve a corridor")
        if power_passing and power_share >= 0.3:
            causes.append("power trunk through signal corridor")
            actions.append(f"move {power_passing} to a polygon or plane with via access instead of a routed trunk")
        if len(free_layers) <= 1:
            causes.append("layer scarcity")
            actions.append("free a layer in this region (plane access vias only) or thin the placement")
        if mean_blocked_all >= 0.6:
            causes.append("pad-blocked")
            actions.append("placement refinement: open a channel by moving a passive 0.5-1.0 mm away")
        if not causes:
            causes.append("demand exceeds supply")
            actions.append("reserve corridors for the constrained nets and route them first")

        if "fine-pitch escape" in causes:
            strategy = "ESCAPE_FIRST"
        elif "power trunk through signal corridor" in causes:
            strategy = "POWER_TO_POLYGON"
        elif "layer scarcity" in causes or "pad-blocked" in causes:
            strategy = "PLACEMENT_REFINE_THEN_ROUTE"
        else:
            strategy = "CORRIDOR_RESERVE_LAYER_SPLIT"

        return HotspotRegion(
            region_id=f"H{idx}", cells=sorted(comp), bbox_mm=bbox, max_score=round(max_score, 3),
            mean_score=mean_score, pad_count=pad_count, fine_pitch_pads=fine, net_count=len(nets),
            nets=[n for n, _ in nets.most_common(12)], crossings=crossings, free_layers=free_layers,
            preferred_escape_directions=[d for d, _ in dirs.most_common(3)], power_nets_passing=power_passing,
            causes=causes, recommended_strategy=strategy, recommended_actions=actions, components=sorted(comps)[:12],
        )

    def _find_corridors(self, hotspots: List[HotspotRegion]) -> List[Corridor]:
        """Maximal horizontal and vertical runs of quiet, unblocked cells (candidate reserved channels)."""
        def quiet(k):
            c = self.cells.get(k)
            if not c:
                return False
            blocked = sum(c.blocked.get(l, 0.0) for l in self.routable_layers) / len(self.routable_layers)
            return c.score <= self.CORRIDOR_THRESHOLD and blocked < 0.3

        region_cells = {k: h.region_id for h in hotspots for k in h.cells}
        runs: List[Corridor] = []
        min_len = 3
        g = self.grid / MIL
        # horizontal
        for cy in range(self.ny):
            cx = 0
            while cx < self.nx:
                if quiet((cx, cy)):
                    start = cx
                    while cx < self.nx and quiet((cx, cy)):
                        cx += 1
                    if cx - start >= min_len:
                        cells = [(x, cy) for x in range(start, cx)]
                        adj = sorted({region_cells[(x, y)] for x, y in cells for y in (cy - 1, cy + 1) if (x, y) in region_cells})
                        runs.append(Corridor("", "H", (round(start * g, 2), round(cy * g, 2), round(cx * g, 2), round((cy + 1) * g, 2)),
                                             round((cx - start) * g, 2), round(g, 2),
                                             round(sum(self.cells[k].score for k in cells) / len(cells), 3), adj))
                else:
                    cx += 1
        for cx in range(self.nx):
            cy = 0
            while cy < self.ny:
                if quiet((cx, cy)):
                    start = cy
                    while cy < self.ny and quiet((cx, cy)):
                        cy += 1
                    if cy - start >= min_len:
                        cells = [(cx, y) for y in range(start, cy)]
                        adj = sorted({region_cells[(x, y)] for x, y in cells for x in (cx - 1, cx + 1) if (x, y) in region_cells})
                        runs.append(Corridor("", "V", (round(cx * g, 2), round(start * g, 2), round((cx + 1) * g, 2), round(cy * g, 2)),
                                             round((cy - start) * g, 2), round(g, 2),
                                             round(sum(self.cells[k].score for k in cells) / len(cells), 3), adj))
                else:
                    cy += 1
        # corridors next to hotspots are the valuable ones; then the longest
        runs.sort(key=lambda r: (-len(r.adjacent_regions), -r.length_mm))
        runs = runs[:12]
        for i, r in enumerate(runs, 1):
            r.corridor_id = f"C{i}"
        return runs

    def _priority_order(self, hotspots: List[HotspotRegion]) -> List[str]:
        region_score: Dict[str, float] = defaultdict(float)
        for h in hotspots:
            for n in h.nets:
                region_score[n] = max(region_score[n], h.max_score)
        scored = []
        for net, endpoints in self.graph.nets.items():
            if len(endpoints) < 2 or net in self.plane_layers.values():
                continue
            esc = 1.0
            for ep in endpoints:
                a = self._escape.get(f"{ep.ref}.{ep.pad_num}")
                if a:
                    esc = max(esc, ESCAPE_WEIGHT.get(a.difficulty, 1.0))
            diff = 6.0 if re.search(r"_(P|N|DP|DM|\+|-)$", net) or re.search(r"USB_D[PM]|D\+|D-", net) else 0.0
            pwr = 3.0 if POWER_RX.match(net) and not GND_RX.match(net) else 0.0
            terms = min(4.0, len(endpoints) / 4.0)
            scored.append((esc * 2.0 + region_score[net] * 5.0 + diff + pwr + terms, net))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [n for _, n in scored]

    def _recommendations(self, hotspots, corridors, esc_counter, overloaded) -> List[str]:
        recs = []
        if esc_counter.get("NO_LEGAL_ESCAPE_FOUND"):
            recs.append(f"{esc_counter['NO_LEGAL_ESCAPE_FOUND']} pads have no legal escape: fix placement or footprint before routing")
        if overloaded:
            recs.append(f"{overloaded} cells are overloaded (demand > supply): routing will need detours, vias or placement changes")
        for h in hotspots[:5]:
            recs.append(f"{h.region_id} {h.bbox_mm} score {h.max_score}: {', '.join(h.causes)} -> {h.recommended_strategy}")
        for c in corridors[:3]:
            if c.adjacent_regions:
                recs.append(f"reserve corridor {c.corridor_id} ({c.orientation}, {c.length_mm} mm) next to {c.adjacent_regions} for constrained nets")
        if not hotspots:
            recs.append("no hotspot regions: standard routing order is adequate")
        return recs


def dump_to_board_mm(dump: Dict[str, Any], margin_mm: float = 2.0) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Fallback board extent from the dump when no placement.json exists: (board_mm, origin_mm)."""
    xs, ys = [], []
    for c in dump.values():
        if not isinstance(c, dict):
            continue
        b = c.get("bbox") or [0, 0, 0, 0]
        xs += [c["x"] + b[0], c["x"] + b[1]]
        ys += [c["y"] + b[2], c["y"] + b[3]]
    if not xs:
        return (50.0, 50.0), (0.0, 0.0)
    ox = min(xs) / MIL - margin_mm
    oy = min(ys) / MIL - margin_mm
    w = (max(xs) - min(xs)) / MIL + 2 * margin_mm
    h = (max(ys) - min(ys)) / MIL + 2 * margin_mm
    return (round(w, 2), round(h, 2)), (round(ox, 2), round(oy, 2))
