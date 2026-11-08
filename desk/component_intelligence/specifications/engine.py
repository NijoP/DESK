"""
Component Specification & Unit Normalization Engine.
Extracts and normalizes electrical and physical properties with explicit source provenance.
"""

from __future__ import annotations

import enum
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class ExtractionMethod(str, enum.Enum):
    DATASHEET_EXTRACTED = "DATASHEET_EXTRACTED"
    SUPPLIER_CATALOG = "SUPPLIER_CATALOG"
    AI_EXTRACTED = "AI_EXTRACTED"
    CALCULATED = "CALCULATED"
    ASSUMED = "ASSUMED"


class SpecVerificationState(str, enum.Enum):
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    UNVERIFIED = "UNVERIFIED"
    DISPUTED = "DISPUTED"


@dataclass
class ComponentSpecification:
    """Represents a single typed property with strict unit normalization."""
    property_name: str
    normalized_value: Optional[float]
    unit: str
    original_value: str
    source_ref: str = ""
    extraction_method: ExtractionMethod = ExtractionMethod.SUPPLIER_CATALOG
    verification_state: SpecVerificationState = SpecVerificationState.UNVERIFIED
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_name": self.property_name,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "original_value": self.original_value,
            "source_ref": self.source_ref,
            "extraction_method": self.extraction_method.value,
            "verification_state": self.verification_state.value,
            "timestamp": self.timestamp,
        }


class SpecificationParser:
    """Parses engineering strings into normalized SI values."""

    # SI multipliers
    MULTIPLIERS = {
        "P": 1e-12,
        "N": 1e-9,
        "U": 1e-6,
        "µ": 1e-6,
        "M": 1e-3,  # In resistance/capacitance contexts, lower or upper checked by context
        "K": 1e3,
        "MEG": 1e6,
        "G": 1e9,
    }

    @classmethod
    def parse_capacitance(cls, raw: str) -> Optional[float]:
        """Normalizes capacitance string into Farads (F)."""
        clean = raw.strip().upper().replace("F", "").replace(" ", "")
        m = re.match(r"^(\d+(?:\.\d+)?)\s*([PNUµMK]?)$", clean)
        if not m:
            return None
        val, prefix = float(m.group(1)), m.group(2)
        mult = cls.MULTIPLIERS.get(prefix, 1.0)
        return val * mult

    @classmethod
    def parse_resistance(cls, raw: str) -> Optional[float]:
        """Normalizes resistance string into Ohms (Ω)."""
        clean = raw.strip().upper().replace("OHM", "").replace("Ω", "").replace("R", "").strip()
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(MEG|[KM]?)$", clean)
        if not m:
            return None
        val, prefix = float(m.group(1)), m.group(2)
        mult = 1e6 if prefix == "MEG" else (1e3 if prefix == "K" else (1e-3 if prefix == "M" else 1.0))
        return val * mult

    @classmethod
    def parse_voltage(cls, raw: str) -> Optional[float]:
        """Normalizes voltage string into Volts (V)."""
        clean = raw.strip().upper().replace("V", "").strip()
        m = re.match(r"^(\d+(?:\.\d+)?)$", clean)
        if m:
            return float(m.group(1))
        return None

    @classmethod
    def parse_current(cls, raw: str) -> Optional[float]:
        """Normalizes current string into Amperes (A)."""
        clean = raw.strip().upper().replace("A", "").strip()
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(MA|UA|U|M)?$", clean)
        if not m:
            return None
        val, prefix = float(m.group(1)), m.group(2)
        mult = 1e-3 if "M" in prefix else (1e-6 if "U" in prefix else 1.0)
        return val * mult

    @classmethod
    def parse_power(cls, raw: str) -> Optional[float]:
        """Normalizes power string into Watts (W)."""
        clean = raw.strip()
        # Handle fractional e.g. 1/16, 1/10, 1/4, 1/8
        if "/" in clean:
            frac = clean.upper().replace("W", "").strip()
            parts = frac.split("/")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return float(parts[0]) / float(parts[1])

        m = re.match(r"^(\d+(?:\.\d+)?)\s*(MW|KW|W|mw|kw|w)?$", clean, re.IGNORECASE)
        if not m:
            return None
        val = float(m.group(1))
        unit = (m.group(2) or "").lower()
        if unit in ("mw",):
            return val * 1e-3
        elif unit in ("kw",):
            return val * 1e3
        return val
