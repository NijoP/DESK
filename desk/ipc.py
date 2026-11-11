"""Single source of truth for DESK's electrical sizing rules (roadmap H-10, H-01, H-06).

Every trace-width, clearance, creepage and via-current number used anywhere in DESK
must come from this module so that one constant lives in one place and is pinned by
`tests/test_ipc_models.py` against published reference values.

Provenance
----------
* Trace ampacity: IPC-2221 (generic standard) power law
      I = k * dT^0.44 * A^0.725      A in mil^2, k = 0.048 external / 0.024 internal.
  IPC-2152 chart data is NOT implemented; the 2221 formula is conservative for
  external layers and known-conservative for internal layers.
* Electrical clearance: IPC-2221B Table 6-1, conductor spacing by voltage, in mm.
  Rows: 0-15, 16-30, 31-50, 51-100, 101-150, 151-170, 171-250, 251-300, 301-500 V,
  then a per-volt increment above 500 V.
      B1 internal conductors                      B2 external, uncoated, sea level to 3050 m
      B3 external, uncoated, above 3050 m         B4 external, with permanent polymer coating
      A5 external, component leads, uncoated      A6 external, component leads, with coating
      A7 external, component leads, conformal coat
* Creepage: IEC 60664-1 Table F.4 (functional insulation, printed wiring material,
  pollution degree 1 and 2, material groups I, II, IIIa/IIIb), in mm.
* Via ampacity: IPC-2221 formula applied to the plated-wall cross-section
      A_via = pi * (drill + plating) * plating      (mil^2), external k.

VERIFY: the table values below were transcribed from the standards as commonly
published. The Principal Hardware Architect must confirm them against the purchased
standard text before a manufacturing release relies on them (`verified_against_standard`).

Zero external dependencies.
"""
import math
from typing import Dict, List, Optional, Tuple

MIL_PER_MM = 39.37007874
MIL_PER_OZ = 1.37  # copper thickness per ounce (1 oz = 34.8 um = 1.37 mil)

verified_against_standard = False  # flip only after a human check against IPC-2221B / IEC 60664-1 text


# ----------------------------------------------------------------------------- trace ampacity
def trace_area_mil2(current_a: float, is_inner: bool = False, temp_rise_c: float = 10.0) -> float:
    """Required copper cross-section (mil^2) for `current_a` at `temp_rise_c` (IPC-2221)."""
    if current_a <= 0.0:
        raise ValueError("current_a must be > 0 for an ampacity calculation")
    if temp_rise_c <= 0.0:
        raise ValueError("temp_rise_c must be > 0")
    k = 0.024 if is_inner else 0.048
    return (current_a / (k * (temp_rise_c ** 0.44))) ** (1.0 / 0.725)


def trace_width_mil(current_a: float, is_inner: bool = False, copper_oz: float = 1.0,
                    temp_rise_c: float = 10.0, min_width_mil: float = 0.0) -> float:
    """Required trace width (mil). Raises on non-positive current: unknown current is never sized."""
    if copper_oz <= 0.0:
        raise ValueError("copper_oz must be > 0")
    width = trace_area_mil2(current_a, is_inner, temp_rise_c) / (copper_oz * MIL_PER_OZ)
    return round(max(width, min_width_mil), 2)


def trace_current_a(width_mil: float, is_inner: bool = False, copper_oz: float = 1.0,
                    temp_rise_c: float = 10.0) -> float:
    """Inverse: current capacity (A) of a trace of `width_mil`."""
    if width_mil <= 0.0 or copper_oz <= 0.0:
        return 0.0
    k = 0.024 if is_inner else 0.048
    area = width_mil * copper_oz * MIL_PER_OZ
    return round(k * (temp_rise_c ** 0.44) * (area ** 0.725), 3)


# ----------------------------------------------------------------------------- clearance (IPC-2221B Table 6-1)
_CLEARANCE_BANDS_V: List[float] = [15, 30, 50, 100, 150, 170, 250, 300, 500]
_CLEARANCE_MM: Dict[str, Tuple[List[float], float]] = {
    # condition: ([mm for each band], mm per volt above 500 V)
    "B1": ([0.05, 0.05, 0.10, 0.10, 0.20, 0.20, 0.20, 0.20, 0.25], 0.0025),
    "B2": ([0.10, 0.10, 0.60, 0.60, 0.60, 1.25, 1.25, 1.25, 2.50], 0.0050),
    "B3": ([0.10, 0.10, 0.60, 1.50, 3.20, 3.20, 6.40, 12.5, 12.5], 0.0250),
    "B4": ([0.05, 0.05, 0.13, 0.13, 0.40, 0.40, 0.40, 0.80, 0.80], 0.00305),
    "A5": ([0.13, 0.13, 0.13, 0.13, 0.40, 0.40, 0.40, 0.80, 0.80], 0.00305),
    "A6": ([0.13, 0.25, 0.40, 0.50, 0.80, 0.80, 0.80, 0.80, 1.50], 0.00305),
    "A7": ([0.13, 0.13, 0.13, 0.13, 0.40, 0.40, 0.40, 0.80, 0.80], 0.00305),
}
CLEARANCE_CONDITIONS = tuple(_CLEARANCE_MM.keys())


