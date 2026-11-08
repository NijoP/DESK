"""JLCPCB PCBA Catalog Classification and Rotation Correction Engine.

Provides:
1. Classification of parts into 'Basic', 'Preferred', and 'Extended'.
2. SMT assembly eligibility rules.
3. Rotation offset transformations matching JLCPCB tape-and-reel feeder standards.
"""

from __future__ import annotations
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


class PartAssemblyType:
    BASIC = "Basic"
    PREFERRED = "Preferred"
    EXTENDED = "Extended"
    UNSUPPORTED = "Unsupported"


# Standard angle offsets required by JLCPCB SMT feeders per footprint pattern
# Maps footprint substring/regex pattern to correction angle in degrees
ROTATION_OFFSET_TABLE: Dict[str, float] = {
    "SOT-23": 0.0,
    "SOT-23-3": 0.0,
    "SOT-23-5": 0.0,
    "SOT-23-6": 0.0,
    "SOT-223": 180.0,
    "SOIC-8": 0.0,
    "SOIC-16": 0.0,
    "SOP-8": 0.0,
    "SOP-16": 0.0,
    "TSSOP": 0.0,
    "QFN": 0.0,
    "LQFP": 0.0,
    "SOD-123": 180.0,
    "SOD-323": 180.0,
    "SMA": 180.0,
    "SMB": 180.0,
    "SMC": 180.0,
    "0402": 0.0,
    "0603": 0.0,
    "0805": 0.0,
    "1206": 0.0,
    "C_0402": 0.0,
    "C_0603": 0.0,
    "R_0402": 0.0,
    "R_0603": 0.0,
    "LED_0603": 180.0,
    "LED_0805": 180.0,
}


@dataclass
class AssemblyComponentInfo:
    lcsc_part_number: str
    part_type: str  # Basic, Preferred, Extended
    package: str
    is_smt_eligible: bool
    feeder_fee_usd: float
    rotation_offset_deg: float


class JLCPCBPCBACatalog:
    """Manages SMT assembly classifications, fees, and footprint rotation alignments."""

    # Common basic parts readily available in JLCPCB standard feeders without setup cost
    COMMON_BASIC_PREFIXES = (
        "C0402", "C0603", "C0805", "R0402", "R0603", "R0805",
    )

    KNOWN_BASIC_PARTS = {
        "C15849",  # 100nF 0402 50V
        "C14663",  # 10uF 0805 16V
        "C25076",  # 10k 0402 1%
        "C25077",  # 1k 0402 1%
        "C25879",  # 0R 0402 5%
        "C8680",   # 100nF 0603 50V
        "C7298",   # 10k 0603 1%
        "C14877",  # 10uF 0603 10V
        "C2040",   # BSS138 SOT-23
        "C2290",   # 2N7002 SOT-23
        "C347222", # AMS1117-3.3 SOT-223
    }

    @classmethod
    def classify_part(cls, lcsc_pn: str, package: str = "") -> AssemblyComponentInfo:
        """Classify a component into Basic, Preferred, or Extended."""
        norm_pn = lcsc_pn.strip().upper()
        if norm_pn in cls.KNOWN_BASIC_PARTS:
            part_type = PartAssemblyType.BASIC
            fee = 0.0
        elif any(norm_pn.startswith(p) for p in cls.COMMON_BASIC_PREFIXES):
            part_type = PartAssemblyType.BASIC
            fee = 0.0
        else:
            # Default to Extended part ($3.00 feeder fee)
            part_type = PartAssemblyType.EXTENDED
            fee = 3.00

        # Compute rotation offset for package
        offset = cls.get_rotation_offset(package)

        return AssemblyComponentInfo(
            lcsc_part_number=norm_pn,
            part_type=part_type,
            package=package,
            is_smt_eligible=True,
            feeder_fee_usd=fee,
            rotation_offset_deg=offset,
        )

    @classmethod
    def get_rotation_offset(cls, package: str) -> float:
        """Calculate rotation correction angle for CAD to JLCPCB pick-and-place orientation."""
        if not package:
            return 0.0
        pkg_upper = package.upper()
        for pat, offset in ROTATION_OFFSET_TABLE.items():
            if pat.upper() in pkg_upper:
                return offset
        return 0.0

    @classmethod
    def normalize_rotation(cls, cad_rotation: float, package: str) -> float:
        """Normalize CAD rotation angle to JLCPCB SMT coordinate system (0 to 360)."""
        offset = cls.get_rotation_offset(package)
        total = (cad_rotation + offset) % 360.0
        if total < 0:
            total += 360.0
        return round(total, 2)
