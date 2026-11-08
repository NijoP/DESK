"""
Component Alternatives and Cross-Reference Engine.
Evaluates pin-compatible, electrical, and package replacements with deterministic margin rules.
Enforces the safety invariant: AI may recommend alternatives, but verification rules decide compatibility.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from desk.component_intelligence.identity.models import CanonicalComponent
from desk.component_intelligence.specifications.engine import ComponentSpecification


class CompatibilityLevel(str, enum.Enum):
    EXACT = "EXACT"
    PIN_COMPATIBLE = "PIN_COMPATIBLE"
    ELECTRICAL_COMPATIBLE = "ELECTRICAL_COMPATIBLE"
    PACKAGE_COMPATIBLE = "PACKAGE_COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class AlternativeEvaluationResult:
    """Report evaluating candidate replacement against the primary design component."""
    target_desk_id: str
    target_mpn: str
    compatibility: CompatibilityLevel
    compatibility_score: float  # 0.0 to 1.0
    violations: List[str] = field(default_factory=list)
    advantages: List[str] = field(default_factory=list)
    notes: str = ""

    def is_acceptable_substitute(self) -> bool:
        return self.compatibility in (CompatibilityLevel.EXACT, CompatibilityLevel.PIN_COMPATIBLE) and not self.violations


class ComponentAlternativesEngine:
    """Compares two canonical components to determine substitution viability."""

    @classmethod
    def evaluate_alternative(
        cls,
        primary: CanonicalComponent,
        primary_specs: List[ComponentSpecification],
        candidate: CanonicalComponent,
        candidate_specs: List[ComponentSpecification],
        primary_pins: Optional[List[Dict[str, str]]] = None,
        candidate_pins: Optional[List[Dict[str, str]]] = None,
    ) -> AlternativeEvaluationResult:
        violations: List[str] = []
        advantages: List[str] = []
        score = 1.0

        # 1. Exact match check
        if primary.desk_id == candidate.desk_id:
            return AlternativeEvaluationResult(
                target_desk_id=candidate.desk_id,
                target_mpn=candidate.mpn,
                compatibility=CompatibilityLevel.EXACT,
                compatibility_score=1.0,
                notes="Exact same canonical component.",
            )

        # 2. Package matching
        same_package = bool(primary.package and candidate.package and primary.package == candidate.package)
        if not same_package:
            violations.append(f"Package mismatch: '{primary.package}' vs candidate '{candidate.package}'.")
            score -= 0.4

        # 3. Pin count & pinout matching
        if primary_pins and candidate_pins:
            if len(primary_pins) != len(candidate_pins):
                violations.append(
                    f"Pin count differs: primary has {len(primary_pins)} pins, candidate has {len(candidate_pins)}."
                )
                score -= 0.5
            else:
                # Compare pin names
                mismatched_pins = []
                for p_pin, c_pin in zip(primary_pins, candidate_pins):
                    if p_pin.get("name", "").upper() != c_pin.get("name", "").upper():
                        mismatched_pins.append(f"Pin {p_pin.get('num')}: {p_pin.get('name')} vs {c_pin.get('name')}")
                if mismatched_pins:
                    violations.append(f"Pinout discrepancy on pins: {', '.join(mismatched_pins[:4])}")
                    score -= 0.3

        # 4. Electrical ratings comparison
        p_volt = next((s.normalized_value for s in primary_specs if "VOLTAGE" in s.property_name.upper() and s.normalized_value), None)
        c_volt = next((s.normalized_value for s in candidate_specs if "VOLTAGE" in s.property_name.upper() and s.normalized_value), None)
        if p_volt and c_volt:
            if c_volt < p_volt:
                violations.append(f"Lower voltage rating: candidate has {c_volt}V vs primary {p_volt}V.")
                score -= 0.3
            elif c_volt > p_volt:
                advantages.append(f"Higher voltage margin: candidate has {c_volt}V vs primary {p_volt}V.")

        p_curr = next((s.normalized_value for s in primary_specs if "CURRENT" in s.property_name.upper() and s.normalized_value), None)
        c_curr = next((s.normalized_value for s in candidate_specs if "CURRENT" in s.property_name.upper() and s.normalized_value), None)
        if p_curr and c_curr:
            if c_curr < p_curr:
                violations.append(f"Lower current rating: candidate has {c_curr}A vs primary {p_curr}A.")
                score -= 0.3
            elif c_curr > p_curr:
                advantages.append(f"Higher current capacity: candidate has {c_curr}A vs primary {p_curr}A.")

        # Determine level
        if violations:
            compat = CompatibilityLevel.INCOMPATIBLE if score < 0.5 else CompatibilityLevel.ELECTRICAL_COMPATIBLE
        elif same_package:
            compat = CompatibilityLevel.PIN_COMPATIBLE
        else:
            compat = CompatibilityLevel.ELECTRICAL_COMPATIBLE

        final_score = max(0.0, round(score, 2))
        return AlternativeEvaluationResult(
            target_desk_id=candidate.desk_id,
            target_mpn=candidate.mpn,
            compatibility=compat,
            compatibility_score=final_score,
            violations=violations,
            advantages=advantages,
            notes=f"Evaluated compatibility score: {final_score:.2f}",
        )
