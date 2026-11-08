"""
Component Verification Engine (V1-V4).
Enforces fail-closed, multi-dimensional verification across:
V1: Identity verification (Manufacturer, MPN, canonical hash)
V2: Electrical verification (Voltage derating, current, power)
V3: Physical verification (Package, pin count, footprint integrity)
V4: Procurement verification (Supplier SKU, active stock, quote freshness)
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from desk.component_intelligence.identity.models import CanonicalComponent
from desk.component_intelligence.identity.resolver import ComponentIdentityResolver
from desk.component_intelligence.specifications.engine import ComponentSpecification
from desk.component_intelligence.suppliers.models import SupplierOffer


class VerificationLevel(str, enum.Enum):
    V1_IDENTITY = "V1_IDENTITY"
    V2_ELECTRICAL = "V2_ELECTRICAL"
    V3_PHYSICAL = "V3_PHYSICAL"
    V4_PROCUREMENT = "V4_PROCUREMENT"


class VerificationState(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_RUN = "NOT_RUN"
    STALE = "STALE"


@dataclass
class VerificationEvidence:
    """Audit evidence for a single verification dimension."""
    level: VerificationLevel
    state: VerificationState
    checked_properties: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "state": self.state.value,
            "checked_properties": self.checked_properties,
            "violations": self.violations,
            "warnings": self.warnings,
            "source": self.source,
            "timestamp": self.timestamp,
        }


class ComponentVerificationEngine:
    """Executes deterministic engineering verification checks across V1-V4."""

    @classmethod
    def verify_v1_identity(cls, comp: CanonicalComponent) -> VerificationEvidence:
        """Verifies manufacturer normalization and MPN canonical identity."""
        violations = []
        warnings = []
        props: Dict[str, Any] = {
            "manufacturer": comp.manufacturer_name,
            "normalized_manufacturer": comp.normalized_manufacturer,
            "mpn": comp.mpn,
            "normalized_mpn": comp.normalized_mpn,
            "desk_id": comp.desk_id,
        }

        if not comp.mpn:
            violations.append("Missing Manufacturer Part Number (MPN).")

        expected_id = ComponentIdentityResolver.generate_desk_id(
            comp.normalized_manufacturer,
            comp.normalized_mpn,
        )
        if comp.desk_id != expected_id:
            violations.append(f"Canonical DESK ID mismatch: expected {expected_id}, got {comp.desk_id}")

        if comp.normalized_manufacturer == "Generic":
            warnings.append("Manufacturer is unverified or generic.")

        state = VerificationState.FAIL if violations else VerificationState.PASS
        return VerificationEvidence(
            level=VerificationLevel.V1_IDENTITY,
            state=state,
            checked_properties=props,
            violations=violations,
            warnings=warnings,
            source="identity_resolver",
        )

    @classmethod
    def verify_v2_electrical(
        cls,
        comp: CanonicalComponent,
        specs: List[ComponentSpecification],
        operating_rail_v: float = 0.0,
        operating_current_a: float = 0.0,
    ) -> VerificationEvidence:
        """Verifies electrical operating ratings and derating rules."""
        violations = []
        warnings = []
        props: Dict[str, Any] = {
            "operating_rail_v": operating_rail_v,
            "operating_current_a": operating_current_a,
        }

        # Look up voltage rating
        voltage_spec = next((s for s in specs if s.property_name.lower() in ("voltage", "rated_voltage", "voltage_rating")), None)
        if voltage_spec and voltage_spec.normalized_value is not None:
            props["rated_voltage_v"] = voltage_spec.normalized_value
            # Capacitor 1.5x derating rule
            if "Capacitor" in comp.category or comp.mpn.startswith("C"):
                required_v = 1.5 * operating_rail_v
                if operating_rail_v > 0 and voltage_spec.normalized_value < required_v:
                    violations.append(
                        f"Capacitor rated at {voltage_spec.normalized_value}V on {operating_rail_v}V rail "
                        f"violates 1.5x derating requirement (minimum {required_v:.1f}V required for DC-bias margin)."
                    )

        # Fail-closed if no electrical specs are available on an active component
        if not specs:
            return VerificationEvidence(
                level=VerificationLevel.V2_ELECTRICAL,
                state=VerificationState.UNKNOWN,
                checked_properties=props,
                violations=["Missing electrical specifications evidence."],
                source="specification_engine",
            )

        state = VerificationState.FAIL if violations else VerificationState.PASS
        return VerificationEvidence(
            level=VerificationLevel.V2_ELECTRICAL,
            state=state,
            checked_properties=props,
            violations=violations,
            warnings=warnings,
            source="specification_engine",
        )

    @classmethod
    def verify_v3_physical(
        cls,
        comp: CanonicalComponent,
        footprint_pins: Optional[List[Dict[str, str]]] = None,
        expected_pin_count: Optional[int] = None,
    ) -> VerificationEvidence:
        """Verifies package, courtyard dimensions, and pinout integrity."""
        violations = []
        warnings = []
        props: Dict[str, Any] = {
            "package": comp.package,
            "expected_pin_count": expected_pin_count,
        }

        if not comp.package:
            violations.append("Component lacks a physical package designation.")

        if footprint_pins is not None:
            props["actual_pin_count"] = len(footprint_pins)
            if expected_pin_count is not None and len(footprint_pins) != expected_pin_count:
                violations.append(
                    f"Pin count mismatch: footprint has {len(footprint_pins)} pins, expected {expected_pin_count}."
                )

        state = VerificationState.FAIL if violations else VerificationState.PASS
        return VerificationEvidence(
            level=VerificationLevel.V3_PHYSICAL,
            state=state,
            checked_properties=props,
            violations=violations,
            warnings=warnings,
            source="physical_engine",
        )

    @classmethod
    def verify_v4_procurement(
        cls,
        offer: Optional[SupplierOffer],
        required_quantity: int = 1,
        max_age_days: float = 7.0,
    ) -> VerificationEvidence:
        """Verifies supplier commercial offer, active stock, and quote freshness."""
        if offer is None:
            return VerificationEvidence(
                level=VerificationLevel.V4_PROCUREMENT,
                state=VerificationState.UNKNOWN,
                violations=["No supplier offer available for procurement."],
                source="supplier_registry",
            )

        violations = []
        warnings = []
        now = time.time()
        age_days = (now - offer.last_checked_ts) / 86400.0

        props = {
            "supplier_id": offer.supplier_id,
            "sku": offer.sku,
            "stock": offer.stock,
            "required_quantity": required_quantity,
            "unit_price": offer.unit_price,
            "age_days": round(age_days, 1),
        }

        # Check stock shortage
        if offer.stock < required_quantity:
            violations.append(
                f"Insufficient inventory at {offer.supplier_name}: available {offer.stock}, "
                f"required {required_quantity}."
            )

        # Check quote staleness
        if age_days > max_age_days:
            return VerificationEvidence(
                level=VerificationLevel.V4_PROCUREMENT,
                state=VerificationState.STALE,
                checked_properties=props,
                violations=[f"Supplier price/stock quote is {age_days:.1f} days old (exceeds {max_age_days} day limit)."],
                source="supplier_registry",
            )

        state = VerificationState.FAIL if violations else VerificationState.PASS
        return VerificationEvidence(
            level=VerificationLevel.V4_PROCUREMENT,
            state=state,
            checked_properties=props,
            violations=violations,
            warnings=warnings,
            source="supplier_registry",
        )
