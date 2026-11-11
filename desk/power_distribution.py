"""Power distribution intelligence: from declared rail currents and real pad geometry to a
distribution strategy per rail, copper sizing, via arrays, voltage-drop estimates, zone
proposals and a copper-zone verification report.

Inputs (never guessed):
* currents and voltages from `DesignProfile` (fail-closed: undeclared rails are reported, not sized)
* pad geometry from the PCB dump; planes/keep-outs from placement.json
* copper weight and temperature rise from the profile

Outputs are proposals for the engineer and inputs for the router (plane nets, polygon zones);
nothing here mutates a board.

Zero external dependencies.
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from desk import ipc
from desk.copper import CopperPlaneEngine, CopperZoneSpec
from desk.routability import RoutabilityEvaluator
from desk.routing.density import MIL, GND_RX, POWER_RX

RHO_CU_OHM_M = 1.72e-8          # copper resistivity at 20 C
OZ_TO_M = 34.8e-6               # 1 oz copper thickness in metres
SOURCE_RX = re.compile(r"^(U|VR|PS|J|BAT|BT|CN|P)\d*", re.I)


@dataclass
class RailPlan:
    net: str
    current_a: Optional[float]
    current_confidence: str
    voltage_v: Optional[float]
    pad_count: int
    component_count: int
    source_ref: Optional[str]
    load_refs: List[str]
    mst_length_mm: float
    spread_mm: float
    strategy: str                       # PLANE | POLYGON | WIDE_TRACE | TRACE | BLOCKED
    trace_width_mil: Optional[float]
    resistance_mohm_worst_path: Optional[float]
    voltage_drop_mv_worst_path: Optional[float]
    drop_pct: Optional[float]
    vias_per_transition: Optional[int]
    plane_layer: Optional[str]
    rationale: List[str]
    zone: Optional[Dict[str, Any]] = None


@dataclass
class ZoneCheck:
    zone_id: str
    net: str
    layer: str
    area_mm2: float
    pads_inside: int
    pads_outside: int
    boundary_violations: List[str]
    islands: Dict[str, Any]
    status: str                         # OK | UNRESOLVED_PADS | BOUNDARY_VIOLATION | EMPTY


@dataclass
class PowerDistributionReport:
    rails: List[RailPlan]
    ground: Dict[str, Any]
    zones: List[ZoneCheck]
    blocking_issues: List[str]
    plane_nets: List[str]
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PowerDistributionPlanner:
    def __init__(self, dump: Dict[str, Any], profile: Any, plan: Dict[str, Any],
                 max_drop_pct: float = 2.0, via_drill_mil: float = 12.0, via_plating_mil: float = 1.0):
        self.dump = {r: c for r, c in dump.items() if isinstance(c, dict)}
        self.profile = profile
        self.plan = plan
        self.board_mm = tuple(plan.get("board_mm", [50.0, 50.0]))
        self.origin_mm = tuple(plan.get("origin_mm", [0.0, 0.0]))
        self.planes = plan.get("planes", []) or []
        self.max_drop_pct = max_drop_pct
        self.via_drill = via_drill_mil
        self.via_plating = via_plating_mil
        self.graph = RoutabilityEvaluator.build_connectivity_graph(self.dump)
        self.cu_oz = profile.stackup[0].copper_thickness_oz if getattr(profile, "stackup", None) else 1.0
        self.temp_rise = max(1.0, getattr(getattr(profile, "thermal", None), "max_temperature_rise_c", 10.0))

    # ------------------------------------------------------------------ helpers
    def _pads_mm(self, net: str) -> List[Dict[str, Any]]:
        out = []
        for ep in self.graph.nets.get(net, []):
            out.append({"ref": ep.ref, "pad": ep.pad_num, "net": net,
                        "x_mm": ep.x_mil / MIL - self.origin_mm[0], "y_mm": ep.y_mil / MIL - self.origin_mm[1],
                        "layer": ep.layer})
        return out

    def _power_nets(self) -> List[str]:
        declared = set(getattr(self.profile, "current_limits_A", {}) or {})
        for nc in getattr(self.profile, "net_classes", {}).values():
            declared |= set(nc.nets)
        rail_rx = re.compile(r"^(V[A-Z0-9_]+|PWR|\d+V\d*|SW|LX|PHASE)", re.I)
        pattern = {n for n in self.graph.nets if (POWER_RX.match(n) or rail_rx.match(n)) and not GND_RX.match(n)}
        return sorted((declared | pattern) & set(self.graph.nets))

    def _source_ref(self, net: str, pads: List[Dict[str, Any]]) -> Optional[str]:
        roles = (self.plan.get("roles", {}) or {}).get("power_sources", {}) or {}
        if net in roles:
            return roles[net]
        counts: Dict[str, int] = {}
        for p in pads:
            counts[p["ref"]] = counts.get(p["ref"], 0) + 1
        cands = [(SOURCE_RX.match(r) is not None, n, r) for r, n in counts.items()]
        cands.sort(key=lambda t: (-int(t[0]), -t[1], t[2]))
        return cands[0][2] if cands else None

    def _resistance_mohm(self, length_mm: float, width_mil: float) -> float:
        w_m = width_mil * 25.4e-6
        t_m = self.cu_oz * OZ_TO_M
        return RHO_CU_OHM_M * (length_mm / 1000.0) / (w_m * t_m) * 1000.0

    def _plane_for(self, net: str) -> Optional[str]:
        for p in self.planes:
            if p.get("net") == net:
                return str(p.get("layer"))
        return None

    # ------------------------------------------------------------------ rails
    def plan_rail(self, net: str) -> RailPlan:
        pads = self._pads_mm(net)
        refs = sorted({p["ref"] for p in pads})
        src = self._source_ref(net, pads)
        loads = [r for r in refs if r != src]
        xs = [p["x_mm"] for p in pads]; ys = [p["y_mm"] for p in pads]
        spread = round(math.hypot(max(xs) - min(xs), max(ys) - min(ys)), 1) if pads else 0.0
        mst_mm = round(sum(math.hypot(e[0].x_mil - e[1].x_mil, e[0].y_mil - e[1].y_mil)
                           for e in self.graph.multi_terminal_trees.get(net, [])) / MIL, 1)
        cur, conf = self.profile.get_net_current_status(net)
        volt, vconf = self.profile.get_net_voltage_status(net)
        rationale: List[str] = []
        plane_layer = self._plane_for(net)

        if conf == "UNKNOWN" or cur is None or cur <= 0:
            return RailPlan(net, None, conf, volt, len(pads), len(refs), src, loads, mst_mm, spread, "BLOCKED", None,
                            None, None, None, None, plane_layer,
                            [f"current for {net} is {conf}: declare current_limits_A['{net}'] before sizing"])

        width = ipc.trace_width_mil(cur, is_inner=False, copper_oz=self.cu_oz, temp_rise_c=self.temp_rise,
                                    min_width_mil=self.profile.manufacturing.min_trace_width_mil)
        r_mohm = self._resistance_mohm(mst_mm, width)
        drop_mv = cur * r_mohm
        drop_pct = (drop_mv / 1000.0 / volt * 100.0) if volt else None
        vias = ipc.vias_required(cur, self.via_drill, self.via_plating, self.temp_rise)

        if plane_layer:
            strategy = "PLANE"
            rationale.append(f"plane declared on {plane_layer}; loads tap the plane with {vias} via(s) each")
        elif cur >= 2.0 or (drop_pct is not None and drop_pct > self.max_drop_pct) or width > 60.0:
            strategy = "POLYGON"
            rationale.append(f"{cur} A needs {width:.0f} mil; a polygon keeps drop below {self.max_drop_pct}% "
                             f"(estimated {drop_mv:.0f} mV over the {mst_mm} mm tree as a trace)")
        elif cur > 0.5:
            strategy = "WIDE_TRACE"
            rationale.append(f"{cur} A -> {width:.0f} mil trace; estimated worst-path drop {drop_mv:.0f} mV")
        else:
            strategy = "TRACE"
            rationale.append(f"{cur} A fits a {width:.0f} mil trace")
        if spread > 15.0 and strategy in ("WIDE_TRACE", "POLYGON"):
            rationale.append(f"loads spread over {spread} mm: distribute as a star/trunk with branches, not a daisy chain")

        zone = None
        if strategy == "POLYGON":
            z = CopperPlaneEngine.plan_power_polygons(net, 1, "Top", pads, self.board_mm, self.profile)
            if z:
                zone = asdict(z)
        return RailPlan(net, cur, conf, volt, len(pads), len(refs), src, loads, mst_mm, spread, strategy,
                        round(width, 1), round(r_mohm, 2), round(drop_mv, 1), round(drop_pct, 3) if drop_pct is not None else None,
                        vias, plane_layer, rationale, zone)

    # ------------------------------------------------------------------ zones
    def check_zone(self, zone: CopperZoneSpec) -> ZoneCheck:
        pads = self._pads_mm(zone.net)
        inside = [p for p in pads if CopperPlaneEngine.point_in_polygon(p["x_mm"], p["y_mm"], zone.points_mm)]
        outside = [p for p in pads if p not in inside]
        area = CopperPlaneEngine.calculate_polygon_area_mm2(zone.points_mm)
        viol = CopperPlaneEngine.check_polygon_boundary(zone, self.board_mm, keepouts=self.plan.get("keepouts"))
        islands = CopperPlaneEngine.detect_copper_islands(zone, pads)
        if area <= 0:
            status = "EMPTY"
        elif viol:
            status = "BOUNDARY_VIOLATION"
        elif outside:
            status = "UNRESOLVED_PADS"
        else:
            status = "OK"
        return ZoneCheck(zone.zone_id, zone.net, zone.layer_name, round(area, 1), len(inside), len(outside), viol, islands, status)

    def declared_zones(self) -> List[CopperZoneSpec]:
        out = []
        names = [s.name for s in getattr(self.profile, "stackup", [])]
        for i, p in enumerate(self.planes):
            layer_name = str(p.get("layer"))
            idx = names.index(layer_name) + 1 if layer_name in names else 0
            out.append(CopperZoneSpec(zone_id=f"DECLARED_{p['net']}_{layer_name}", net=p["net"], layer=idx, layer_name=layer_name,
                                      points_mm=[tuple(pt) for pt in p.get("polygon_mm", [])], priority=1 if GND_RX.match(p["net"]) else 2,
                                      connection_type="thermal_relief", clearance_mil=self.profile.manufacturing.min_clearance_mil,
                                      spoke_width_mil=12.0, spoke_count=4, min_island_area_mm2=2.0,
                                      is_ground_plane=bool(GND_RX.match(p["net"])), poured_area_mm2=0.0, status="DECLARED"))
        return out

    # ------------------------------------------------------------------ report
    def analyze(self) -> PowerDistributionReport:
        rails = [self.plan_rail(n) for n in self._power_nets()]
        blocking = [r.rationale[0] for r in rails if r.strategy == "BLOCKED"]
        gnd_nets = [n for n in self.graph.nets if GND_RX.match(n)]
        gnd_pads = sum(len(self.graph.nets[n]) for n in gnd_nets)
        gnd_plane = next((self._plane_for(n) for n in gnd_nets if self._plane_for(n)), None)
        ground = {
            "nets": gnd_nets, "pad_count": gnd_pads, "plane_layer": gnd_plane,
            "strategy": "CONTINUOUS_PLANE" if gnd_plane else "POUR_BOTH_SIDES_WITH_STITCHING",
            "rules": ["no splits by functional block name", "thermal relief on hand-soldered/THT pads, solid on power stages",
                      "stitching via pitch <= lambda/20 of the highest edge rate when known (UNKNOWN: use 2.5 mm)",
                      "verify continuity on poured copper, never on the outline"],
            "continuity_verified": False,
        }
        zones = [self.check_zone(z) for z in self.declared_zones()]
        for r in rails:
            if r.zone:
                zones.append(self.check_zone(CopperZoneSpec(**{k: v for k, v in r.zone.items() if k in CopperZoneSpec.__dataclass_fields__})))
        recs: List[str] = []
        for r in rails:
            if r.strategy == "BLOCKED":
                continue
            recs.append(f"{r.net}: {r.strategy} ({r.current_a} A, {r.trace_width_mil} mil, drop {r.voltage_drop_mv_worst_path} mV"
                        + (f" = {r.drop_pct}%" if r.drop_pct is not None else "") + f", {r.vias_per_transition} via(s) per transition)")
        for z in zones:
            if z.status != "OK":
                recs.append(f"zone {z.zone_id}: {z.status} ({z.pads_outside} pads outside; {len(z.boundary_violations)} boundary issues)")
        if blocking:
            recs.append(f"{len(blocking)} rail(s) cannot be sized until currents are declared")
        return PowerDistributionReport(rails=rails, ground=ground, zones=zones, blocking_issues=blocking,
                                       plane_nets=sorted({p['net'] for p in self.planes}), recommendations=recs)
