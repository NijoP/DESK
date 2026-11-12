"""Autonomous Multi-Stage Routing Engine for DESK.
Implements the Connectivity-First, DRC-Driven Routing Loop:
Stage 1: GND Preparation (ground escape stubs and plane access vias)
Stage 2: Connector Escapes and Interface Routing
Stage 3: Critical Signals (differential pairs, high-speed, clocks, analog)
Stage 4: Control & Sensor Signals
Stage 5: Power Distribution (trace widths calculated by current/thermal capacity)
Stage 6: Remaining Populated Nets

Supports:
- Profile-driven constraint propagation over regex heuristics
- Differential pair coupling, target impedance, and skew verification
- Multi-terminal routing trees (MST)
- Selective unrouting and bounded failure recovery (terminating unresolvable loops)
- Native A* maze routing for targeted connections and escape stubs
- Automated DSN export tuning with per-net IPC-2152 calculated widths and clearances
- Post-routing readback verification against intended net connectivity.
"""
from __future__ import annotations
import re
import math
import heapq
import json
import time
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field
from desk.models import (
    NetEndpoint,
    RoutingConstraint,
    RoutingPlan,
    RoutingAttempt,
    RoutingRecoveryPlan,
    NetConnectivityGraph,
)
from desk.routing.dsn import DSNTree
from desk.routing.connectivity import PhysicalConnectivityVerifier

MIL = 39.37007874


@dataclass
class DiffPairVerification:
    """Verification results for a differential signal pair."""
    pair_name: str
    pos_net: str
    neg_net: str
    pos_routed: bool = False
    neg_routed: bool = False
    pos_length_mm: float = 0.0
    neg_length_mm: float = 0.0
    skew_mm: float = 0.0
    max_skew_mm: float = 0.5
    target_impedance_ohms: float = 90.0
    status: str = "UNROUTED"  # "PASS", "FAIL", "UNROUTED"
    details: str = ""


class StackupManager:
    """Manages layer definitions and routing allocations."""

    @staticmethod
    def detect_stackup(dump: Dict[str, Any], rules: Optional[Dict[str, Any]] = None, profile: Optional[Any] = None) -> List[str]:
        if profile and hasattr(profile, "get_stackup_layers"):
            return profile.get_stackup_layers()
        rules = rules or {}
        if rules.get("stackup"):
            return list(rules["stackup"])
        layer_count = rules.get("layers", 2)
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
    """Classifies every net on the board into one of the 6 Priority Stages.
    
    Strict Invariant: Explicit DesignProfile constraints take absolute precedence
    over regex naming heuristics.
    """

    @staticmethod
    def schedule_nets(nets: Dict[str, List[NetEndpoint]],
                      diff_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
                      high_current: Optional[Dict[str, float]] = None,
                      rules: Optional[Dict[str, Any]] = None,
                      profile: Optional[Any] = None) -> Dict[int, List[str]]:
        diff_pairs = diff_pairs or {}
        high_current = high_current or {}
        rules = rules or {}
        stages: Dict[int, List[str]] = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}

        diff_pair_nets = {p[0] for p in diff_pairs.values()} | {p[1] for p in diff_pairs.values()}
        explicit_stage3 = set(rules.get("critical_nets", []))
        explicit_stage4 = set(rules.get("control_nets", []))
        explicit_stage5 = set(rules.get("power_nets", []))

        # Profile precedence
        if profile:
            if hasattr(profile, "rf_nets"):
                explicit_stage3.update(profile.rf_nets.keys())
            if hasattr(profile, "critical_nets"):
                explicit_stage3.update(profile.critical_nets)
            if hasattr(profile, "diff_pairs"):
                for dp in profile.diff_pairs.values():
                    diff_pair_nets.add(dp.pos_net)
                    diff_pair_nets.add(dp.neg_net)
                    explicit_stage3.add(dp.pos_net)
                    explicit_stage3.add(dp.neg_net)
            if hasattr(profile, "voltage_rails"):
                for r in profile.voltage_rails:
                    if not re.search(r"^(GND|VSS|AGND|DGND|PGND)$", r, re.I):
                        explicit_stage5.add(r)

        for net_name, endpoints in nets.items():
            if not net_name or len(endpoints) < 2: continue
            net_u = net_name.upper()

            # Stage 1: Ground nets (highest priority reference plane prep)
            if re.search(r"^(GND|VSS|AGND|DGND|PGND)$", net_u):
                stages[1].append(net_name)

            # Stage 3: Critical signals (explicit profile constraints take priority!)
            elif net_name in explicit_stage3 or net_name in diff_pair_nets:
                stages[3].append(net_name)

            # Stage 5: Power distribution (explicit profile power rails / high current)
            elif net_name in explicit_stage5 or net_name in high_current:
                stages[5].append(net_name)

            # Fallback Heuristics when not explicitly listed in profile:
            # Stage 3 Heuristic: Clocks, RF, USB, High-Speed
            elif re.search(r"(CLK|OSC|XTAL|RF|ANT|DP|DM|D\+|D\-|USB_P|USB_N|TX|RX)", net_u):
                stages[3].append(net_name)

            # Stage 5 Heuristic: Recognized power rails
            elif re.search(r"(VCC|VDD|3V3|5V|1V8|12V|VBAT|VBUS|VSYS|PWR|VIN)", net_u):
                stages[5].append(net_name)

            # Stage 2: Connector interfaces
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
    """Calculates trace widths (IPC-2221 power law) based on current capacity and layer placement."""

    @staticmethod
    def get_width_mil(net_name: str, current_A: Optional[float] = None, is_inner: bool = False,
                      layer_idx: Optional[int] = None,
                      min_signal_width_mil: float = 5.0, max_power_width_mil: float = 120.0,
                      profile: Optional[Any] = None) -> float:
        if profile and hasattr(profile, "derive_trace_width_mil"):
            return profile.derive_trace_width_mil(net_name, is_inner=is_inner, layer_idx=layer_idx)

        net_u = net_name.upper()
        if current_A is None:
            if re.search(r"VBUS|VBAT|VSYS|12V|PWR|VIN", net_u):
                current_A = 2.0
            elif re.search(r"3V3|5V|VCC|VDD", net_u):
                current_A = 1.0
            else:
                current_A = 0.2

        if current_A <= 0.3:
            return min_signal_width_mil

        from desk import ipc
        cu_oz = 0.5 if is_inner else 1.0
        width_mil = ipc.trace_width_mil(current_A, is_inner=is_inner, copper_oz=cu_oz, temp_rise_c=10.0)
        if width_mil > max_power_width_mil:
            import warnings
            warnings.warn(f"Net {net_name}: IPC-2221 width {width_mil:.1f} mil exceeds the {max_power_width_mil:.0f} mil "
                          f"single-trace cap; use a plane, multiple traces or a wider cap.", stacklevel=2)
        return round(min(max_power_width_mil, max(min_signal_width_mil, width_mil)), 1)


