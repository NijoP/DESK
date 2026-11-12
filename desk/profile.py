"""Engineering Design Profile Engine for DESK.
Captures versioned, profile-driven engineering constraints:
- Functional and electrical requirements
- Voltage rails and per-net current limits with explicit confidence (VERIFIED, ESTIMATED, UNKNOWN)
- Actual layer stackup, copper thickness, dielectric thickness, loss tangent, and reference layers
- Switching frequencies, RF lines, and differential pairs
- Thermal constraints and environmental ratings
- Manufacturer design rules, process tolerances, and layer-specific capabilities
- Fine-grained change tracking and domain-specific cache invalidation.

Zero external dependencies (pure Python standard library).
"""
from __future__ import annotations
import os
import json
import math
import hashlib
import re
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field, asdict

MIL = 39.37007874


class CurrentConfidence:
    VERIFIED = "VERIFIED"     # Explicitly declared in current_limits_A, net_class, or datasheet
    ESTIMATED = "ESTIMATED"   # Derived from rail heuristics
    UNKNOWN = "UNKNOWN"       # High-current/power rail with unverified current limits


@dataclass
class LayerStackup:
    index: int
    name: str
    layer_type: str                         # "signal", "plane", "dielectric"
    copper_thickness_oz: float = 1.0        # 1.0 oz ~= 1.37 mil (35 um)
    thickness_mil: float = 1.37
    dielectric_thickness_mil: float = 6.0   # Prepreg / core thickness
    dielectric_er: float = 4.4              # FR-4 default
    loss_tangent: float = 0.02
    reference_layer_idx: Optional[int] = None  # Explicit reference plane for impedance control


@dataclass
class NetClassProfile:
    name: str
    nets: List[str] = field(default_factory=list)
    min_width_mil: float = 5.0
    clearance_mil: float = 4.02
    via_dia_mil: float = 24.0
    via_drill_mil: float = 12.0
    max_current_A: float = 0.2
    target_layers: List[int] = field(default_factory=lambda: [1, 2])


@dataclass
class DiffPairProfile:
    name: str
    pos_net: str
    neg_net: str
    target_impedance_ohms: float = 90.0  # 90 ohm for USB, 100 ohm for PCIe/Ethernet
    tolerance_pct: float = 10.0
    trace_width_mil: float = 5.0
    pair_spacing_mil: float = 5.0
    max_length_diff_mm: float = 0.5
    reference_layer: Optional[int] = None


@dataclass
class RFProfile:
    net: str
    frequency_hz: float = 2.4e9
    target_impedance_ohms: float = 50.0
    topology: str = "coplanar_waveguide"  # "microstrip", "coplanar_waveguide", "stripline"
    trace_width_mil: float = 10.0
    ground_clearance_mil: float = 8.0
    reference_layer: int = 2


@dataclass
class ThermalProfile:
    max_ambient_temp_c: float = 40.0
    max_junction_temp_c: float = 105.0
    max_temperature_rise_c: float = 10.0
    airflow_lfm: float = 0.0


@dataclass
class ManufacturerProfile:
    name: str = "jlcpcb_standard_2layer"
    version: str = "2026.1"
    min_trace_width_mil: float = 5.0
    min_clearance_mil: float = 4.02
    min_drill_mil: float = 12.0
    min_via_annular_ring_mil: float = 5.0
    copper_to_edge_mil: float = 12.0
    max_aspect_ratio: float = 8.0
    impedance_control_available: bool = True
    layer_capabilities: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def get_preset(cls, preset_name: str) -> "ManufacturerProfile":
        norm = preset_name.lower()
        if "4layer" in norm or "4l" in norm:
            return cls(
                name="jlcpcb_standard_4layer",
                version="2026.1",
                min_trace_width_mil=3.5,
                min_clearance_mil=3.5,
                min_drill_mil=8.0,
                min_via_annular_ring_mil=4.0,
                copper_to_edge_mil=10.0,
                max_aspect_ratio=10.0,
                impedance_control_available=True,
            )
        elif "pcbway" in norm:
            return cls(
                name="pcbway_standard",
                version="2026.1",
                min_trace_width_mil=4.0,
                min_clearance_mil=4.0,
                min_drill_mil=8.0,
                min_via_annular_ring_mil=4.5,
                copper_to_edge_mil=10.0,
                max_aspect_ratio=8.0,
            )
        return cls()


