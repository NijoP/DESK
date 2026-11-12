"""Evidence states and provenance checks for rules and archetypes.

A rule's evidence state says how far its claim has been checked; the enforcement mode says what DESK does with it.
The two are coupled: nothing is ENFORCED unless it is at least IMPLEMENTED, and nothing is called VERIFIED
unless a human has checked it against the source.
"""
from __future__ import annotations
from typing import Any, Dict, List

from desk.domain_intelligence.models import EVIDENCE_STATES, Rule

RANK = {s: i for i, s in enumerate(EVIDENCE_STATES)}
# States that mean "code exists and ran" (eligible for ENFORCED)
EXECUTABLE_STATES = {"IMPLEMENTED", "OFFLINE_TESTED", "VERIFIED_AGAINST_SOURCE", "LIVE_VERIFIED"}
# Allowed forward transitions (human review gates the ones marked)
TRANSITIONS = {
    "DRAFT": {"ADVISORY", "IMPLEMENTED", "BLOCKED"},
    "ADVISORY": {"IMPLEMENTED", "BLOCKED"},
    "IMPLEMENTED": {"OFFLINE_TESTED", "BLOCKED"},
    "OFFLINE_TESTED": {"VERIFIED_AGAINST_SOURCE", "NEEDS_HARDWARE_VALIDATION", "BLOCKED"},
    "VERIFIED_AGAINST_SOURCE": {"LIVE_VERIFIED", "NEEDS_HARDWARE_VALIDATION", "BLOCKED"},
    "NEEDS_HARDWARE_VALIDATION": {"LIVE_VERIFIED", "BLOCKED"},
    "LIVE_VERIFIED": {"BLOCKED"},
    "BLOCKED": {"DRAFT"},
}
HUMAN_GATED = {"VERIFIED_AGAINST_SOURCE", "LIVE_VERIFIED"}


def can_transition(old: str, new: str, human_approved: bool = False) -> bool:
    if new not in TRANSITIONS.get(old, set()):
        return False
    if new in HUMAN_GATED and not human_approved:
        return False
    return True


def check_rule(rule: Rule, references: Dict[str, Dict[str, Any]], standards_verified: bool = False) -> List[str]:
    """Provenance problems for one rule (empty list = consistent)."""
    p: List[str] = []
    for ref in rule.source_references:
        if ref not in references:
            p.append(f"{rule.rule_id}: reference {ref} not in the registry")
    if rule.mode == "ENFORCED" and rule.status not in EXECUTABLE_STATES:
        p.append(f"{rule.rule_id}: ENFORCED requires an executable evidence state, has {rule.status}")
    if rule.status in ("VERIFIED_AGAINST_SOURCE", "LIVE_VERIFIED") and not standards_verified:
        p.append(f"{rule.rule_id}: claims {rule.status} while desk.ipc.verified_against_standard is False")
    if rule.mode == "UNSUPPORTED" and rule.status not in ("DRAFT", "ADVISORY", "BLOCKED"):
        p.append(f"{rule.rule_id}: UNSUPPORTED rule should be DRAFT/ADVISORY/BLOCKED, has {rule.status}")
    if rule.severity == "BLOCKING" and rule.mode == "UNSUPPORTED":
        p.append(f"{rule.rule_id}: a BLOCKING rule that DESK cannot evaluate must be human_review_required")
    return p


def rule_provenance(rule: Rule, references: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """What a reader needs to trust (or distrust) a rule."""
    refs = [{"id": r, "title": references.get(r, {}).get("title", "?"), "clause_notes": references.get(r, {}).get("clause_notes", "")}
            for r in rule.source_references]
    return {"rule_id": rule.rule_id, "version": rule.version, "status": rule.status, "mode": rule.mode, "subsystem": rule.subsystem,
            "human_review_required": rule.human_review_required, "verification_method": rule.verification_method, "references": refs,
            "rationale": rule.rationale}
