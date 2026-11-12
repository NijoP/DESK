"""Known-failure signature registry: measured patterns, their confirmed causes and the recovery that worked.

Entries come from learning/index/KNOWN_FAILURES.md, learning/incidents and the UPS_1000 live test. A signature
matches a FailureRecord by category and a regex over its message / log tails. A match is evidence for the
deterministic diagnosis (desk.reliability.root_cause) and names the recovery kinds the planner may propose.
HYPOTHESIS entries never confirm a root cause on their own.

Zero external dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from desk.reliability.models import Confidence, FailureCategory as C, FailureRecord


@dataclass(frozen=True)
class KnownFailure:
    id: str
    title: str
    categories: Sequence[C]
    pattern: str                         # regex over message + stdout/stderr tails (case-insensitive)
    cause: str
    recovery_kinds: Sequence[str]        # desk.reliability.recovery_planner action kinds that resolved it
    confidence: Confidence
    evidence: Sequence[str]
    prevention: str = ""

    def matches(self, rec: FailureRecord) -> bool:
        if self.categories and rec.category not in self.categories:
            return False
        text = "\n".join([rec.message, rec.stdout_tail or "", rec.stderr_tail or ""])
        return bool(re.search(self.pattern, text, re.I))

    def to_dict(self) -> Dict[str, object]:
        return {"id": self.id, "title": self.title, "categories": [c.value for c in self.categories], "pattern": self.pattern,
                "cause": self.cause, "recovery_kinds": list(self.recovery_kinds), "confidence": self.confidence.value,
                "evidence": list(self.evidence), "prevention": self.prevention}


KNOWN: List[KnownFailure] = [
    KnownFailure("KF-20251111-003", "Window disconnection during long operations", (C.WINDOW_DISCONNECTED, C.WINDOW_ID_ROTATED),
                 r"no longer connected|disconnected|reconnect", "WebSocket timeout after 60-120 s; the gateway reconnects with a NEW window id",
                 ("rebind_session", "verify_identity"), Confidence.CONFIRMED, ("INC-20251111-003", "INC-20261112-013", "UPS_1000 F-002"),
                 "never cache a window id across calls without re-verifying the project uuid"),
    KnownFailure("KF-20261112-008", "Live CLI runs in another project's window", (C.WRONG_PROJECT_CONTEXT,),
                 r"no verified EasyEDA window binding|ACTIVE window|foreign", "an unbound call is executed by the gateway in the ACTIVE window",
                 ("bind_project",), Confidence.CONFIRMED, ("INC-20261112-011", "UPS_1000 F-001"),
                 "mutations refuse to run without a verified binding (desk.bridge.ex)"),
    KnownFailure("KF-20261111-006", "Freerouting 2.1.0 never returns a partial board", (C.EXTERNAL_TOOL_UNSUPPORTED, C.ROUTER_ENGINE_TIMEOUT, C.ROUTER_SES_MISSING),
                 r"ignores max_passes|v2\.1\.|ENGINE_UNBOUNDABLE|ENGINE_IGNORES_LIMITS",
                 "2.1.0 ignores -mp, max_passes and job_timeout; the SES is written only at 100 %; terminate() on Windows loses it",
                 ("switch_engine_version", "use_bundled_jdk"), Confidence.CONFIRMED,
                 ("KF-20261111-006", "INC-20261112-009", "UPS_1000 attempts 5-6"), "engine profile marks 2.1.x unboundable; the chunked runner refuses it"),
    KnownFailure("KF-20261112-ROUTE-CHUNK", "Static routing chunk discards all progress on slow boards", (C.ROUTER_ENGINE_TIMEOUT,),
                 r"CHUNK_TIMEOUT|exceeded timeout budget|TIMEOUT.*no SES|no SES.*TIMEOUT", "chunks of >= 4 passes in 300 s could never finish when a pass took > 75 s; no SES, nothing imported",
                 ("resume_from_checkpoint", "adaptive_chunk"), Confidence.CONFIRMED,
                 ("live-test/ups-1000/ROUTING_BLOCKERS.md", "builder-records/progress_chunks.json"),
                 "chunk size planned from measured pass durations; checkpoint keeps the best valid SES"),
    KnownFailure("KF-20261112-SPACING", "Creepage applied as router clearance on fine-pitch pins", (C.ROUTER_RULE_CONFLICT, C.ROUTER_NO_LEGAL_ESCAPE),
                 r"BLOCKED_BY_CLEARANCE|pin-field gap|engineering decision",
                 "max(IPC clearance, IEC creepage) became the net's DSN class clearance, larger than the pad gap of 1.27 mm-pitch packages",
                 ("engineering_decision",), Confidence.CONFIRMED, ("live-test/ups-1000/ROUTING_BLOCKERS.md", "desk/router.py:491"),
                 "feasibility gate blocks the run and records the decision; spacing_policy is a Captain decision"),
    KnownFailure("KF-20261111-004", "DSN without planes", (C.ROUTER_STAGNATION, C.ROUTER_ENGINE_TIMEOUT),
                 r"no planes declared", "the DSN carries no pours so every GND/power pin is routed as a trace",
                 ("declare_planes",), Confidence.CONFIRMED, ("INC-20261111-007",), "pre-flight ROUTE_PLANES_DECLARED"),
    KnownFailure("KF-20261111-005", "Placement keep-outs exported as router keep-outs", (C.ROUTER_NO_LEGAL_ESCAPE,),
                 r"maze search algorithm could not be created|inside keep-out", "pads inside all-layer keep-outs are unreachable",
                 ("fix_route_keepouts",), Confidence.CONFIRMED, ("INC-20261111-007",), "pre-flight ROUTE_KEEPOUTS_PAD_FREE"),
    KnownFailure("KF-20261111-007", "Board outline must be one closed primitive", (C.ROUTER_ENGINE_CRASH, C.API_SCHEMA_MISMATCH),
                 r"getDsnFile|NO FILE returned|boundary path is missing", "36 line segments make getDsnFile() return undefined",
                 ("fix_outline",), Confidence.CONFIRMED, ("INC-20261111-008",), "OUTLINE_SINGLE_PRIMITIVE"),
    KnownFailure("KF-20261111-IMPORTCHANGES", "importChanges() returns true but only opens a dialog", (C.API_FALSE_SUCCESS,),
                 r"importChanges|pcb_component_count|components", "the Import Changes dialog needs a human Apply; the return value is not completion",
                 ("human_apply_then_readback",), Confidence.CONFIRMED, ("INC-20261111-006", "UPS_1000 F-004"),
                 "API registry marks the method DIALOG; verification contract pin_net_map"),
    KnownFailure("KF-20261112-DELETE", "delete() returns true while primitives survive", (C.API_FALSE_SUCCESS, C.PARTIAL_MUTATION),
                 r"deleted_ids_absent|delete", "33 of 1360 tracks survived a delete that returned true; detaching the net first removed them",
                 ("detach_net_then_delete",), Confidence.CONFIRMED, ("INC-20261112-012",), "verification contract ids_absent"),
    KnownFailure("KF-20261112-007", "Gateway 120 s cap with zombie JavaScript", (C.API_TIMEOUT, C.UNKNOWN_MUTATION_OUTCOME),
                 r"timed out|timeout", "the gateway answers after 120 s but the script keeps running; the outcome is unknown until readback",
                 ("reconcile_readback", "poll_until_stable"), Confidence.CONFIRMED, ("INC-20261112-007",),
                 "never repeat a timed-out mutation; poll the document until stable, then compare"),
    KnownFailure("KF-20261111-PROBE", "Freerouting 2.1.0 --help blocks on its online version check", (C.EXTERNAL_TOOL_UNSUPPORTED,),
                 r"No compatible Freerouting engine|probe timed out", "banner printed in ~2 s, then > 60 s online check",
                 ("select_compatible_engine",), Confidence.CONFIRMED, ("UPS_1000 F-007", "tests/test_freerouting_probe_timeout.py"), ""),
    KnownFailure("KF-20261112-PROFILE", "Hand-edited design_profile.json with unknown keys", (C.DESIGN_PROFILE_INVALID,),
                 r"unexpected keyword argument|does not accept", "free-text keys made DesignProfile.from_dict raise and the router sized nothing",
                 ("escalate",), Confidence.CONFIRMED, ("UPS_1000 F-011",), "DesignProfile.load names the key; notes go to PROFILE_NOTES.md"),
    KnownFailure("KF-20251111-004", "Pour polygon translation", (C.API_FALSE_SUCCESS,),
                 r"complexPolygon|pour.*move", "modify(complexPolygon) does not move pours", ("recreate_pour",), Confidence.PLAUSIBLE,
                 ("INC-20251111-004",), "recreate pours instead of moving them"),
]


def match(rec: FailureRecord) -> List[KnownFailure]:
    return [k for k in KNOWN if k.matches(rec)]


def by_id(kf_id: str) -> Optional[KnownFailure]:
    for k in KNOWN:
        if k.id == kf_id:
            return k
    return None


def register(kf: KnownFailure) -> None:
    """Runtime registration (promoted from incidents by desk.reliability.learning); duplicates by id are replaced."""
    for i, k in enumerate(KNOWN):
        if k.id == kf.id:
            KNOWN[i] = kf
            return
    KNOWN.append(kf)
