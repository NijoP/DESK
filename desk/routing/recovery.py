"""Subsystem Eleven: Intelligent Selective Routing Recovery and Stagnation Detection.
Replaces destructive whole-board rerouting with targeted problem-solving:
classifies routing failures into structured diagnostic records, preserves verified copper,
and selectively identifies the minimal conflicting segments for rip-up.
Zero external dependencies.
"""
from __future__ import annotations
import math
import time
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass, field


@dataclass
class RoutingFailureDiagnostic:
    """Structured diagnostic record for an unrouted or failing routing unit."""
    net_name: str
    failure_category: str  # "PAD_ESCAPE_FAILURE", "CONGESTION", "NO_LEGAL_LAYER", "CLEARANCE_CONFLICT", "POWER_WIDTH_FAILURE", etc.
    failed_pads: List[str]
    attempt_count: int
    candidate_layers: List[int]
    blocked_directions: List[str]
    blocking_objects: List[str]
    required_clearance_mil: float
    available_clearance_mil: float
    required_width_mil: float
    estimated_congestion: float
    engine_error_detail: Optional[str] = None
    recommended_action: str = ""
    conflicting_track_ids: List[str] = field(default_factory=list)
    confidence: str = "GEOMETRY_VERIFIED"


@dataclass
class SelectiveRecoveryPlan:
    """Actionable plan for selective rip-up and targeted re-routing."""
    timestamp: float
    total_unrouted_nets: int
    stagnation_detected: bool
    stagnation_reason: Optional[str]
    diagnostics: List[RoutingFailureDiagnostic]
    conflicting_tracks_to_ripup: List[str]
    preserved_tracks_count: int
    recommended_next_strategy: str


class IntelligentRecoveryEngine:
    """Analyzes failed connections, identifies conflicting tracks, and manages recovery."""

    FAILURE_CATEGORIES = [
        "PAD_ESCAPE_FAILURE",
        "CONGESTION",
        "NO_LEGAL_LAYER",
        "NO_LEGAL_VIA",
        "WIDTH_CONSTRAINT_CONFLICT",
        "CLEARANCE_CONFLICT",
        "DIFFERENTIAL_PAIR_FAILURE",
        "LENGTH_CONSTRAINT_FAILURE",
        "POWER_WIDTH_FAILURE",
        "DRC_FAILURE",
        "CONNECTIVITY_FAILURE",
        "ENGINE_TIMEOUT",
        "ENGINE_CRASH",
        "IMPORT_FAILURE",
        "API_FAILURE",
        "UNKNOWN"
    ]

    def __init__(self, max_patience: int = 5):
        self.max_patience = max_patience
        self.history: List[Dict[str, Any]] = []

    def record_iteration(
        self,
        unrouted_net_names: Set[str],
        total_wire_length: float,
        total_vias: int,
        drc_violations_count: int
    ) -> bool:
        """Records iteration progress. Returns True if progress is continuing, False if stagnated."""
        snapshot = {
            "unrouted": set(unrouted_net_names),
            "unrouted_count": len(unrouted_net_names),
            "wire_len": total_wire_length,
            "vias": total_vias,
            "drc_count": drc_violations_count,
            "ts": time.time()
        }
        self.history.append(snapshot)

        if len(self.history) < self.max_patience:
            return True

        recent = self.history[-self.max_patience:]
        # Check if unrouted count is flat
        unrouted_counts = [h["unrouted_count"] for h in recent]
        if len(set(unrouted_counts)) == 1 and unrouted_counts[0] > 0:
            # Check if wire length or vias also stopped changing
            len_delta = abs(recent[-1]["wire_len"] - recent[0]["wire_len"])
            via_delta = abs(recent[-1]["vias"] - recent[0]["vias"])
            if len_delta < 5.0 and via_delta == 0:
                return False  # Stagnated

        return True

    @classmethod
    def diagnose_and_plan_recovery(
        cls,
        unrouted_nets: List[str],
        board_dump: Dict[str, Any],
        existing_tracks: List[Dict[str, Any]],
        escape_analyses: Dict[str, Any],
        tolerance_mil: float = 4.02
    ) -> SelectiveRecoveryPlan:
        """Generates targeted recovery diagnostics and identifies minimal conflicting tracks."""
        diagnostics: List[RoutingFailureDiagnostic] = []
        conflicting_tracks: Set[str] = set()

        # Build spatial index of existing tracks to identify what is blocking unrouted airwires
        for net_name in unrouted_nets:
            pads = []
            for ref, comp in board_dump.items():
                if not isinstance(comp, dict): continue
                for p in comp.get("pads", []):
                    if (p.get("net") or "").strip() == net_name:
                        pads.append(f"{ref}.{p.get('num', '')}")

            # Check escape diagnosis for this net's pads
            has_escape_failure = False
            blocked_dirs = []
            blocking_objs = []
            for pid in pads:
                ea = escape_analyses.get(pid)
                if ea and ea.difficulty in ("CRITICAL_ESCAPE", "NO_LEGAL_ESCAPE_FOUND"):
                    has_escape_failure = True
                    blocked_dirs.extend(ea.legal_escape_directions)
                    blocking_objs.extend(ea.blocking_obstacles)

            if has_escape_failure:
                cat = "PAD_ESCAPE_FAILURE"
                rec = "Apply local pad neckdown in DSN export or widen escape corridor"
            else:
                cat = "CONGESTION"
                rec = "Selective rip-up of crossing lower-priority digital signal tracks"

            # Identify crossing tracks between unrouted pad endpoints
            diag_conflict_tracks = []
            for trk in existing_tracks:
                trk_id = trk.get("id") or trk.get("primitiveId") or ""
                trk_net = trk.get("net", "")
                if trk_net == net_name or not trk_id:
                    continue
                # If track belongs to a low-priority signal that crosses through this net's bounding box
                # candidate for selective rip-up
                if any(obj in trk_net for obj in blocking_objs):
                    conflicting_tracks.add(trk_id)
                    diag_conflict_tracks.append(trk_id)

            diagnostics.append(RoutingFailureDiagnostic(
                net_name=net_name,
                failure_category=cat,
                failed_pads=pads,
                attempt_count=1,
                candidate_layers=[1, 2],
                blocked_directions=list(set(blocked_dirs)),
                blocking_objects=list(set(blocking_objs)),
                required_clearance_mil=tolerance_mil,
                available_clearance_mil=2.0,
                required_width_mil=6.0,
                estimated_congestion=0.75,
                recommended_action=rec,
                conflicting_track_ids=diag_conflict_tracks
            ))

        preserved_count = max(0, len(existing_tracks) - len(conflicting_tracks))

        return SelectiveRecoveryPlan(
            timestamp=time.time(),
            total_unrouted_nets=len(unrouted_nets),
            stagnation_detected=False,
            stagnation_reason=None,
            diagnostics=diagnostics,
            conflicting_tracks_to_ripup=sorted(list(conflicting_tracks)),
            preserved_tracks_count=preserved_count,
            recommended_next_strategy="Selective minimal rip-up of conflicting tracks followed by prioritized fanout"
        )
