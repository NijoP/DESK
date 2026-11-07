"""Standard Engineering Data Contracts for DESK.
Defines structured, validated representations for component intelligence,
placement intent, mechanical and electrical constraints, routability analysis,
routing plans, DRC violations, and iteration history.
Zero third-party dependencies (pure standard library).
"""
import dataclasses
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Any, Set
import json
import math
import time

@dataclass
class PadGeometry:
    num: str
    name: str = ""
    net: str = ""
    dx_mil: float = 0.0
    dy_mil: float = 0.0
    width_mil: float = 20.0
    height_mil: float = 20.0
    shape: str = "RECT"  # RECT, OVAL, ROUND, POLYGON
    layer: int = 1       # 1=Top, 2=Bottom, 11/12=Multi-layer (THT)
    drill_mil: float = 0.0
    plated: bool = True

@dataclass
class FootprintInvariant:
    ref: str
    footprint_name: str
    pad_count: int
    pad_numbers: List[str] = field(default_factory=list)
    pad_positions: Dict[str, Tuple[float, float]] = field(default_factory=dict) # num -> (dx_mil, dy_mil)
    pad_dimensions: Dict[str, Tuple[float, float]] = field(default_factory=dict) # num -> (w_mil, h_mil)
    pad_pitch_mm: float = 0.0
    pad_shapes: Dict[str, str] = field(default_factory=dict) # num -> shape
    drill_definitions: Dict[str, float] = field(default_factory=dict) # num -> drill_mil
    pin1_pos_mil: Tuple[float, float] = (0.0, 0.0)
    electrical_orientation: float = 0.0 # deg

    def validate_invariance(self, current_pad_count: int, current_pad_numbers: List[str], current_positions: Dict[str, Tuple[float, float]]) -> List[str]:
        """Verify that footprint has not suffered pad loss, renumbering, or pitch distortion."""
        errs = []
        if current_pad_count != self.pad_count:
            errs.append(f"{self.ref}: pad count changed from {self.pad_count} to {current_pad_count}")
        missing_pads = set(self.pad_numbers) - set(current_pad_numbers)
        if missing_pads:
            errs.append(f"{self.ref}: missing required pads: {sorted(missing_pads)}")
        # Check pad relative distances (pitch)
        for num, orig_pos in self.pad_positions.items():
            if num in current_positions:
                cur_pos = current_positions[num]
                # Compare relative delta from origin
                dist = math.hypot(cur_pos[0] - orig_pos[0], cur_pos[1] - orig_pos[1])
                if dist > 0.5:  # more than 0.5 mil internal displacement
                    errs.append(f"{self.ref} pad {num}: internal pad position shifted by {dist:.2f} mil")
        return errs

@dataclass
class ComponentRequirement:
    ref: str
    mpn: str
    value: str = ""
    package: str = ""
    footprint_id: str = ""
    width_mm: float = 0.0
    height_mm: float = 0.0
    thickness_mm: float = 0.0
    pad_count: int = 0
    pads: List[PadGeometry] = field(default_factory=list)
    pad_to_net: Dict[str, str] = field(default_factory=dict) # num -> net
    pin1_position: Tuple[float, float] = (0.0, 0.0)
    polarity: Optional[str] = None  # e.g. "DIODE_A_K", "CAP_POS_NEG", "PIN1"
    drill_count: int = 0
    plated_holes: bool = True
    courtyard_rect_mm: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    height_restriction_mm: Optional[float] = None
    thermal_dissipation_mw: float = 0.0
    mechanical_constraints: List[str] = field(default_factory=list)
    electrical_role: str = "general" # mechanical_anchor, primary_ic, passive, special_electrical
    verified: bool = False
    invariants: Optional[FootprintInvariant] = None