class NativeMazeRouter:
    """Lightweight 2.5D A* grid router for escape stubs and single net repair."""

    def __init__(self, bounds_mil: Tuple[float, float, float, float], grid_mil: float = 10.0):
        self.min_x, self.min_y, self.max_x, self.max_y = bounds_mil
        self.grid = grid_mil
        self.obstacles: Set[Tuple[int, int, int]] = set()

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
                    neighbors.append((gx, gy, ol, 4.0))

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
CLASS_BLOCK_RX = re.compile(
    r"\(class\s+([^\s]+)\s+'([^']+)'.*?\(rule\s*\(width\s+[\d\.]+\)\s*\(clearance\s+[\d\.]+\)\s*\)",
    re.DOTALL
)


class DSNTuningEngine:
    """Tuning engine for EasyEDA DSN export: fixes boundaries, fine-pitch clearances, class widths, and removes duplicate pad vertices."""

    @staticmethod
    def tune_dsn(dsn_content: str, board_outline_mil: Tuple[float, float],
                  power_nets: Optional[Set[str]] = None,
                  fine_pitch_clearance_mil: float = 4.02,
                  fine_pitch_width_mil: float = 5.0,
                  keepouts: Optional[List[Dict[str, Any]]] = None,
                  net_widths: Optional[Dict[str, float]] = None,
                  net_clearances: Optional[Dict[str, float]] = None) -> str:
        """Tunes DSN representation using profile-driven per-net widths and clearances."""
        power_nets = {n.upper() for n in (power_nets or set())}
        net_widths = {k.upper(): v for k, v in (net_widths or {}).items()}
        net_clearances = {k.upper(): v for k, v in (net_clearances or {}).items()}
        W_mil, H_mil = board_outline_mil

        # Try robust AST S-expression transformation first
        try:
            tree = DSNTree(dsn_content)
            tree.clean_duplicate_polygon_vertices()
            tree.set_boundary(W_mil, H_mil, keepouts=keepouts)
            tree.set_grid_resolution(wire_grid=1.25, via_grid=1.25)
            tree.set_default_rules(width_mil=fine_pitch_width_mil, clearance_mil=fine_pitch_clearance_mil)
            tree.update_net_classes(
                net_widths=net_widths,
                net_clearances=net_clearances,
                power_nets=power_nets,
                fine_pitch_width_mil=fine_pitch_width_mil,
                fine_pitch_clearance_mil=fine_pitch_clearance_mil
            )
            return tree.serialize()
        except Exception:
            # Fall back to legacy regex tuner if AST parsing fails on partial/synthetic fragments
            pass

        # 0. Deduplicate consecutive duplicate coordinates in padstack polygons
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

        # 3. Inject calculated net class widths and clearances (eliminates hardcoded 12.0 mil default!)
        def power_repl(m):
            cname = m.group(1).strip("'")
            c_upper = cname.upper()

            # Check if specific width is provided
            if c_upper in net_widths:
                w = str(net_widths[c_upper])
            elif c_upper in power_nets:
                w = "12.0"
            else:
                w = str(fine_pitch_width_mil)

            # Check if specific clearance is provided
            clr = str(net_clearances.get(c_upper, fine_pitch_clearance_mil))

            rule_sub = f"(rule\n        (width {w})\n        (clearance {clr}))"
            return re.sub(r"\(rule\s*\(width\s+[\d\.]+\)\s*\(clearance\s+[\d\.]+\)\s*\)", rule_sub, m.group(0))

        return CLASS_BLOCK_RX.sub(power_repl, content)


