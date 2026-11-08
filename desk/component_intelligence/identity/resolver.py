"""
Component Identity Resolver and Deduplication Engine.
Performs conservative, deterministic manufacturer normalization, MPN standardization,
and canonical component identity matching.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from desk.component_intelligence.identity.models import (
    CanonicalComponent,
    DatasheetReference,
    IdentityVerificationStatus,
    LifecycleStatus,
)

# Standard manufacturer alias dictionary
MANUFACTURER_ALIASES: Dict[str, str] = {
    "TI": "Texas Instruments",
    "TEXAS INSTRUMENTS": "Texas Instruments",
    "TEXAS INSTRUMENTS INC": "Texas Instruments",
    "TEXAS INSTRUMENTS INCORPORATED": "Texas Instruments",
    "ST": "STMicroelectronics",
    "STM": "STMicroelectronics",
    "STMICRO": "STMicroelectronics",
    "STMICROELECTRONICS": "STMicroelectronics",
    "NXP": "NXP Semiconductors",
    "NXP SEMI": "NXP Semiconductors",
    "NXP SEMICONDUCTORS": "NXP Semiconductors",
    "ADI": "Analog Devices",
    "ANALOG DEVICES": "Analog Devices",
    "LINEAR TECHNOLOGY": "Analog Devices",
    "MAXIM": "Analog Devices",
    "MAXIM INTEGRATED": "Analog Devices",
    "MICROCHIP": "Microchip Technology",
    "MICROCHIP TECHNOLOGY": "Microchip Technology",
    "ATMEL": "Microchip Technology",
    "INFINEON": "Infineon Technologies",
    "INFINEON TECHNOLOGIES": "Infineon Technologies",
    "CYPRESS": "Infineon Technologies",
    "ON SEMI": "onsemi",
    "ONSEMI": "onsemi",
    "ON SEMICONDUCTOR": "onsemi",
    "DIODES": "Diodes Incorporated",
    "DIODES INC": "Diodes Incorporated",
    "DIODES INCORPORATED": "Diodes Incorporated",
    "YAGEO": "Yageo",
    "YAGEO CORP": "Yageo",
    "UNI-ROYAL": "Uni-Royal",
    "UNIROYAL": "Uni-Royal",
    "UNI-ROYAL HOLDING": "Uni-Royal",
    "MURATA": "Murata Manufacturing",
    "MURATA MANUFACTURING": "Murata Manufacturing",
    "TDK": "TDK Corporation",
    "TDK CORP": "TDK Corporation",
    "SAMSUNG": "Samsung Electro-Mechanics",
    "SAMSUNG ELECTRO-MECHANICS": "Samsung Electro-Mechanics",
    "KEMET": "KEMET",
    "VISHAY": "Vishay Intertechnology",
    "VISHAY INTERTECHNOLOGY": "Vishay Intertechnology",
    "ROHM": "ROHM Semiconductor",
    "ROHM SEMICONDUCTOR": "ROHM Semiconductor",
    "PANASONIC": "Panasonic",
    "ESP": "Espressif Systems",
    "ESPRESSIF": "Espressif Systems",
    "ESPRESSIF SYSTEMS": "Espressif Systems",
    "NORDIC": "Nordic Semiconductor",
    "NORDIC SEMICONDUCTOR": "Nordic Semiconductor",
}

# Regex for corporate suffixes
CORPORATE_SUFFIX_REGEX = re.compile(
    r"\b(Inc|Incorporated|LLC|Ltd|Limited|Corp|Corporation|Co|GmbH|AG|SA|Pte|Pvt)\b\.?",
    re.IGNORECASE,
)


class ComponentIdentityResolver:
    """Normalizes manufacturer and MPN attributes and resolves canonical identity."""

    @classmethod
    def normalize_manufacturer(cls, raw_mfr: str) -> str:
        """Normalizes manufacturer string using alias mappings and corporate suffix stripping."""
        if not raw_mfr:
            return "Generic"

        mfr_clean = raw_mfr.strip()
        mfr_upper = mfr_clean.upper()

        if mfr_upper in MANUFACTURER_ALIASES:
            return MANUFACTURER_ALIASES[mfr_upper]

        # Strip corporate suffixes
        cleaned = CORPORATE_SUFFIX_REGEX.sub("", mfr_clean).strip().strip(",.- ")
        cleaned_upper = cleaned.upper()
        if cleaned_upper in MANUFACTURER_ALIASES:
            return MANUFACTURER_ALIASES[cleaned_upper]

        return cleaned if cleaned else mfr_clean

    @classmethod
    def normalize_mpn(cls, raw_mpn: str) -> str:
        """
        Normalizes Manufacturer Part Number for matching.
        Preserves original alphanumerics, hyphens, and slashes while eliminating
        accidental whitespace or invisible formatting characters.
        """
        if not raw_mpn:
            return ""
        # Remove non-breaking spaces, trim
        clean = raw_mpn.replace("\u00a0", " ").strip()
        # Convert em/en dashes to standard hyphens
        clean = clean.replace("—", "-").replace("–", "-")
        # Normalize uppercase
        return clean.upper()

    @classmethod
    def generate_desk_id(cls, norm_mfr: str, norm_mpn: str) -> str:
        """Generates deterministic internal canonical DESK component ID."""
        key = f"{norm_mfr.upper()}:{norm_mpn.upper()}".encode("utf-8")
        h = hashlib.sha256(key).hexdigest()[:16]
        return f"comp_{h}"

    @classmethod
    def resolve(
        cls,
        manufacturer: str,
        mpn: str,
        package: str = "",
        category: str = "",
        description: str = "",
        datasheet_url: Optional[str] = None,
        provenance: str = "manual",
    ) -> CanonicalComponent:
        """Resolves inputs into a structured CanonicalComponent."""
        norm_mfr = cls.normalize_manufacturer(manufacturer)
        norm_mpn = cls.normalize_mpn(mpn)
        desk_id = cls.generate_desk_id(norm_mfr, norm_mpn)

        datasheets = []
        if datasheet_url:
            ds_id = f"ds_{hashlib.sha256(datasheet_url.encode()).hexdigest()[:12]}"
            datasheets.append(DatasheetReference(id=ds_id, url=datasheet_url))

        # Infer category if missing
        final_category = category or cls._infer_category(mpn, description, package)

        return CanonicalComponent(
            desk_id=desk_id,
            manufacturer_name=manufacturer.strip() or "Generic",
            normalized_manufacturer=norm_mfr,
            mpn=mpn.strip(),
            normalized_mpn=norm_mpn,
            category=final_category,
            description=description.strip(),
            package=package.strip().upper(),
            datasheets=datasheets,
            lifecycle_status=LifecycleStatus.UNKNOWN,
            verification_status=IdentityVerificationStatus.PROVISIONAL,
            provenance=provenance,
        )

    @classmethod
    def detect_conflicts(cls, comp_a: CanonicalComponent, comp_b: CanonicalComponent) -> List[str]:
        """Detects discrepancies between two components sharing matching canonical identities."""
        warnings: List[str] = []
        if comp_a.desk_id != comp_b.desk_id:
            warnings.append(f"Identity mismatch: {comp_a.desk_id} vs {comp_b.desk_id}")

        if comp_a.package and comp_b.package and comp_a.package != comp_b.package:
            warnings.append(f"Package conflict: '{comp_a.package}' vs '{comp_b.package}'")

        if comp_a.normalized_manufacturer != comp_b.normalized_manufacturer:
            warnings.append(
                f"Manufacturer divergence: '{comp_a.normalized_manufacturer}' vs '{comp_b.normalized_manufacturer}'"
            )

        return warnings

    @staticmethod
    def _infer_category(mpn: str, desc: str, package: str) -> str:
        """Basic heuristic categorization based on MPN prefix and description."""
        combined = f"{mpn} {desc}".upper()
        if any(w in combined for w in ["BUCK", "STEP-DOWN", "REGULATOR", "LDO", "BOOST", "CONVERTER"]):
            return "Power Management / Voltage Regulators"
        if any(w in combined for w in ["MCU", "MICROCONTROLLER", "CORTEX", "STM32", "ESP32", "ATMEGA"]):
            return "Microcontrollers / Embedded Processors"
        if any(w in combined for w in ["MOSFET", "TRANSISTOR", "N-CH", "P-CH"]):
            return "Discrete Semiconductors / Transistors"
        if any(w in combined for w in ["RESISTOR", "OHM"]) or re.match(r"^R\d+", mpn):
            return "Passive Components / Resistors"
        if any(w in combined for w in ["CAPACITOR", "CERAMIC", "MLCC", "TANTALUM", "UF", "PF", "NF"]):
            return "Passive Components / Capacitors"
        if any(w in combined for w in ["INDUCTOR", "CHOKE", "UH", "MH"]):
            return "Passive Components / Inductors"
        if any(w in combined for w in ["CONNECTOR", "HEADER", "JACK", "PLUG", "USB"]):
            return "Connectors / Interconnects"
        return "Uncategorized Electronic Components"