@dataclass
class DesignProfile:
    project_id: str
    version: str = "1.0.0"
    board_dimensions_mm: Tuple[float, float] = (50.0, 50.0)
    layer_count: int = 2
    stackup: List[LayerStackup] = field(default_factory=list)
    voltage_rails: Dict[str, float] = field(default_factory=dict)         # net -> voltage (V)
    current_limits_A: Dict[str, float] = field(default_factory=dict)       # net -> max current (A)
    switching_frequencies_hz: Dict[str, float] = field(default_factory=dict)
    net_classes: Dict[str, NetClassProfile] = field(default_factory=dict)
    diff_pairs: Dict[str, DiffPairProfile] = field(default_factory=dict)
    rf_lines: Dict[str, RFProfile] = field(default_factory=dict)
    thermal: ThermalProfile = field(default_factory=ThermalProfile)
    manufacturing: ManufacturerProfile = field(default_factory=ManufacturerProfile)
    critical_nets: List[str] = field(default_factory=list)
    keepouts: List[Dict[str, Any]] = field(default_factory=list)
    approved_exceptions: List[Dict[str, Any]] = field(default_factory=list)
    # Electrical-spacing environment (IPC-2221B Table 6-1 condition and IEC 60664-1 creepage inputs).
    clearance_condition: str = "B2"        # B1 internal, B2 external uncoated, B3 >3050 m, B4 coated, A5-A7 leads
    pollution_degree: int = 2              # 1 or 2 (3/4 not implemented)
    material_group: str = "III"            # CTI group I, II, III (IIIa/IIIb)
    # Fail-closed policy for power nets without a declared current: "fail" raises, "default_1A" sizes at 1 A.
    unknown_current_policy: str = "fail"
    # Spacing model (desk/spacing.py). CREEPAGE_AS_CLEARANCE keeps the historical max(clearance, creepage) router
    # rule; FUNCTIONAL uses the IPC-2221B clearance as the net rule and enforces creepage only across the declared
    # insulation_barriers. Switching to FUNCTIONAL is a Captain decision recorded in the ledger (AGENTS.md A).
    spacing_policy: str = "CREEPAGE_AS_CLEARANCE"
    insulation_barriers: List[Dict[str, Any]] = field(default_factory=list)
    # Domain Intelligence (desk/domain_intelligence): archetype/overlay ids, resolved rule ids and compile status.
    # Optional and informational; engines never read numbers from it. Empty for profiles made before DDIS.
    domain_profile: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    profile_hash: str = ""

    # Net names that imply a hazardous or undeclared high voltage. Such nets must appear in voltage_rails.
    HV_NET_PATTERN = r"(HV|MAINS|AC_|_AC\b|^L\d*$|^N\d*$|LINE|NEUTRAL|230V|240V|110V|120V|400V|VBULK|VDC_?BUS|HVDC)"

    def __post_init__(self):
        if not self.stackup:
            self._init_default_stackup()
        if not self.profile_hash:
            self.profile_hash = self.compute_hash()

    def _init_default_stackup(self):
        """Initialise physical stackup based on layer count."""
        if self.layer_count == 4:
            self.stackup = [
                LayerStackup(1, "Top", "signal", copper_thickness_oz=1.0, thickness_mil=1.37, dielectric_thickness_mil=6.0, reference_layer_idx=2),
                LayerStackup(2, "Inner1_GND", "plane", copper_thickness_oz=1.0, thickness_mil=1.37, dielectric_thickness_mil=40.0, reference_layer_idx=None),
                LayerStackup(3, "Inner2_PWR", "plane", copper_thickness_oz=1.0, thickness_mil=1.37, dielectric_thickness_mil=6.0, reference_layer_idx=None),
                LayerStackup(4, "Bottom", "signal", copper_thickness_oz=1.0, thickness_mil=1.37, dielectric_thickness_mil=6.0, reference_layer_idx=3),
            ]
        else:
            self.stackup = [
                LayerStackup(1, "Top", "signal", copper_thickness_oz=1.0, thickness_mil=1.37, dielectric_thickness_mil=60.0, reference_layer_idx=2),
                LayerStackup(2, "Bottom", "signal", copper_thickness_oz=1.0, thickness_mil=1.37, dielectric_thickness_mil=60.0, reference_layer_idx=1),
            ]

    def compute_hash(self) -> str:
        """Deterministic SHA-1 digest of the electrical and manufacturing properties."""
        d = self.to_dict()
        d.pop("profile_hash", None)
        d.pop("created_at", None)
        raw = json.dumps(d, sort_keys=True)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def rf_nets(self) -> Dict[str, RFProfile]:
        return self.rf_lines

    def get_stackup_layers(self) -> List[str]:
        return [layer.name for layer in sorted(self.stackup, key=lambda l: l.index)]

    def get_net_current_status(self, net: str) -> Tuple[float, str]:
        """Distinguish VERIFIED, ESTIMATED, and UNKNOWN electrical current limits.
        
        Eliminates unsafe silent defaults where high-current power nets inherit signal ratings.
        """
        # 1. Explicit verified current limit in profile
        if net in self.current_limits_A:
            return self.current_limits_A[net], CurrentConfidence.VERIFIED

        # 2. Explicit net class current limit
        for nc in self.net_classes.values():
            if net in nc.nets:
                return nc.max_current_A, CurrentConfidence.VERIFIED

        # 3. Known power / battery / motor net names without explicit limit -> UNKNOWN
        net_u = net.upper()
        is_power_pattern = bool(re.search(r"(VCC|VDD|VBAT|VBUS|VSYS|VIN|VOUT|VDRV|VMOT|VPP|12V|5V|3V3|PWR|MOTOR|COIL|HEATER)", net_u))
        if is_power_pattern:
            return 0.0, CurrentConfidence.UNKNOWN

        # 4. Standard generic signal net -> ESTIMATED 0.2A
        return 0.2, CurrentConfidence.ESTIMATED

    def get_current_for_net(self, net: str, allow_unknown_default: Optional[bool] = None) -> float:
        """Returns current limit for a net.

        Fails closed on UNKNOWN power rails unless the caller passes `allow_unknown_default=True`
        or the profile's `unknown_current_policy` is "default_1A". The 1 A fallback exists only for
        exploratory runs; production sizing must declare every power-rail current (roadmap H-02).
        """
        curr, confidence = self.get_net_current_status(net)
        if confidence == CurrentConfidence.UNKNOWN:
            if allow_unknown_default is None:
                allow_unknown_default = (self.unknown_current_policy == "default_1A")
            if not allow_unknown_default:
                raise ValueError(
                    f"Unsafe electrical assumption: Net '{net}' is a power rail with UNKNOWN current capacity. "
                    f"An explicit current limit in 'current_limits_A' is required."
                )
            return 1.0
        return curr

    def get_net_voltage_status(self, net: str) -> Tuple[Optional[float], str]:
        """(voltage, confidence). GND-like nets are 0 V VERIFIED; declared rails VERIFIED;
        nets matching HV_NET_PATTERN without a declaration are UNKNOWN; others ESTIMATED 3.3 V."""
        if net in self.voltage_rails:
            return float(self.voltage_rails[net]), CurrentConfidence.VERIFIED
        net_u = net.upper()
        if re.search(r"^(GND|AGND|DGND|PGND|VSS|0V)", net_u):
            return 0.0, CurrentConfidence.VERIFIED
        if re.search(self.HV_NET_PATTERN, net_u):
            return None, CurrentConfidence.UNKNOWN
        return 3.3, CurrentConfidence.ESTIMATED

    def validate_electrical_inputs(self, nets: List[str]) -> List[str]:
        """Fail-closed pre-flight: every blocking electrical unknown for the given nets, as messages.
        Empty list means sizing and clearance can be derived safely."""
        issues: List[str] = []
        for net in nets:
            _, c_conf = self.get_net_current_status(net)
            if c_conf == CurrentConfidence.UNKNOWN:
                issues.append(f"{net}: power rail without a declared current; add current_limits_A['{net}']")
            _, v_conf = self.get_net_voltage_status(net)
            if v_conf == CurrentConfidence.UNKNOWN:
                issues.append(f"{net}: high-voltage net without a declared voltage; add voltage_rails['{net}']")
        return issues

    def derive_trace_width_mil(self, net: str, is_inner: bool = False, layer_idx: Optional[int] = None) -> float:
        """Calculate trace width (IPC-2221 power law; see routing/width.py) from profile current, copper weight and temp rise."""
        min_width = self.manufacturing.min_trace_width_mil

        # 1. Check if net is in RF profile
        rf_dict = getattr(self, "rf_lines", {}) or getattr(self, "rf_nets", {})
        if net in rf_dict:
            rf_prof = rf_dict[net]
            return max(rf_prof.trace_width_mil, min_width)

        # 2. Derive physical current capacity (IPC-2221 formula)
        current_A = self.get_current_for_net(net)

        # Determine actual copper thickness from stackup
        layer = None
        if layer_idx is not None and self.stackup:
            for l in self.stackup:
                if l.index == layer_idx:
                    layer = l
                    break

        if layer is not None:
            is_inner = (layer.layer_type in ("inner", "plane") or "inner" in layer.name.lower())
            cu_oz = layer.copper_thickness_oz
        else:
            if is_inner:
                inner_layers = [l for l in self.stackup if l.layer_type in ("inner", "plane") or "inner" in l.name.lower()]
                cu_oz = inner_layers[0].copper_thickness_oz if inner_layers else 0.5
            else:
                cu_oz = self.stackup[0].copper_thickness_oz if self.stackup else 1.0

        from desk import ipc
        delta_T = max(1.0, self.thermal.max_temperature_rise_c)
        if current_A > 0.3:
            ipc_width = ipc.trace_width_mil(current_A, is_inner=is_inner, copper_oz=max(0.1, cu_oz),
                                            temp_rise_c=delta_T)
        else:
            ipc_width = min_width

        # 3. Net class minimum width must NOT compromise current capacity
        net_class_min = 0.0
        for nc in self.net_classes.values():
            if net in nc.nets and nc.min_width_mil > 0:
                net_class_min = max(net_class_min, nc.min_width_mil)

        final_width = max(ipc_width, net_class_min, min_width)
        return round(final_width, 1)

    def spacing_requirement(self, net1: str, net2: str, allow_unknown_voltage: bool = False,
                            pin_field_mm: Optional[float] = None):
        """The separated spacing quantities for a net pair (desk.spacing.SpacingRequirement): functional clearance,
        creepage across a declared barrier (or None), fabricator minimum and the policy that turns them into the
        router rule. Raises ValueError for an undeclared high-voltage net (fail-closed, H-01)."""
        from desk import spacing as SP
        volts = []
        for net in (net1, net2):
            v, conf = self.get_net_voltage_status(net)
            if conf == CurrentConfidence.UNKNOWN:
                if not allow_unknown_voltage:
                    raise ValueError(
                        f"Unsafe electrical assumption: Net '{net}' looks high-voltage but has no entry in "
                        f"'voltage_rails'. Declare its working voltage before deriving clearance.")
                v = 0.0
            volts.append(v)
        return SP.requirement(net1, net2, volts[0], volts[1], self.clearance_condition,
                              self.manufacturing.min_clearance_mil / SP.MIL, SP.parse_policy(self.spacing_policy),
                              SP.parse_barriers(self.insulation_barriers), pin_field_mm=pin_field_mm,
                              pollution_degree=self.pollution_degree, material_group=self.material_group)

    def derive_clearance_mil(self, net1: str, net2: str, allow_unknown_voltage: bool = False) -> float:
        """Electrical spacing between two nets as the router rule under the profile's spacing_policy.

        CREEPAGE_AS_CLEARANCE (default, historical): max(IPC-2221B clearance for the profile's condition,
        IEC 60664-1 creepage for its pollution degree and material group, fabricator minimum).
        FUNCTIONAL: max(IPC-2221B clearance, fabricator minimum), plus creepage only when a declared
        insulation barrier separates the two nets. See desk/spacing.py.

        Raises ValueError when either net looks high-voltage but has no declared voltage, unless
        `allow_unknown_voltage` is set (roadmap H-01, fail-closed)."""
        return self.spacing_requirement(net1, net2, allow_unknown_voltage).router_rule_mil

    def _legacy_derive_clearance_mil(self, net1: str, net2: str, allow_unknown_voltage: bool = False) -> float:
        """The pre-spacing-model computation, kept for the equivalence test (tests/test_reliability_spacing.py)."""
        from desk import ipc
        base = self.manufacturing.min_clearance_mil
        volts = []
        for net in (net1, net2):
            v, conf = self.get_net_voltage_status(net)
            if conf == CurrentConfidence.UNKNOWN:
                if not allow_unknown_voltage:
                    raise ValueError(
                        f"Unsafe electrical assumption: Net '{net}' looks high-voltage but has no entry in "
                        f"'voltage_rails'. Declare its working voltage before deriving clearance.")
                v = 0.0
            volts.append(v)
        v_diff = abs(volts[0] - volts[1])
        return ipc.required_spacing_mil(v_diff, condition=self.clearance_condition,
                                        pollution_degree=self.pollution_degree,
                                        material_group=self.material_group,
                                        manufacturer_min_mil=base)

    def affected_domains(self, changed_keys: Set[str]) -> Set[str]:
        """Identify which engineering mental model domains are invalidated by specific key changes."""
        domains = set()
        if changed_keys & {"voltage_rails", "switching_frequencies_hz"}:
            domains.add("M1")  # Schematic
        if changed_keys & {"board_dimensions_mm", "keepouts", "thermal"}:
            domains.add("M2")  # Placement
        if changed_keys & {"current_limits_A", "diff_pairs", "rf_lines", "stackup", "layer_count"}:
            domains.add("M3")  # Routing
            domains.add("M4")  # Copper / Ground
        if changed_keys & {"manufacturing", "thermal"}:
            domains.add("M5")  # Electrical / Manufacturing
        if changed_keys:
            domains.add("M6")  # Verification (always invalidated if any profile value changes)
        return domains

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "version": self.version,
            "board_dimensions_mm": list(self.board_dimensions_mm),
            "layer_count": self.layer_count,
            "stackup": [asdict(l) for l in self.stackup],
            "voltage_rails": self.voltage_rails,
            "current_limits_A": self.current_limits_A,
            "switching_frequencies_hz": self.switching_frequencies_hz,
            "net_classes": {k: asdict(v) for k, v in self.net_classes.items()},
            "diff_pairs": {k: asdict(v) for k, v in self.diff_pairs.items()},
            "rf_lines": {k: asdict(v) for k, v in self.rf_lines.items()},
            "thermal": asdict(self.thermal),
            "manufacturing": asdict(self.manufacturing),
            "critical_nets": self.critical_nets,
            "keepouts": self.keepouts,
            "approved_exceptions": self.approved_exceptions,
            "clearance_condition": self.clearance_condition,
            "pollution_degree": self.pollution_degree,
            "material_group": self.material_group,
            "unknown_current_policy": self.unknown_current_policy,
            "spacing_policy": self.spacing_policy,
            "insulation_barriers": self.insulation_barriers,
            "domain_profile": self.domain_profile,
            "created_at": self.created_at,
            "profile_hash": self.profile_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignProfile":
        d = dict(data)
        if "stackup" in d:
            d["stackup"] = [LayerStackup(**l) for l in d["stackup"]]
        if "net_classes" in d:
            d["net_classes"] = {k: NetClassProfile(**v) for k, v in d["net_classes"].items()}
        if "diff_pairs" in d:
            d["diff_pairs"] = {k: DiffPairProfile(**v) for k, v in d["diff_pairs"].items()}
        if "rf_lines" in d:
            d["rf_lines"] = {k: RFProfile(**v) for k, v in d["rf_lines"].items()}
        if "thermal" in d and isinstance(d["thermal"], dict):
            d["thermal"] = ThermalProfile(**d["thermal"])
        if "manufacturing" in d and isinstance(d["manufacturing"], dict):
            d["manufacturing"] = ManufacturerProfile(**d["manufacturing"])
        if "board_dimensions_mm" in d:
            d["board_dimensions_mm"] = tuple(d["board_dimensions_mm"])
        return cls(**d)

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        self.profile_hash = self.compute_hash()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "DesignProfile":
        """Load design_profile.json. An unknown key or a wrong type is a DesignProfileInvalid that names the field
        (UPS_1000 F-011: a hand-edited 'name_note' key made the loader fail and the router then sized nothing)."""
        from desk.errors import DesignProfileInvalid
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise DesignProfileInvalid(f"STOP: {filepath} cannot be read as JSON: {e}", path=filepath, category="DESIGN_PROFILE_INVALID")
        try:
            return cls.from_dict(data)
        except TypeError as e:
            import re as _re
            m = _re.search(r"unexpected keyword argument '([^']+)'", str(e))
            key = m.group(1) if m else "?"
            raise DesignProfileInvalid(
                f"STOP: {filepath} has a key the profile schema does not accept: '{key}' ({e}). Remove it (notes belong in "
                f"PROFILE_NOTES.md) or fix its type; the router refuses to size a board from a profile it cannot load.",
                path=filepath, key=key, category="DESIGN_PROFILE_INVALID")