@dataclass
class MechanicalConstraint:
    board_outline_mm: Tuple[float, float] = (50.0, 50.0) # width, height
    origin_mm: Tuple[float, float] = (0.0, 0.0)
    edge_clearance_pad_mm: float = 0.30
    edge_clearance_body_mm: float = 0.00
    mounting_holes: List[Dict[str, Any]] = field(default_factory=list) # [{x, y, drill_mm, standoff_mm, head_mm}]
    enclosure_keepouts: List[Dict[str, Any]] = field(default_factory=list) # [{name, rect_mm, side, allow}]
    height_zones: List[Dict[str, Any]] = field(default_factory=list) # [{name, rect_mm, max_mm, side}]
    connector_rules: Dict[str, Any] = field(default_factory=lambda: {
        "edge_distance_mm": 1.0,
        "front_keepout_mm": 3.0,
        "clearance_mm": 1.0,
        "screwdriver_access_depth_mm": 10.0,
        "screwdriver_cone_deg": 15.0
    })

@dataclass
class ElectricalConstraint:
    net_classes: Dict[str, List[str]] = field(default_factory=dict) # class_name -> [nets]
    diff_pairs: Dict[str, Tuple[str, str]] = field(default_factory=dict) # pair_name -> (P_net, N_net)
    equal_length: Dict[str, List[str]] = field(default_factory=dict) # group_name -> [nets]
    high_current_nets: Dict[str, float] = field(default_factory=dict) # net -> max_current_A
    kelvin_sense_pairs: List[Tuple[str, str]] = field(default_factory=list) # [(sense_p, sense_n)]
    max_decoupling_distance_mm: float = 2.0
    max_esd_distance_mm: float = 3.0
    rf_edge_distance_mm: float = 0.5
    sensor_heat_isolation_mm: float = 7.0

@dataclass
class PlacementIntent:
    ref: str
    target_x_mm: float
    target_y_mm: float
    rotation: float = 0.0
    side: str = "T" # 'T' or 'B'
    reason: str = ""
    anchor_ref: Optional[str] = None
    anchor_pin: Optional[str] = None
    locked: bool = False
    cluster_id: Optional[str] = None

@dataclass
class FunctionalCluster:
    cluster_id: str
    name: str
    electrical_role: str # power_input, power_conversion, main_control, sensor_acquisition, comms, audio, output_driver
    primary_refs: List[str] = field(default_factory=list)
    passive_refs: List[str] = field(default_factory=list)
    power_nets: List[str] = field(default_factory=list)
    ground_strategy: str = "star_to_plane" # star_to_plane, direct_via, isolated_polygon
    external_signals: List[str] = field(default_factory=list)
    bounding_box_mm: Optional[Tuple[float, float, float, float]] = None

@dataclass
class PlacementPlan:
    board_mm: Tuple[float, float]
    origin_mm: Tuple[float, float] = (0.0, 0.0)
    intents: Dict[str, PlacementIntent] = field(default_factory=dict)
    clusters: Dict[str, FunctionalCluster] = field(default_factory=dict)
    rules: Dict[str, Any] = field(default_factory=dict)
    keepouts: List[Dict[str, Any]] = field(default_factory=list)
    height_zones: List[Dict[str, Any]] = field(default_factory=list)
    frozen: bool = False
    snapshot_hash: Optional[str] = None

@dataclass
class PlacementValidationResult:
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    routability_score: float = 1.0 # 0.0 = completely blocked, 1.0 = fully routable
    ratsnest_crossings: int = 0
    estimated_total_wirelength_mm: float = 0.0
    escape_congestion_score: float = 0.0 # 0.0 = clear, 1.0 = severe congestion

@dataclass
class RoutingCorridor:
    corridor_id: str
    start_pt: Tuple[float, float]
    end_pt: Tuple[float, float]
    width_mm: float
    layer: int
    assigned_nets: List[str] = field(default_factory=list)
    capacity_tracks: int = 5

@dataclass
class RoutingConstraint:
    net: str
    min_width_mil: float = 5.0
    clearance_mil: float = 4.02
    target_layer_preference: List[int] = field(default_factory=lambda: [1, 2]) # 1=Top, 2=Bottom, etc.
    diff_pair_partner: Optional[str] = None
    max_vias: int = 4
    priority_tier: int = 6 # 1=GND, 2=Connector, 3=Critical, 4=Control/Sensors, 5=Power, 6=Remaining
    current_capacity_A: float = 0.2