def clearance_mm(voltage_v: float, condition: str = "B2") -> float:
    """Minimum conductor spacing (mm) for a peak working voltage per IPC-2221B Table 6-1."""
    cond = condition.upper()
    if cond not in _CLEARANCE_MM:
        raise ValueError(f"Unknown clearance condition '{condition}'; use one of {CLEARANCE_CONDITIONS}")
    v = abs(float(voltage_v))
    table, per_volt = _CLEARANCE_MM[cond]
    for band_v, mm in zip(_CLEARANCE_BANDS_V, table):
        if v <= band_v:
            return mm
    return round(table[-1] + per_volt * (v - 500.0), 4)


def clearance_mil(voltage_v: float, condition: str = "B2") -> float:
    return round(clearance_mm(voltage_v, condition) * MIL_PER_MM, 2)


# ----------------------------------------------------------------------------- creepage (IEC 60664-1 Table F.4)
_CREEPAGE_V: List[float] = [10, 12.5, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 320, 400, 500, 630, 800, 1000]
_CREEPAGE_MM: Dict[str, List[float]] = {
    # pollution degree 1, any material group
    "PD1": [0.025, 0.025, 0.025, 0.025, 0.025, 0.025, 0.025, 0.025, 0.040, 0.063, 0.100, 0.160, 0.250, 0.400, 0.560, 0.750, 1.0, 1.3, 1.8, 2.4, 3.2],
    # pollution degree 2 by material group
    "PD2-I":   [0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.60, 0.63, 0.67, 0.71, 0.75, 0.80, 1.00, 1.25, 1.60, 2.0, 2.5, 3.2, 4.0, 5.0],
    "PD2-II":  [0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.40, 1.80, 2.20, 2.8, 3.6, 4.5, 5.6, 7.1],
    "PD2-III": [0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 1.20, 1.25, 1.30, 1.40, 1.50, 1.60, 2.00, 2.50, 3.20, 4.0, 5.0, 6.3, 8.0, 10.0],
}


def creepage_mm(voltage_v: float, pollution_degree: int = 2, material_group: str = "III") -> float:
    """Minimum creepage (mm) for functional insulation on printed wiring (IEC 60664-1 Table F.4).
    Voltage is rounded up to the next table row; above 1000 V the caller must consult the standard."""
    v = abs(float(voltage_v))
    if v > 1000.0:
        raise ValueError("creepage above 1000 V RMS is outside the implemented table; consult IEC 60664-1")
    if pollution_degree == 1:
        key = "PD1"
    elif pollution_degree == 2:
        mg = material_group.upper().rstrip("AB")
        if mg not in ("I", "II", "III"):
            raise ValueError("material_group must be I, II, IIIa or IIIb")
        key = f"PD2-{mg}"
    else:
        raise ValueError("pollution degree 3 and 4 are not implemented; consult IEC 60664-1 Table F.4")
    table = _CREEPAGE_MM[key]
    for row_v, mm in zip(_CREEPAGE_V, table):
        if v <= row_v:
            return mm
    return table[-1]


def creepage_mil(voltage_v: float, pollution_degree: int = 2, material_group: str = "III") -> float:
    return round(creepage_mm(voltage_v, pollution_degree, material_group) * MIL_PER_MM, 2)


def required_spacing_mil(voltage_v: float, condition: str = "B2", pollution_degree: Optional[int] = 2,
                         material_group: str = "III", manufacturer_min_mil: float = 0.0) -> float:
    """Spacing a router rule must enforce: max(clearance, creepage if requested, fab minimum)."""
    spacing = clearance_mil(voltage_v, condition)
    if pollution_degree is not None and abs(voltage_v) >= 10.0:
        spacing = max(spacing, creepage_mil(voltage_v, pollution_degree, material_group))
    return round(max(spacing, manufacturer_min_mil), 2)


# ----------------------------------------------------------------------------- vias
def via_wall_area_mil2(drill_mil: float, plating_mil: float = 1.0) -> float:
    """Copper cross-section of a plated via barrel (annulus approximated as pi*(d+t)*t)."""
    if drill_mil <= 0 or plating_mil <= 0:
        raise ValueError("drill_mil and plating_mil must be > 0")
    return math.pi * (drill_mil + plating_mil) * plating_mil


def via_current_a(drill_mil: float, plating_mil: float = 1.0, temp_rise_c: float = 10.0) -> float:
    """Current capacity (A) of one via.

    Uses the IPC-2221 *internal* constant (k = 0.024): the barrel is buried in laminate and
    cannot shed heat like an external trace. With a 12 mil drill and 1 mil (25 um) plating this
    gives about 1.0 A at 10 C rise, matching the common engineering rule of thumb; the external
    constant would claim about 1.9 A, which is optimistic."""
    area = via_wall_area_mil2(drill_mil, plating_mil)
    return round(0.024 * (temp_rise_c ** 0.44) * (area ** 0.725), 3)


def vias_required(current_a: float, drill_mil: float, plating_mil: float = 1.0, temp_rise_c: float = 10.0,
                  derating: float = 0.8) -> int:
    """Number of parallel vias to carry `current_a` with a sharing derating (default 80 %)."""
    if current_a <= 0:
        raise ValueError("current_a must be > 0")
    per_via = via_current_a(drill_mil, plating_mil, temp_rise_c) * derating
    return max(1, math.ceil(current_a / per_via))
