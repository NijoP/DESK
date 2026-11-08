"""Autonomous Multi-Stage Routing Engine for DESK.
Implements the Connectivity-First, DRC-Driven Routing Loop:
Stage 1: GND Preparation (ground escape stubs and plane access vias)
Stage 2: Connector Escapes and Interface Routing
Stage 3: Critical Signals (differential pairs, high-speed, clocks, analog)
Stage 4: Control & Sensor Signals
Stage 5: Power Distribution (trace widths calculated by current/thermal capacity)
Stage 6: Remaining Populated Nets

Supports:
- Stackup detection (2-layer, 4-layer: Top, Inner1_GND, Inner2_PWR, Bottom)
- Multi-terminal routing trees (MST)
- Selective unrouting and failure recovery
- Native A* maze routing for targeted connections and escape stubs
- Automated DSN export tuning and SES import integration
"""
import re
import math
import heapq
import json
from typing import Dict, List, Tuple, Optional, Any, Set
from desk.models import (
    NetEndpoint,
    RoutingConstraint,
    RoutingPlan,
    RoutingAttempt,
    RoutingRecoveryPlan,
    NetConnectivityGraph
)

MIL = 39.37007874

class StackupManager:
    """Manages layer definitions and routing allocations."""

    @staticmethod
    def detect_stackup(dump: Dict[str, Any], rules: Optional[Dict[str, Any]] = None) -> List[str]:
        rules = rules or {}
        layer_count = rules.get("layers", 2)
        # Check if any primitives in dump reference inner layers (e.g. layer 3, 4, 15, 16)
        has_inner = False
        for comp in dump.values():
            for p in comp.get("pads", []):
                if p.get("layer") in (3, 4, 15, 16):
                    has_inner = True
                    break
            if has_inner: break

        if layer_count == 4 or has_inner:
            return ["Top", "Inner1_GND", "Inner2_PWR", "Bottom"]
        return ["Top", "Bottom"]

class RoutingPriorityScheduler:
    """Classifies every net on the board into one of the 6 Priority Stages."""

    @staticmethod
    def schedule_nets(nets: Dict[str, List[NetEndpoint]],
                      diff_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
                      high_current: Optional[Dict[str, float]] = None,
                      rules: Optional[Dict[str, Any]] = None) -> Dict[int, List[str]]:
        diff_pairs = diff_pairs or {}
        high_current = high_current or {}
        rules = rules or {}
        stages: Dict[int, List[str]] = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}

        diff_pair_nets = {p[0] for p in diff_pairs.values()} | {p[1] for p in diff_pairs.values()}
        explicit_stage3 = set(rules.get("critical_nets", []))
        explicit_stage4 = set(rules.get("control_nets", []))
        explicit_stage5 = set(rules.get("power_nets", []))

        for net_name, endpoints in nets.items():
            if not net_name or len(endpoints) < 2: continue
            net_u = net_name.upper()

            # Stage 1: Ground nets
            if re.search(r"^(GND|VSS|AGND|DGND|PGND)$", net_u):
                stages[1].append(net_name)

            # Stage 3: Critical signals (diff pairs, clocks, RF, analog)
            elif net_name in diff_pair_nets or net_name in explicit_stage3 or \
                 re.search(r"(CLK|OSC|XTAL|RF|ANT|DP|DM|D\+|D\-|USB_P|USB_N|TX|RX)", net_u):
                stages[3].append(net_name)

            # Stage 5: Power distribution
            elif net_name in high_current or net_name in explicit_stage5 or \
                 re.search(r"(VCC|VDD|3V3|5V|1V8|12V|VBAT|VBUS|VSYS|PWR|VIN)", net_u):
                stages[5].append(net_name)

            # Stage 2: Connector interfaces (connected to connectors or screw terminals)
            elif any(re.match(r"^(J|CN|CON|USB|TB|TERM|HDR)\d+", ep.ref, re.I) for ep in endpoints):
                stages[2].append(net_name)

            # Stage 4: Control & sensor signals
            elif net_name in explicit_stage4 or \
                 re.search(r"(SCL|SDA|MOSI|MISO|SCK|CS|SS|EN|RST|RESET|INT|PWM|GPIO|ADC|DAC)", net_u):
                stages[4].append(net_name)

            # Stage 6: Remaining signals
            else:
                stages[6].append(net_name)

        return stages

