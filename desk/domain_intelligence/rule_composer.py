"""Cross-domain rule composition: scope resolution, de-duplication, precedence and conflict detection.

Precedence: severity (BLOCKING > ERROR > WARNING > ADVISORY), then overlay precedence, then rule id (stable).
Conflicts: two in-scope rules about the same subject (same category, same evaluator, same component-family scope)
sharing a numeric parameter key with different values. Rules about different subjects (USB pair impedance vs RF
line impedance) are not conflicts.
Resolution keeps the stricter value and records the conflict; when strictness cannot be decided the conflict
is marked review_required and BOTH rules stay. A stricter safety requirement is never dropped.
Zero external dependencies.
"""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from desk.domain_intelligence.models import Rule, RuleConflict, Composition
from desk.domain_intelligence.registry import DomainLibrary
from desk.domain_intelligence.rule_engine import in_scope

# numeric parameter keys where "stricter" has a known direction
_SMALLER_IS_STRICTER = ("max_", "polygon_threshold", "plane_threshold", "tolerance", "drop_budget", "stitch_pitch", "via_pitch")
_LARGER_IS_STRICTER = ("min_", "margin", "derating", "temperature_rise", "max_harmonic")


def _strictness(key: str) -> Optional[str]:
    k = key.lower()
    if any(k.startswith(p) or p in k for p in _SMALLER_IS_STRICTER):
        return "smaller"
    if any(k.startswith(p) or p in k for p in _LARGER_IS_STRICTER):
        return "larger"
    return None


def compose(lib: DomainLibrary, archetypes: Iterable[str], overlays: Iterable[str], families: Iterable[str],
            extra_rules: Optional[Iterable[Rule]] = None) -> Composition:
    arch, ov, fam = list(archetypes), list(overlays), list(families)
    prec = {o.overlay_id: o.precedence for o in lib.overlays()}
    sources: Dict[str, List[str]] = {}
    pool: Dict[str, Rule] = {}
    for r in list(lib.rules().values()) + list(extra_rules or []):
        why = in_scope(r, arch, ov, fam)
        if why:
            pool[r.rule_id] = r
            sources.setdefault(r.rule_id, []).append(why)

    def ov_prec(r: Rule) -> int:
        return max([prec.get(o, 0) for o in r.scope.get("overlays", [])] or [0])

    ordered = sorted(pool.values(), key=lambda r: (r.severity_rank, -ov_prec(r), r.rule_id))
    conflicts: List[RuleConflict] = []
    dropped: List[str] = []
    keep: Dict[str, Rule] = {r.rule_id: r for r in ordered}
    by_cat: Dict[Tuple[str, str, str, str], List[Rule]] = {}
    for r in ordered:
        subject = ",".join(sorted(r.scope.get("component_families", []))) or "*"
        for key, val in r.parameters.items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                by_cat.setdefault((r.category, r.evaluation_method, subject, key), []).append(r)
    for (cat, _method, _subject, key), rs in sorted(by_cat.items()):
        if len(rs) < 2:
            continue
        vals = {r.rule_id: r.parameters[key] for r in rs}
        if len(set(vals.values())) < 2:
            continue
        direction = _strictness(key)
        if direction is None:
            conflicts.append(RuleConflict(rule_ids=sorted(vals), parameter=f"{cat}.{key}", values=vals, resolution="review_required",
                                          note="strictness direction unknown; both rules kept"))
            continue
        winner = min(rs, key=lambda r: (r.parameters[key] if direction == "smaller" else -r.parameters[key], r.severity_rank, r.rule_id))
        conflicts.append(RuleConflict(rule_ids=sorted(vals), parameter=f"{cat}.{key}", values=vals,
                                      resolution=f"stricter_kept:{winner.rule_id}", note=f"{direction} value is stricter"))
        for r in rs:
            if r.rule_id != winner.rule_id and r.severity_rank >= winner.severity_rank and r.rule_id in keep:
                # the losing rule is only dropped when it is not more severe than the winner
                del keep[r.rule_id]; dropped.append(r.rule_id)
    rules = [r for r in ordered if r.rule_id in keep]
    return Composition(rules=rules, conflicts=conflicts, dropped=dropped, sources=sources)