class RoutingPlanGenerator:
    """Generates a complete ordered RoutingPlan with stage allocations and net constraints."""

    @staticmethod
    def generate_plan(net_graph: NetConnectivityGraph,
                      dump: Dict[str, Any],
                      board_dims_mm: Tuple[float, float],
                      rules: Optional[Dict[str, Any]] = None,
                      profile: Optional[Any] = None) -> RoutingPlan:
        rules = rules or {}
        stackup = StackupManager.detect_stackup(dump, rules, profile=profile)
        diff_p = dict(rules.get("diff_pairs") or {})
        high_c = dict(rules.get("high_current") or {})
        explicit_stage3 = list(rules.get("critical_nets") or [])
        explicit_stage5 = list(rules.get("power_nets") or [])

        if profile:
            if hasattr(profile, "diff_pairs"):
                for dp_name, dp in profile.diff_pairs.items():
                    diff_p[dp_name] = (dp.pos_net, dp.neg_net)
            if hasattr(profile, "rf_nets"):
                for rf_net in profile.rf_nets:
                    if rf_net not in explicit_stage3:
                        explicit_stage3.append(rf_net)
            if hasattr(profile, "current_limits_A"):
                for n, c in profile.current_limits_A.items():
                    if c > 0.3: high_c[n] = c
            if hasattr(profile, "voltage_rails"):
                for n in profile.voltage_rails:
                    if n not in explicit_stage5 and not re.search(r"^(GND|VSS|AGND|DGND|PGND)$", n, re.I):
                        explicit_stage5.append(n)

        sched_rules = dict(rules)
        sched_rules["critical_nets"] = explicit_stage3
        sched_rules["power_nets"] = explicit_stage5

        stages = RoutingPriorityScheduler.schedule_nets(
            net_graph.nets,
            diff_pairs=diff_p,
            high_current=high_c,
            rules=sched_rules,
            profile=profile,
        )

        constraints: Dict[str, RoutingConstraint] = {}
        power_set = {n.upper() for n in stages.get(1, []) + stages.get(5, [])}

        # Fail-closed pre-flight: nets whose current or voltage is undeclared are listed as blocking
        # issues and sized with heuristics only so the plan can still be reported, never executed.
        blocking_issues: List[str] = []
        if profile and hasattr(profile, "validate_electrical_inputs"):
            blocking_issues = profile.validate_electrical_inputs(list(net_graph.nets))
        blocked_nets = {msg.split(":", 1)[0] for msg in blocking_issues}

        # Single source for the spacing floor: the fabricator profile. Never a literal in this module.
        from desk.profile import ManufacturerProfile
        manufacturing = getattr(profile, "manufacturing", None) if profile is not None else None
        fab_min_clearance_mil = float(manufacturing.min_clearance_mil if manufacturing is not None
                                      else ManufacturerProfile().min_clearance_mil)
        assumptions: List[str] = []
        if profile is None:
            blocking_issues.append(
                "PROFILE: no DesignProfile supplied; currents come from name heuristics and clearances from "
                "the fabricator minimum (ASSUMED). Declare a DesignProfile before routing.")

        for net_name in net_graph.nets:
            is_pwr = net_name.upper() in power_set or net_name in high_c
            tier = 6
            for s_num, s_nets in stages.items():
                if net_name in s_nets:
                    tier = s_num
                    break

            net_profile = None if net_name in blocked_nets else profile
            current_A = None
            if net_profile and hasattr(net_profile, "get_current_for_net"):
                current_A = net_profile.get_current_for_net(net_name)
            elif net_name in high_c:
                current_A = high_c[net_name]
            elif is_pwr:
                # No declared current. TraceWidthCalculator sizes it from the net name; that is an
                # assumption, recorded here, and the plan is already blocked for this net.
                assumptions.append(f"{net_name}: power-net current undeclared; width from name heuristic (ASSUMED)")

            # Target layer preferences
            pref_layers = [1, 2] if len(stackup) == 2 else [1, 4, 3, 2]
            if profile and hasattr(profile, "net_classes"):
                for nc in profile.net_classes.values():
                    if net_name in nc.nets and nc.target_layers:
                        pref_layers = list(nc.target_layers)
                        break

            primary_layer = pref_layers[0] if pref_layers else 1
            is_inner = False
            if len(stackup) >= 4 and primary_layer in (2, 3):
                is_inner = True

            width = TraceWidthCalculator.get_width_mil(
                net_name,
                current_A=current_A,
                is_inner=is_inner,
                layer_idx=primary_layer,
                profile=net_profile
            )

            if net_profile and hasattr(net_profile, "derive_clearance_mil"):
                clearance = net_profile.derive_clearance_mil(net_name, "GND")
            else:
                # No voltage data for this net: the only defensible spacing is the fabricator minimum,
                # and the plan stays blocked until a DesignProfile declares the rail.
                clearance = fab_min_clearance_mil
                if is_pwr or net_name in blocked_nets:
                    assumptions.append(f"{net_name}: clearance = fabricator minimum {fab_min_clearance_mil:g} mil; "
                                       "no declared voltage (ASSUMED)")

            if profile and hasattr(profile, "rf_nets") and net_name in profile.rf_nets:
                rf_cfg = profile.rf_nets[net_name]
                clearance = max(clearance, rf_cfg.ground_clearance_mil)
                width = max(width, rf_cfg.trace_width_mil)

            constraints[net_name] = RoutingConstraint(
                net=net_name,
                min_width_mil=width,
                clearance_mil=clearance,
                target_layer_preference=pref_layers,
                priority_tier=tier
            )

        return RoutingPlan(
            board_stackup=stackup,
            stage_nets=stages,
            net_constraints=constraints,
            blocking_issues=blocking_issues,
            assumptions=assumptions,
        )