class TraceWidthCalculator:
    """Calculates IPC-2152 trace widths based on current capacity and layer placement."""

    @staticmethod
    def get_width_mil(net_name: str, current_A: float = 0.2, is_inner: bool = False,
                      min_signal_width_mil: float = 5.0, max_power_width_mil: float = 40.0) -> float:
        net_u = net_name.upper()
        # High power / supply nets default to thicker traces
        if re.search(r"VBUS|VBAT|VSYS|12V", net_u):
            current_A = max(current_A, 1.5)
        elif re.search(r"3V3|5V|VCC|VDD", net_u):
            current_A = max(current_A, 0.8)

        if current_A <= 0.3:
            return min_signal_width_mil

        # IPC-2152 simplified: Area ~= (I / (k * deltaT^0.44))^(1/0.725)
        # For 1 oz copper (1.37 mil thick), width ~= Area / 1.37
        k = 0.024 if is_inner else 0.048
        delta_T = 10.0  # 10 deg C temp rise
        area_mil2 = (current_A / (k * (delta_T ** 0.44))) ** (1.0 / 0.725)
        width_mil = area_mil2 / 1.37
        return round(min(max_power_width_mil, max(min_signal_width_mil, width_mil)), 1)

class NativeMazeRouter:
    """Lightweight 2.5D A* grid router for escape stubs and single net repair."""

    def __init__(self, bounds_mil: Tuple[float, float, float, float], grid_mil: float = 10.0):
        self.min_x, self.min_y, self.max_x, self.max_y = bounds_mil
        self.grid = grid_mil
        self.obstacles: Set[Tuple[int, int, int]] = set()  # (gx, gy, layer)

    def add_obstacle(self, x_mil: float, y_mil: float, radius_mil: float, layers: List[int]):
        r_grid = int(math.ceil(radius_mil / self.grid))
        gx = int(round((x_mil - self.min_x) / self.grid))
        gy = int(round((y_mil - self.min_y) / self.grid))
        for dx in range(-r_grid, r_grid + 1):
            for dy in range(-r_grid, r_grid + 1):
                if dx * dx + dy * dy <= r_grid * r_grid:
                    for l in layers:
                        self.obstacles.add((gx + dx, gy + dy, l))

    def route_net_segment(self, start_mil: Tuple[float, float], end_mil: Tuple[float, float],
                          allowed_layers: List[int] = [1, 2]) -> Optional[List[Tuple[float, float, int]]]:
        """A* search for a legal track path connecting start to end."""
        sgx = int(round((start_mil[0] - self.min_x) / self.grid))
        sgy = int(round((start_mil[1] - self.min_y) / self.grid))
        egx = int(round((end_mil[0] - self.min_x) / self.grid))
        egy = int(round((end_mil[1] - self.min_y) / self.grid))

        # Priority queue entries: (f_score, cost, (gx, gy, layer))
        start_node = (sgx, sgy, allowed_layers[0])
        open_set = []
        heapq.heappush(open_set, (0, 0, start_node))
        came_from = {}
        cost_so_far = {start_node: 0}

        def heuristic(node):
            return (abs(node[0] - egx) + abs(node[1] - egy)) * self.grid

        found = False
        end_node = None
        max_iterations = 8000
        iterations = 0

        while open_set and iterations < max_iterations:
            iterations += 1
            _, current_cost, current = heapq.heappop(open_set)

            if current[0] == egx and current[1] == egy:
                found = True
                end_node = current
                break

            gx, gy, glayer = current

            # 4-directional moves on same layer
            neighbors = []
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbors.append((gx + dx, gy + dy, glayer, 1.0))

            # Via layer transition move
            for ol in allowed_layers:
                if ol != glayer:
                    neighbors.append((gx, gy, ol, 4.0))  # via penalty

            for nx, ny, nl, move_cost in neighbors:
                if (nx, ny, nl) in self.obstacles: continue
                new_cost = current_cost + move_cost * self.grid
                neighbor_node = (nx, ny, nl)
                if neighbor_node not in cost_so_far or new_cost < cost_so_far[neighbor_node]:
                    cost_so_far[neighbor_node] = new_cost
                    priority = new_cost + heuristic(neighbor_node)
                    heapq.heappush(open_set, (priority, new_cost, neighbor_node))
                    came_from[neighbor_node] = current

        if not found or end_node is None:
            return None

        # Reconstruct path
        path = []
        curr = end_node
        while curr in came_from:
            wx = self.min_x + curr[0] * self.grid
            wy = self.min_y + curr[1] * self.grid
            path.append((round(wx, 2), round(wy, 2), curr[2]))
            curr = came_from[curr]
        path.reverse()
        return path

BOUNDARY_RX = re.compile(r"\(boundary\s*\(path[^\)]+\)\s*\)")
RULE_WIDTH_RX = re.compile(r"\(rule\s*\(width\s+[\d\.]+\)\)")
CLASS_BLOCK_RX = re.compile(r"\(class\s+([^\s]+)\s+'([^']+)'\s*\(rule\s*\(width\s+[\d\.]+\)\s*\(clearance\s+[\d\.]+\)\)", re.MULTILINE)

