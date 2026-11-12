"""Facade for CLI, agents and tools: list, search, show, classify, rules, validate, compact agent context."""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional

from desk.domain_intelligence.classifier import classify as _classify, extract_requirements
from desk.domain_intelligence.models import ClassificationResult
from desk.domain_intelligence.profile_compiler import compile_profile
from desk.domain_intelligence.provenance import rule_provenance
from desk.domain_intelligence.registry import DomainLibrary, get_library
from desk.domain_intelligence.rule_composer import compose
from desk.domain_intelligence.rule_engine import EVALUATORS
from desk.domain_intelligence.validation import validate_library


def list_domains(lib: Optional[DomainLibrary] = None) -> List[Dict[str, Any]]:
    lib = lib or get_library()
    idx = lib.archetype_index()
    return [{"domain_id": d["domain_id"], "name": d["name"], "archetypes": [{"id": a, "name": idx[a]["name"], "maturity": idx[a]["maturity"]} for a in d["archetype_ids"]]}
            for d in lib.domains()]


def search(text: str, lib: Optional[DomainLibrary] = None, limit: int = 10) -> List[Dict[str, Any]]:
    return (lib or get_library()).search(text, limit=limit)


def show(archetype_id: str, lib: Optional[DomainLibrary] = None) -> Dict[str, Any]:
    lib = lib or get_library()
    a = lib.archetype(archetype_id)
    rules = lib.rules()
    d = dict(a.data)
    d["rules"] = [{"rule_id": rid, "name": rules[rid].name, "severity": rules[rid].severity, "mode": rules[rid].mode, "status": rules[rid].status}
                  for rid in a.rule_ids if rid in rules]
    return d


def classify(source: Any, lib: Optional[DomainLibrary] = None) -> ClassificationResult:
    return _classify(source, lib or get_library())


def rules_for(archetype_id: str, overlays: Optional[List[str]] = None, lib: Optional[DomainLibrary] = None) -> Dict[str, Any]:
    lib = lib or get_library()
    a = lib.archetype(archetype_id)
    ov = list(overlays) if overlays is not None else a.overlays
    comp = compose(lib, [archetype_id], ov, a.families)
    refs = lib.references()
    return {"archetype_id": archetype_id, "overlays": ov, "rules": [dict(rule_provenance(r, refs), name=r.name, category=r.category, severity=r.severity,
                                                                         evaluation_method=r.evaluation_method, scope_reason=comp.sources.get(r.rule_id, []))
                                                                    for r in comp.rules],
            "conflicts": [c.__dict__ for c in comp.conflicts], "dropped": comp.dropped}


def validate_requirements(source: Any, project_id: str = "UNBOUND", lib: Optional[DomainLibrary] = None, base_profile: Any = None) -> Dict[str, Any]:
    lib = lib or get_library()
    cls = classify(source, lib)
    cp = compile_profile(cls, project_id=project_id, lib=lib, base_profile=base_profile)
    return {"classification": cls.to_dict(), "compiled": cp.to_dict()}


def validate_library_report(lib: Optional[DomainLibrary] = None) -> Dict[str, Any]:
    lib = lib or get_library()
    problems = validate_library(lib, known_evaluators=set(EVALUATORS))
    t = lib.taxonomy()
    return {"ok": not problems, "problems": problems, "archetypes": len(lib.archetype_ids()), "overlays": len(lib.overlay_ids()),
            "families": t.get("family_count"), "rules": len(lib.rules()), "references": len(lib.references()), "version": lib.version}


def agent_context(archetype_id: str, overlays: Optional[List[str]] = None, budget_chars: int = 2500, lib: Optional[DomainLibrary] = None) -> str:
    """Compact, model-independent text an agent can load instead of the whole library."""
    lib = lib or get_library()
    a = lib.archetype(archetype_id)
    d = a.data
    ov = list(overlays) if overlays is not None else a.overlays
    comp = compose(lib, [archetype_id], ov, a.families)
    lines = [f"ARCHETYPE {a.archetype_id} ({a.name}; domain {a.domain}; maturity {a.maturity})",
             f"PURPOSE: {d.get('description', '')}",
             "RULE: never guess currents, voltages, pin maps or part values; declare them in design_profile.json or ask.",
             f"OVERLAYS: {', '.join(ov) or 'none'}",
             f"REQUIRED ROLES: {', '.join(a.required_roles)}",
             "CRITICAL CONSTRAINTS:"] + [f"- {x}" for x in d.get("critical_electrical_constraints", [])] + \
            ["UNSUPPORTED / DANGEROUS:"] + [f"- {x}" for x in d.get("unsupported_conditions", [])] + \
            ["ENFORCED RULES (DESK applies these):"] + [f"- {r.rule_id} {r.name} [{r.subsystem}]" for r in comp.rules if r.mode == "ENFORCED"] + \
            ["ADVISORY / UNSUPPORTED (review by a human, never claimed enforced):"] + \
            [f"- {r.rule_id} {r.name} [{r.mode}]" for r in comp.rules if r.mode != "ENFORCED"]
    out = "\n".join(lines)
    if len(out) > budget_chars:
        out = out[:budget_chars - 20].rstrip() + "\n... [truncated]"
    return out


def to_json(obj: Any) -> str:
    return json.dumps(obj.to_dict() if hasattr(obj, "to_dict") else obj, indent=1, ensure_ascii=False)
