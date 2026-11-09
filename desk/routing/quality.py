"""Subsystem Ten: DRC-First Quality and Acceptance Engine.
Provides baseline-aware DRC diff analysis, distinguishing pre-existing defects
from newly introduced violations and enforcing fail-closed zero-new-violation gates.
Zero external dependencies.
"""
from __future__ import annotations
import hashlib
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class DRCViolationRecord:
    """Normalized DRC violation record with spatial fingerprint."""
    violation_id: str
    category: str  # "SHORT", "CLEARANCE", "WIDTH", "VIA", "UNCONNECTED", "BOARD_EDGE"
    severity: str  # "CRITICAL", "WARNING", "INFO"
    layer: int
    x_mil: float
    y_mil: float
    description: str
    primitives: List[str] = field(default_factory=list)
    nets_involved: List[str] = field(default_factory=list)
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            # Deterministic spatial fingerprint ignoring floating point micro-noise
            prims = ",".join(sorted(self.primitives))
            nets = ",".join(sorted(self.nets_involved))
            key = f"{self.category}:{self.layer}:{round(self.x_mil, 1)}:{round(self.y_mil, 1)}:{prims}:{nets}"
            self.fingerprint = hashlib.sha1(key.encode()).hexdigest()[:12]


@dataclass
class DRCComparisonResult:
    """Outcome of baseline vs post-route DRC evaluation."""
    verdict: str  # "PASSED_CLEAN", "CONDITIONALLY_PASSED_BASELINE_PRESENT", "REJECTED_NEW_VIOLATIONS"
    passed: bool
    baseline_violation_count: int
    post_route_violation_count: int
    resolved_count: int
    newly_introduced_count: int
    pre_existing_unresolved: List[DRCViolationRecord]
    resolved_violations: List[DRCViolationRecord]
    newly_introduced_violations: List[DRCViolationRecord]
    summary: str


class DRCAcceptanceEngine:
    """Enforces fail-closed DRC verification and baseline delta auditing."""

    @classmethod
    def compare_drc(
        cls,
        baseline_violations: List[DRCViolationRecord],
        post_route_violations: List[DRCViolationRecord]
    ) -> DRCComparisonResult:
        """Compares post-route violations against the pre-route baseline."""
        baseline_map = {v.fingerprint: v for v in baseline_violations}
        post_map = {v.fingerprint: v for v in post_route_violations}

        resolved: List[DRCViolationRecord] = []
        for fp, b_viol in baseline_map.items():
            if fp not in post_map:
                resolved.append(b_viol)

        pre_existing: List[DRCViolationRecord] = []
        newly_introduced: List[DRCViolationRecord] = []

        for fp, p_viol in post_map.items():
            if fp in baseline_map:
                pre_existing.append(p_viol)
            else:
                newly_introduced.append(p_viol)

        # Count critical newly introduced violations (shorts, clearances, etc.)
        critical_new = [v for v in newly_introduced if v.severity == "CRITICAL"]

        if len(critical_new) > 0 or len(newly_introduced) > 0:
            verdict = "REJECTED_NEW_VIOLATIONS"
            passed = False
            summary = (
                f"REJECTED: Routing introduced {len(newly_introduced)} new violations "
                f"({len(critical_new)} critical, including {[v.category for v in critical_new]}). "
                f"Resolved: {len(resolved)}, Pre-existing remaining: {len(pre_existing)}."
            )
        elif len(pre_existing) > 0:
            verdict = "CONDITIONALLY_PASSED_BASELINE_PRESENT"
            passed = True  # Passed routing check because 0 new violations were introduced
            summary = (
                f"CONDITIONALLY PASSED: Zero new violations introduced. "
                f"{len(resolved)} baseline issues resolved, but {len(pre_existing)} pre-existing baseline violations remain."
            )
        else:
            verdict = "PASSED_CLEAN"
            passed = True
            summary = f"PASSED: Board has 0 violations ({len(resolved)} baseline issues resolved)."

        return DRCComparisonResult(
            verdict=verdict,
            passed=passed,
            baseline_violation_count=len(baseline_violations),
            post_route_violation_count=len(post_route_violations),
            resolved_count=len(resolved),
            newly_introduced_count=len(newly_introduced),
            pre_existing_unresolved=pre_existing,
            resolved_violations=resolved,
            newly_introduced_violations=newly_introduced,
            summary=summary
        )