class DSNTuningEngine:
    """Tuning engine for EasyEDA DSN export: fixes boundaries, fine-pitch clearances, class widths, and removes duplicate pad vertices."""

    @staticmethod
    def tune_dsn(dsn_content: str, board_outline_mil: Tuple[float, float],
                 power_nets: Optional[Set[str]] = None,
                 fine_pitch_clearance_mil: float = 4.02,
                 fine_pitch_width_mil: float = 5.0,
                 keepouts: Optional[List[Dict[str, Any]]] = None) -> str:
        power_nets = {n.upper() for n in (power_nets or set())}
        W_mil, H_mil = board_outline_mil

        # 0. Deduplicate consecutive duplicate coordinates in padstack polygons to prevent Freerouting infinite calculation loops
        def clean_poly(m):
            tokens = m.group(1).split()
            if len(tokens) < 2:
                return m.group(0)
            layer, width, coords = tokens[0], tokens[1], tokens[2:]
            pts = []
            for i in range(0, len(coords)-1, 2):
                pt = (coords[i], coords[i+1])
                if not pts or pt != pts[-1]:
                    pts.append(pt)
            return f"(polygon {layer} {width} {' '.join(f'{x} {y}' for x, y in pts)})"
        content = re.sub(r"\(polygon\s+([^\)]+)\)", clean_poly, dsn_content)

        # 1. Update boundary to match true board dimension rectangle and profile-driven keepouts
        boundary_parts = [f"(boundary\n    (path signal 0 0 0 0 {W_mil:.2f} {H_mil:.2f} {W_mil:.2f} {H_mil:.2f} 0 0 0)\n  )"]
        if keepouts:
            for ko in keepouts:
                name = ko.get("name", "KEEPOUT")
                rect = ko.get("rect_mil")
                if not rect and ko.get("rect_mm"):
                    rm = ko["rect_mm"]
                    rect = (rm[0] * MIL, rm[1] * MIL, rm[2] * MIL, rm[3] * MIL)
                if rect:
                    x1, y1, x2, y2 = rect
                    boundary_parts.append(
                        f"    (keepout \"{name}\"\n"
                        f"      (polygon signal 0 {x1:.2f} {y1:.2f} {x2:.2f} {y1:.2f} {x2:.2f} {y2:.2f} {x1:.2f} {y2:.2f})\n"
                        f"    )"
                    )
        new_boundary = "\n".join(boundary_parts)
        content = BOUNDARY_RX.sub(new_boundary, content, count=1)

        # 2. Tune default track width and clearance for fine pitch escape
        content = RULE_WIDTH_RX.sub(f"(rule (width {fine_pitch_width_mil}))", content)
        content = re.sub(r"\(grid\s+wire\s+[\d\.]+\)", "(grid wire 1.25)", content)
        content = re.sub(r"\(grid\s+via\s+[\d\.]+\)", "(grid via 1.25)", content)

        # 3. Inject power net class widths
        def power_repl(m):
            cname = m.group(1).strip("'")
            w = "12.0" if cname.upper() in power_nets else str(fine_pitch_width_mil)
            return (f"(class {m.group(1)} '{m.group(2)}'\n"
                    f"      (rule\n"
                    f"        (width {w})\n"
                    f"        (clearance {fine_pitch_clearance_mil}))")

        return CLASS_BLOCK_RX.sub(power_repl, content)

class RoutingPlanGenerator:
    """Generates a complete ordered RoutingPlan with stage allocations and net constraints."""

    @staticmethod
    def generate_plan(net_graph: NetConnectivityGraph,
                      dump: Dict[str, Any],
                      board_dims_mm: Tuple[float, float],
                      rules: Optional[Dict[str, Any]] = None) -> RoutingPlan:
        rules = rules or {}
        stackup = StackupManager.detect_stackup(dump, rules)
        stages = RoutingPriorityScheduler.schedule_nets(
            net_graph.nets,
            diff_pairs=rules.get("diff_pairs"),
            high_current=rules.get("high_current"),
            rules=rules
        )

        constraints: Dict[str, RoutingConstraint] = {}
        power_set = {n.upper() for n in stages.get(1, []) + stages.get(5, [])}

        for net_name in net_graph.nets:
            is_pwr = net_name.upper() in power_set
            tier = 6
            for s_num, s_nets in stages.items():
                if net_name in s_nets:
                    tier = s_num
                    break

            width = TraceWidthCalculator.get_width_mil(
                net_name,
                current_A=1.0 if is_pwr else 0.2,
                is_inner=("Inner" in stackup[0])
            )

            constraints[net_name] = RoutingConstraint(
                net=net_name,
                min_width_mil=width,
                clearance_mil=4.02 if not is_pwr else 6.0,
                target_layer_preference=[1, 2] if len(stackup) == 2 else [1, 4, 3, 2],
                priority_tier=tier
            )

        return RoutingPlan(
            board_stackup=stackup,
            stage_nets=stages,
            net_constraints=constraints
        )