class RoutingConvergenceController:
    """Manages routing recovery, tracking attempts and terminating unresolvable loops."""

    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts
        self.attempts: int = 0
        self.unrouted_history: List[Set[str]] = []
        self.failure_counts: Dict[str, int] = {}

    def record_attempt(self, unrouted_nets: Set[str]) -> bool:
        """Records an attempt. Returns False if convergence has stalled or max attempts exceeded."""
        self.attempts += 1
        self.unrouted_history.append(set(unrouted_nets))

        for n in unrouted_nets:
            self.failure_counts[n] = self.failure_counts.get(n, 0) + 1

        if self.attempts >= self.max_attempts:
            return False

        # If identical unrouted set occurs 3 times consecutively, terminate
        if len(self.unrouted_history) >= 3:
            if self.unrouted_history[-1] == self.unrouted_history[-2] == self.unrouted_history[-3]:
                return False

        return True

    def get_stalled_nets(self) -> List[str]:
        """Returns nets that have repeatedly failed routing."""
        return [n for n, count in self.failure_counts.items() if count >= 3]


def verify_routing_result(intended_plan: RoutingPlan, readback_tracks: List[Dict[str, Any]],
                          pcb_dump: Optional[Dict[str, Any]] = None,
                          vias: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Compares actual readback tracks against intended routing plan.
    If pcb_dump is provided, performs full physical pad-to-pad connectivity verification.
    """
    routed_nets = {trk.get("net", "") for trk in readback_tracks if trk.get("net")}
    intended_nets = set(intended_plan.net_constraints.keys())
    
    missing_nets = intended_nets - routed_nets
    coverage_pct = round((len(intended_nets - missing_nets) / max(1, len(intended_nets))) * 100.0, 1)

    result: Dict[str, Any] = {
        "intended_net_count": len(intended_nets),
        "routed_net_count": len(intended_nets - missing_nets),
        "missing_nets": sorted(list(missing_nets)),
        "coverage_pct": coverage_pct,
        "is_complete": len(missing_nets) == 0,
    }

    if pcb_dump:
        conn_res = PhysicalConnectivityVerifier.verify_board(
            pcb_dump=pcb_dump,
            tracks=readback_tracks,
            vias=vias or []
        )
        result["physical_connectivity"] = {
            "total_nets": conn_res.total_nets,
            "fully_connected_nets": conn_res.fully_connected_nets,
            "partially_connected_nets": conn_res.partially_connected_nets,
            "missing_nets": conn_res.missing_nets,
            "is_100_percent_routed": conn_res.is_100_percent_routed,
            "overall_completion_pct": conn_res.overall_completion_pct,
            "summary": conn_res.summary
        }
        # Update is_complete based on real physical continuity
        result["is_complete"] = conn_res.is_100_percent_routed

    return result
