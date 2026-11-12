"""Schema and cross-reference validation of the domain library (stdlib only; no jsonschema dependency).

Schemas under library/pcb_domains/schemas/*.schema.json list required keys with a coarse type and enums.
"""
from __future__ import annotations
from collections import Counter
from typing import Any, Dict, List

from desk.domain_intelligence.models import EVIDENCE_STATES, ENFORCEMENT_MODES
from desk.domain_intelligence.registry import DomainLibrary

_TYPES = {"string": str, "list": list, "dict": dict, "bool": bool, "number": (int, float)}

ALLOCATION = {"embedded_mcu": 10, "rf_wireless": 10, "dcdc_power": 10, "ac_mains_hv": 8, "battery_bms": 8, "motor_control": 8,
              "analog_sensors": 8, "high_speed_digital": 8, "interfaces_comms": 8, "audio_video": 5, "industrial_control": 5,
              "led_display": 5, "test_debug": 5, "automotive": 2}


def _get(obj: Dict[str, Any], dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def validate_document(doc: Dict[str, Any], schema: Dict[str, Any], label: str) -> List[str]:
    problems: List[str] = []
    for key, typ in schema.get("required", {}).items():
        if key not in doc:
            problems.append(f"{label}: missing '{key}'")
            continue
        exp = _TYPES.get(typ)
        if exp and not isinstance(doc[key], exp) or (typ == "number" and isinstance(doc[key], bool)):
            problems.append(f"{label}: '{key}' should be {typ}")
    for dotted, allowed in schema.get("enums", {}).items():
        v = _get(doc, dotted)
        if v is not None and v not in allowed:
            problems.append(f"{label}: '{dotted}'={v!r} not in {allowed}")
    return problems


def validate_library(lib: DomainLibrary, known_evaluators: Any = None) -> List[str]:
    """Return every problem found; an empty list means the library is consistent."""
    p: List[str] = []
    tax = lib.taxonomy()
    ids = lib.archetype_ids()
    if len(ids) != 100:
        p.append(f"taxonomy: {len(ids)} archetypes, expected 100")
    if len(set(ids)) != len(ids):
        p.append("taxonomy: duplicate archetype ids")
    counts = Counter(m["domain"] for m in lib.archetype_index().values())
    for dom, n in ALLOCATION.items():
        if counts.get(dom, 0) != n:
            p.append(f"taxonomy: domain {dom} has {counts.get(dom, 0)} archetypes, expected {n}")
    domain_ids = {d["domain_id"] for d in lib.domains()}
    fams = lib.families()
    overlays = set(lib.overlay_ids())
    refs = lib.references()
    rules = lib.rules()
    sch_a, sch_o, sch_f, sch_r, sch_ref = lib.schema("archetype"), lib.schema("overlay"), lib.schema("component_family"), lib.schema("rule"), lib.schema("reference")

    for a in lib.archetypes():
        d = a.data
        p += validate_document(d, sch_a, f"archetype {a.archetype_id}")
        if d.get("archetype_id") != a.archetype_id:
            p.append(f"archetype {a.archetype_id}: id mismatch in file")
        if a.domain not in domain_ids:
            p.append(f"archetype {a.archetype_id}: unknown domain {a.domain}")
        for f in d.get("typical_component_families", []) + d.get("required_component_roles", []) + d.get("optional_component_roles", []):
            if f not in fams:
                p.append(f"archetype {a.archetype_id}: unknown family {f}")
        for r in d.get("required_component_roles", []):
            if r not in d.get("typical_component_families", []):
                p.append(f"archetype {a.archetype_id}: required role {r} not in typical families")
        for o in d.get("typical_overlays", []):
            if o not in overlays:
                p.append(f"archetype {a.archetype_id}: unknown overlay {o}")
        for s in d.get("applicable_standards", []):
            if s not in refs:
                p.append(f"archetype {a.archetype_id}: unknown reference {s}")
        for rid in d.get("maturity", {}).get("rule_ids", []):
            if rid not in rules:
                p.append(f"archetype {a.archetype_id}: unknown rule {rid}")
        if not d.get("classification", {}).get("keywords"):
            p.append(f"archetype {a.archetype_id}: no classification keywords")
        for key in ("description", "current_power_characteristics"):
            if not str(d.get(key, "")).strip():
                p.append(f"archetype {a.archetype_id}: empty {key}")

    for o in lib.overlays():
        p += validate_document(o.data, sch_o, f"overlay {o.overlay_id}")
        for f in o.families:
            if f not in fams:
                p.append(f"overlay {o.overlay_id}: unknown family {f}")
        for rid in o.data.get("rule_ids", []):
            if rid not in rules:
                p.append(f"overlay {o.overlay_id}: unknown rule {rid}")

    groups = lib.family_groups()
    for fid, f in fams.items():
        p += validate_document(f.data, sch_f, f"family {fid}")
        if f.group not in groups:
            p.append(f"family {fid}: unknown group {f.group}")
        for aid in f.data.get("relevant_archetypes", []):
            if aid not in ids:
                p.append(f"family {fid}: unknown archetype {aid}")

    for rid, r in rules.items():
        p += validate_document(r.to_dict(), sch_r, f"rule {rid}")
        for x in r.scope.get("archetypes", []):
            if x != "*" and x not in ids:
                p.append(f"rule {rid}: unknown archetype in scope {x}")
        for x in r.scope.get("overlays", []):
            if x not in overlays:
                p.append(f"rule {rid}: unknown overlay in scope {x}")
        for x in r.scope.get("component_families", []):
            if x not in fams:
                p.append(f"rule {rid}: unknown family in scope {x}")
        for x in r.source_references:
            if x not in refs:
                p.append(f"rule {rid}: unknown reference {x}")
        if r.status not in EVIDENCE_STATES:
            p.append(f"rule {rid}: bad status {r.status}")
        if r.mode not in ENFORCEMENT_MODES:
            p.append(f"rule {rid}: bad enforcement mode {r.mode}")
        if r.mode == "ENFORCED" and r.status in ("DRAFT", "ADVISORY", "BLOCKED"):
            p.append(f"rule {rid}: ENFORCED but status {r.status}")
        if r.mode == "ENFORCED" and r.evaluation_method == "advisory":
            p.append(f"rule {rid}: ENFORCED without an evaluator")
        if known_evaluators is not None and r.evaluation_method not in known_evaluators and r.evaluation_method != "advisory":
            p.append(f"rule {rid}: unknown evaluation_method {r.evaluation_method}")
        if r.severity == "BLOCKING" and not r.source_references:
            p.append(f"rule {rid}: BLOCKING rule without a source reference")

    for refid, ref in refs.items():
        p += validate_document(ref, sch_ref, f"reference {refid}")
        if ref.get("copyrighted_text_stored"):
            p.append(f"reference {refid}: copyrighted text must not be stored")
    return p
