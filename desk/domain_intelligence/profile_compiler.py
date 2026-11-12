"""Compile a classification plus requirements into the existing DesignProfile (no second profile system).

The compiler only copies what the requirements declare; it never invents voltages, currents or nets. The
archetype/overlay knowledge lands in DesignProfile.domain_profile (ids, resolved rule ids, status) and in
structural defaults that are safe to suggest (layer count, manufacturer preset, clearance condition for coating).
Rule evaluation runs against the compiled profile; BLOCKING failures make the result BLOCKED.
"""
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional

from desk.domain_intelligence.models import ClassificationResult, CompiledDomainProfile, RuleEvaluation
from desk.domain_intelligence.registry import DomainLibrary, get_library
from desk.domain_intelligence.rule_composer import compose
from desk.domain_intelligence.rule_engine import EvalContext, evaluate_rules

_FOUR_LAYER_OVERLAYS = {"rf_communication", "high_speed_digital", "precision_analog"}


def build_design_profile(project_id: str, classification: ClassificationResult, features: Dict[str, Any], base: Any = None):
    """Return a DesignProfile: `base` (if given) extended, else a new one from declared features only."""
    from desk.profile import DesignProfile, ManufacturerProfile
    kw: Dict[str, Any] = base.to_dict() if base is not None else {"project_id": project_id}
    kw.pop("profile_hash", None)
    if base is None:
        if features.get("voltage_rails"):
            kw["voltage_rails"] = {str(k): float(v) for k, v in features["voltage_rails"].items()}
        if features.get("current_limits_A"):
            kw["current_limits_A"] = {str(k): float(v) for k, v in features["current_limits_A"].items()}
        if features.get("switching_frequency_hz") and features.get("switching_node_net"):
            kw["switching_frequencies_hz"] = {features["switching_node_net"]: float(features["switching_frequency_hz"])}
        if features.get("critical_nets"):
            kw["critical_nets"] = list(features["critical_nets"])
        if features.get("keepouts"):
            kw["keepouts"] = list(features["keepouts"])
        layers = int(features.get("layer_count") or (4 if set(classification.required_overlays) & _FOUR_LAYER_OVERLAYS else 2))
        kw["layer_count"] = layers
        kw["manufacturing"] = ManufacturerProfile.get_preset("jlcpcb_4layer" if layers >= 4 else "jlcpcb_standard_2layer").__dict__.copy()
    if features.get("conformal_coating"):
        kw["clearance_condition"] = "B4"
    elif features.get("clearance_condition"):
        kw["clearance_condition"] = str(features["clearance_condition"])
    if features.get("pollution_degree") in (1, 2):
        kw["pollution_degree"] = int(features["pollution_degree"])
    if features.get("material_group"):
        kw["material_group"] = str(features["material_group"])
    kw["unknown_current_policy"] = "fail"
    prof = DesignProfile.from_dict(kw)
    return prof


def compile_profile(classification: ClassificationResult, project_id: str = "UNBOUND", lib: Optional[DomainLibrary] = None,
                    base_profile: Any = None, families_present: Optional[List[str]] = None, nets: Optional[List[str]] = None) -> CompiledDomainProfile:
    lib = lib or get_library()
    feats = dict(classification.features)
    arch = [a for a in [classification.primary_archetype] + list(classification.secondary_archetypes) if a]
    fam = list(classification.required_component_families)
    comp = compose(lib, arch, classification.required_overlays, fam)
    profile = build_design_profile(project_id, classification, feats, base_profile)
    ctx = EvalContext(features=feats, profile=profile, families_present=set(families_present or feats.get("component_families_present", [])), nets=list(nets or []))
    evals = evaluate_rules(comp.rules, ctx)
    enforced = [r.rule_id for r in comp.rules if r.mode == "ENFORCED"]
    advisory = [r.rule_id for r in comp.rules if r.mode == "ADVISORY"]
    unsupported = [r.rule_id for r in comp.rules if r.mode == "UNSUPPORTED"]
    blocking: List[str] = []
    for e in evals:
        if e.outcome == "FAIL" and e.severity == "BLOCKING":
            blocking.append(f"{e.rule_id}: {e.message}")
    if classification.classification_status == "UNCLASSIFIED":
        blocking.append("CLASSIFICATION: no archetype matched; describe the application, power source and interfaces")
    review = classification.classification_status == "REVIEW_REQUIRED" or bool(classification.conflicts) or any(c.resolution == "review_required" for c in comp.conflicts)
    status = "BLOCKED" if blocking else ("REVIEW_REQUIRED" if review else "READY")
    profile.domain_profile = {
        "primary_archetype": classification.primary_archetype, "secondary_archetypes": list(classification.secondary_archetypes),
        "overlays": list(classification.required_overlays), "component_families": fam, "rule_ids": [r.rule_id for r in comp.rules],
        "enforced_rule_ids": enforced, "advisory_rule_ids": advisory, "unsupported_rule_ids": unsupported,
        "classification_status": classification.classification_status, "confidence": classification.confidence,
        "status": status, "library_version": lib.version, "compiled_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return CompiledDomainProfile(
        project_id=project_id, primary_archetype=classification.primary_archetype, secondary_archetypes=list(classification.secondary_archetypes),
        overlays=list(classification.required_overlays), component_families=fam, rule_ids=[r.rule_id for r in comp.rules],
        enforced_rule_ids=enforced, advisory_rule_ids=advisory, unsupported_rule_ids=unsupported, evaluations=evals, conflicts=comp.conflicts,
        blocking_issues=blocking, missing_information=list(classification.missing_information), design_profile=profile.to_dict(),
        status=status, compiled_at=profile.domain_profile["compiled_at"], library_version=lib.version)