@dataclass
class NetEndpoint:
    ref: str
    pad_num: str
    net: str
    x_mil: float
    y_mil: float
    layer: int
    is_smd: bool = True

@dataclass
class NetConnectivityGraph:
    nets: Dict[str, List[NetEndpoint]] = field(default_factory=dict)
    multi_terminal_trees: Dict[str, List[Tuple[NetEndpoint, NetEndpoint]]] = field(default_factory=dict) # Minimum Spanning Tree segments
    ratsnest_crossings: int = 0
    hpwl_wirelength_mil: float = 0.0
    mst_wirelength_mil: float = 0.0

@dataclass
class RoutingPlan:
    board_stackup: List[str] = field(default_factory=lambda: ["Top", "Bottom"]) # or ["Top", "Inner1_GND", "Inner2_PWR", "Bottom"]
    stage_nets: Dict[int, List[str]] = field(default_factory=dict) # Stage 1-6 -> [net names]
    net_constraints: Dict[str, RoutingConstraint] = field(default_factory=dict)
    via_definitions: Dict[str, Any] = field(default_factory=lambda: {"diameter_mil": 24.0, "drill_mil": 12.0})
    ground_strategy: str = "flood_with_escape_vias"
    routing_corridors: List[RoutingCorridor] = field(default_factory=list)

@dataclass
class RoutingAttempt:
    attempt_id: str
    timestamp: float
    method: str # "native_maze", "freerouting_dsn", "hybrid"
    nets_total: int
    nets_routed: int
    nets_failed: List[str] = field(default_factory=list)
    tracks_added: int = 0
    vias_added: int = 0
    unconnected_pads: int = 0
    execution_time_sec: float = 0.0
    success: bool = False

@dataclass
class DRCViolation:
    violation_id: str
    rule_name: str
    error_type: str
    layer: str
    obj1_type: str = ""
    obj1_id: str = ""
    obj1_net: str = ""
    obj1_suffix: str = ""
    obj2_type: str = ""
    obj2_id: str = ""
    obj2_net: str = ""
    obj2_suffix: str = ""
    min_distance_mil: float = 0.0
    clearance_mil: float = 0.0
    location: Tuple[float, float] = (0.0, 0.0) # mil
    severity: str = "ERROR" # "ERROR", "WARNING"

@dataclass
class RoutingRecoveryPlan:
    iteration: int
    failed_nets: List[str]
    conflicting_tracks_to_ripup: List[str] = field(default_factory=list) # primitive ids
    suggested_layer_shifts: Dict[str, int] = field(default_factory=dict) # net -> target_layer
    inserted_escape_vias: List[Dict[str, Any]] = field(default_factory=list)
    reordered_priority_nets: List[str] = field(default_factory=list)
    rationale: str = ""

@dataclass
class PCBIterationRecord:
    iteration: int
    timestamp: str
    placement_rev: str
    routing_plan_rev: str
    attempt: RoutingAttempt
    drc_violations: List[DRCViolation] = field(default_factory=list)
    violation_count: int = 0
    resolved_violations: int = 0
    new_violations: int = 0
    status: str = "IN_PROGRESS" # "IN_PROGRESS", "CONVERGED", "BLOCKED"

@dataclass
class ManufacturingReadinessReport:
    approved: bool
    project: str
    timestamp: str
    pcb_revision: str
    unconnected_smd_pads: int = 0
    disconnected_tracks: int = 0
    orphan_vias: int = 0
    unconnected_nets: List[str] = field(default_factory=list)
    clearance_violations: int = 0
    short_circuits: int = 0
    footprint_integrity_verified: bool = True
    mechanical_fit_verified: bool = True
    thermal_clearance_verified: bool = True
    summary: str = ""

# Serialization helpers
def serialize_dataclass(obj: Any) -> Any:
    """Recursively convert dataclass instances to JSON-compatible dictionaries."""
    if dataclasses.is_dataclass(obj):
        return {k: serialize_dataclass(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, list):
        return [serialize_dataclass(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: serialize_dataclass(v) for k, v in obj.items()}
    elif isinstance(obj, set):
        return sorted(list(obj))
    return obj
