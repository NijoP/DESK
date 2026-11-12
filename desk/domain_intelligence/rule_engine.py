"""Deterministic rule evaluation: scope matching, declarative applicability and a registry of evaluators.

An evaluator is a named deterministic function. Rules name their evaluator; the engine never interprets prose.
Outcomes: PASS, FAIL, NOT_EVALUATED (inputs missing), DEFERRED (the owning DESK subsystem applies it at build/route
time), ADVISORY (no engine), UNSUPPORTED (unknown evaluator). A rule that DESK cannot evaluate is never reported
as enforced. Zero external dependencies.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from desk.domain_intelligence.models import Rule, RuleEvaluation


# ----------------------------------------------------------------------------- conditions
def evaluate_condition(cond: Dict[str, Any], feats: Dict[str, Any]) -> bool:
    fld, op, val = cond.get("field"), cond.get("op"), cond.get("value")
    have = fld in feats and feats[fld] not in (None, "", [], {})
    actual = feats.get(fld)
    if op == "exists":
        return have == bool(val)
    if not have:
        return False
    try:
        if op == "==":
            return actual == val
        if op == "!=":
            return actual != val
        if op in (">", ">=", "<", "<="):
            a = float(actual)
            return {">": a > val, ">=": a >= val, "<": a < val, "<=": a <= val}[op]
        if op == "in":
            return actual in val
        if op == "intersects":
            items = actual if isinstance(actual, (list, tuple, set)) else [actual]
            return bool(set(items) & set(val))
        if op == "between":
            a = float(actual)
            return val[0] <= a <= val[1]
    except (TypeError, ValueError):
        return False
    return False


def applies(applicability: Dict[str, Any], feats: Dict[str, Any]) -> bool:
    """{"all": [...]} and/or {"any": [...]}; empty applicability applies everywhere."""
    if not applicability:
        return True
    ok = True
    if applicability.get("all"):
        ok = all(evaluate_condition(c, feats) for c in applicability["all"])
    if ok and applicability.get("any"):
        ok = any(evaluate_condition(c, feats) for c in applicability["any"])
    return ok


def in_scope(rule: Rule, archetypes: Iterable[str], overlays: Iterable[str], families: Iterable[str]) -> Optional[str]:
    """Return the reason the rule is in scope, or None."""
    s = rule.scope
    arch, ov, fam = set(archetypes), set(overlays), set(families)
    if "*" in s.get("archetypes", []):
        return "global"
    hit = arch & set(s.get("archetypes", []))
    if hit:
        return "archetype:" + ",".join(sorted(hit))
    hit = ov & set(s.get("overlays", []))
    if hit:
        return "overlay:" + ",".join(sorted(hit))
    hit = fam & set(s.get("component_families", []))
    if hit:
        return "family:" + ",".join(sorted(hit))
    return None


# ----------------------------------------------------------------------------- context
@dataclass
class EvalContext:
    features: Dict[str, Any] = field(default_factory=dict)
    profile: Any = None                       # desk.profile.DesignProfile or None
    families_present: Set[str] = field(default_factory=set)
    nets: List[str] = field(default_factory=list)

    def inputs(self) -> Dict[str, Any]:
        d = dict(self.features)
        if self.profile is not None:
            d.setdefault("voltage_rails", dict(getattr(self.profile, "voltage_rails", {})))
            d.setdefault("current_limits_A", dict(getattr(self.profile, "current_limits_A", {})))
        return d


Evaluator = Callable[[Rule, EvalContext], RuleEvaluation]
EVALUATORS: Dict[str, Evaluator] = {}


def _ev(rule: Rule, outcome: str, msg: str, **details: Any) -> RuleEvaluation:
    return RuleEvaluation(rule_id=rule.rule_id, outcome=outcome, severity=rule.severity, mode=rule.mode, subsystem=rule.subsystem, message=msg, details=details)


def evaluator(name: str):
    def deco(fn: Evaluator) -> Evaluator:
        EVALUATORS[name] = fn
        return fn
    return deco


def _missing(rule: Rule, ctx: EvalContext, keys: Iterable[str]) -> List[str]:
    d = ctx.inputs()
    return [k for k in keys if k not in d or d[k] in (None, "", [], {})]


# ----------------------------------------------------------------------------- profile-backed evaluators
@evaluator("desk.ipc.trace_width")
def _trace_width(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    if ctx.profile is None:
        return _ev(rule, "NOT_EVALUATED", "requires a DesignProfile with current_limits_A")
    widths = {}
    for net in sorted(getattr(ctx.profile, "current_limits_A", {})):
        try:
            widths[net] = ctx.profile.derive_trace_width_mil(net, is_inner=False, layer_idx=1)
        except ValueError as e:
            return _ev(rule, "FAIL", str(e))
    return _ev(rule, "PASS", f"{len(widths)} power nets sized from declared currents (IPC-2221, applied by tools/route.py)", widths_mil=widths)


@evaluator("desk.profile.validate_electrical_inputs")
def _validate_inputs(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    if ctx.profile is None:
        return _ev(rule, "NOT_EVALUATED", "requires a DesignProfile")
    nets = sorted(set(ctx.nets) | set(getattr(ctx.profile, "voltage_rails", {})) | set(getattr(ctx.profile, "current_limits_A", {})))
    issues = ctx.profile.validate_electrical_inputs(nets)
    return _ev(rule, "FAIL" if issues else "PASS", "; ".join(issues) if issues else f"{len(nets)} nets declared", issues=issues)


@evaluator("desk.profile.clearance")
def _clearance(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    if ctx.profile is None:
        return _ev(rule, "NOT_EVALUATED", "requires a DesignProfile with voltage_rails")
    cond = rule.parameters.get("condition")
    if cond and getattr(ctx.profile, "clearance_condition", None) != cond:
        return _ev(rule, "FAIL", f"clearance_condition must be {cond} (conformal coating declared), profile has {ctx.profile.clearance_condition}")
    out = {}
    for net in sorted(getattr(ctx.profile, "voltage_rails", {})):
        try:
            out[net] = ctx.profile.derive_clearance_mil(net, "GND")
        except ValueError as e:
            return _ev(rule, "FAIL", str(e))
    return _ev(rule, "PASS", f"clearance derived for {len(out)} rails (IPC-2221B {ctx.profile.clearance_condition}, fabricator floor)", clearance_mil=out)


@evaluator("desk.profile.creepage")
def _creepage(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    from desk import ipc
    d = ctx.inputs()
    # Creepage follows the WORKING voltage across the barrier (IEC 60664-1), not the isolation test voltage.
    v = d.get("working_voltage_v") or (max(d.get("voltage_rails", {}).values()) if d.get("voltage_rails") else None)
    if v is None:
        return _ev(rule, "NOT_EVALUATED", "requires working_voltage_v or declared voltage_rails (isolation test voltage alone does not define creepage)")
    pd = int(d.get("pollution_degree", getattr(ctx.profile, "pollution_degree", rule.parameters.get("pollution_degree_default", 2))))
    mg = str(d.get("material_group", getattr(ctx.profile, "material_group", rule.parameters.get("material_group_default", "III"))))
    try:
        mm = ipc.creepage_mm(float(v), pollution_degree=pd, material_group=mg)
    except Exception as e:
        return _ev(rule, "FAIL", f"creepage not derivable: {e}")
    grade = str(d.get("insulation_grade", "basic")).lower()
    if grade == "reinforced":
        mm *= 2.0
    return _ev(rule, "PASS", f"creepage {mm:.2f} mm for working voltage {v:g} V, PD{pd}, group {mg}, {grade} insulation"
               + (f"; isolation test voltage {d['isolation_voltage_v']:g} V recorded (hipot is a hardware test)" if d.get("isolation_voltage_v") else "")
               + " (table transcription unverified)",
               creepage_mm=round(mm, 3), working_voltage_v=float(v), verified_against_standard=bool(getattr(ipc, "verified_against_standard", False)))


@evaluator("desk.profile.manufacturing_floor")
def _mfg_floor(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    if ctx.profile is None:
        return _ev(rule, "NOT_EVALUATED", "requires a DesignProfile")
    m = ctx.profile.manufacturing
    return _ev(rule, "PASS", f"{m.name}: min width {m.min_trace_width_mil} mil, clearance {m.min_clearance_mil} mil, drill {m.min_drill_mil} mil applied as floors")


@evaluator("desk.ipc.via_current")
def _via(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    from desk import ipc
    d = ctx.inputs()
    cur = d.get("current_limits_A") or {}
    if not cur and d.get("current_a"):
        cur = {"LOAD": d["current_a"]}
    if not cur:
        return _ev(rule, "NOT_EVALUATED", "requires declared currents")
    drill = float(d.get("via_drill_mil", 12.0)); plating_mil = float(d.get("plating_um", rule.parameters.get("plating_um_default", 25.0))) / 25.4
    out = {n: ipc.vias_required(float(a), drill, plating_mil, rule.parameters.get("temperature_rise_c_default", 10.0)) for n, a in sorted(cur.items()) if float(a) >= 1.0}
    return _ev(rule, "PASS", f"parallel vias per net at {drill:g} mil drill: {out} (advisory: the autorouter does not place them)", vias_required=out)


# ----------------------------------------------------------------------------- deterministic rule-specific evaluators
@evaluator("desk.rules.harmonic_check")
def _harmonics(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    fsw, frf = d.get("switching_frequency_hz"), d.get("rf_frequency_hz")
    if not fsw or not frf:
        return _ev(rule, "NOT_EVALUATED", "requires switching_frequency_hz and rf_frequency_hz")
    tol = 0.05
    for n in range(1, int(rule.parameters.get("max_harmonic", 50)) + 1):
        h = n * float(fsw)
        if abs(h - float(frf)) <= tol * float(frf):
            return _ev(rule, "FAIL", f"harmonic {n} of {fsw/1e3:g} kHz ({h/1e6:.3f} MHz) falls within 5 % of {frf/1e6:g} MHz", harmonic=n)
    return _ev(rule, "PASS", f"no harmonic of {fsw/1e3:g} kHz up to n={rule.parameters.get('max_harmonic', 50)} within 5 % of {frf/1e6:g} MHz")


@evaluator("desk.rules.rail_headroom")
def _headroom(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    rating = d.get("regulator_rating_a")
    peak = d.get("tx_peak_a", rule.parameters.get("tx_peak_a_default", 0.5))
    if rating is None:
        return _ev(rule, "NOT_EVALUATED", "requires regulator_rating_a (and tx_peak_a)")
    need = float(peak) * (1 + rule.parameters.get("min_headroom_pct", 20) / 100.0)
    ok = float(rating) >= need
    return _ev(rule, "PASS" if ok else "FAIL", f"regulator {rating} A vs required {need:.2f} A (TX peak {peak} A + headroom)", required_a=round(need, 3))


@evaluator("desk.rules.band_plan")
def _band(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    region, fz = d.get("rf_region"), d.get("rf_frequency_hz")
    if not region or not fz:
        return _ev(rule, "NOT_EVALUATED", "requires rf_region and rf_frequency_hz")
    band = rule.parameters.get("regions", {}).get(str(region).upper())
    if not band:
        return _ev(rule, "FAIL", f"unknown region {region}; known: {sorted(rule.parameters.get('regions', {}))}")
    ok = band[0] <= float(fz) <= band[1]
    return _ev(rule, "PASS" if ok else "FAIL", f"{fz/1e6:g} MHz {'inside' if ok else 'outside'} {region} band {band[0]/1e6:g}-{band[1]/1e6:g} MHz")


@evaluator("desk.rules.inductor_margin")
def _isat(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    iout, isat = d.get("output_current_a"), d.get("inductor_isat_a")
    if iout is None or isat is None:
        return _ev(rule, "NOT_EVALUATED", "requires output_current_a and inductor_isat_a")
    ripple = float(d.get("ripple_ratio", rule.parameters.get("ripple_ratio_default", 0.3)))
    base = float(iout)
    conv = set(d.get("converter", []))
    if "boost" in conv and d.get("input_voltage_v") and d.get("output_voltage_v"):
        base = float(iout) * float(d["output_voltage_v"]) / float(d["input_voltage_v"]) / 0.9
    need = base * (1 + ripple / 2) * (1 + rule.parameters.get("margin_pct", 20) / 100.0)
    ok = float(isat) >= need
    return _ev(rule, "PASS" if ok else "FAIL", f"Isat {isat} A vs required {need:.2f} A (peak {base*(1+ripple/2):.2f} A + margin)", required_isat_a=round(need, 3))


@evaluator("desk.rules.range_within")
def _range(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    fld = rule.parameters.get("field"); val = d.get(fld)
    lo = d.get(rule.parameters.get("min_key", "")); hi = d.get(rule.parameters.get("max_key", ""))
    if val is None or (lo is None and hi is None):
        return _ev(rule, "NOT_EVALUATED", f"requires {fld} and {rule.parameters.get('min_key', '')}/{rule.parameters.get('max_key', '')}")
    ok = (lo is None or float(val) >= float(lo)) and (hi is None or float(val) <= float(hi))
    return _ev(rule, "PASS" if ok else "FAIL", f"{fld}={val} within [{lo}, {hi}]" if ok else f"{fld}={val} outside [{lo}, {hi}]")


@evaluator("desk.rules.charge_voltage")
def _charge_v(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    chem, cells, cv = d.get("chemistry"), d.get("cells"), d.get("charge_voltage_v")
    if not chem or not cells:
        return _ev(rule, "FAIL", "chemistry and cell count must be declared before a charge voltage exists (fail-closed)")
    per = rule.parameters.get("per_cell_v", {}).get(str(chem))
    if per is None:
        return _ev(rule, "FAIL", f"unknown chemistry {chem}; declare per-cell charge voltage from the cell datasheet")
    expected = per * int(cells)
    if cv is None:
        return _ev(rule, "PASS", f"charge voltage derived: {expected:.2f} V ({cells} x {per} V, {chem})", charge_voltage_v=round(expected, 3))
    ok = abs(float(cv) - expected) <= rule.parameters.get("tolerance_v", 0.05) * int(cells)
    return _ev(rule, "PASS" if ok else "FAIL", f"declared {cv} V vs {expected:.2f} V for {cells}x {chem}", charge_voltage_v=round(expected, 3))


@evaluator("desk.rules.family_present")
def _family_present(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    want = set(rule.parameters.get("any_of", []))
    have = set(ctx.families_present) | set(ctx.features.get("component_families_present", []))
    if not have:
        return _ev(rule, "NOT_EVALUATED", f"requires the component family list (any of {sorted(want)})")
    hit = sorted(want & have)
    return _ev(rule, "PASS" if hit else "FAIL", f"present: {hit}" if hit else f"none of {sorted(want)} present", present=hit)


@evaluator("desk.rules.peak_margin")
def _peak(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    peak, rating = d.get("peak_current_a"), d.get("fet_id_rating_a")
    if peak is None:
        return _ev(rule, "FAIL", "peak_current_a must be declared (fail-closed)")
    if rating is None:
        return _ev(rule, "NOT_EVALUATED", "requires fet_id_rating_a")
    need = float(peak) * (1 + rule.parameters.get("margin_pct", 30) / 100.0)
    ok = float(rating) >= need
    return _ev(rule, "PASS" if ok else "FAIL", f"device rating {rating} A vs {need:.2f} A (peak {peak} A + margin)", required_a=round(need, 3))


@evaluator("desk.rules.usbc_cc")
def _usbc(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    d = ctx.inputs()
    role, cc = d.get("usb_role"), d.get("cc_resistors")
    if not role:
        return _ev(rule, "NOT_EVALUATED", "requires usb_role")
    if cc is None:
        return _ev(rule, "NOT_EVALUATED", "requires cc_resistors {CC1: ohms, CC2: ohms, type: pulldown|pullup}")
    typ = str(cc.get("type", "")).lower()
    vals = [cc.get("CC1"), cc.get("CC2")]
    if role == "sink":
        ok = typ == "pulldown" and all(v is not None and abs(float(v) - rule.parameters.get("sink_rd_ohm", 5100)) <= 100 for v in vals)
        return _ev(rule, "PASS" if ok else "FAIL", "sink needs Rd 5.1 k pull-down on CC1 and CC2" if not ok else "Rd 5.1 k on both CC lines")
    if role == "source":
        allowed = set(rule.parameters.get("source_rp_ohm", {}).values())
        ok = typ == "pullup" and all(v is not None and any(abs(float(v) - a) <= a * 0.05 for a in allowed) for v in vals)
        return _ev(rule, "PASS" if ok else "FAIL", "source needs Rp pull-ups (56k/22k/10k) on both CC lines" if not ok else "Rp pull-ups present")
    return _ev(rule, "NOT_EVALUATED", f"role {role} needs a PD controller; evaluate with the controller datasheet")


@evaluator("desk.rules.field_present")
def _fields(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    miss = _missing(rule, ctx, rule.parameters.get("fields", []))
    return _ev(rule, "FAIL" if miss else "PASS", f"missing: {miss}" if miss else "all declared", missing=miss)


# ----------------------------------------------------------------------------- deferred to DESK subsystems
for _name, _sub in {
    "desk.power_distribution.voltage_drop": "power.distribution", "desk.power_distribution.strategy": "power.distribution",
    "desk.placement.decoupling_proximity": "placement", "desk.placement.keepout": "placement", "desk.placement.group_proximity": "placement",
    "desk.routing.priority": "routing", "desk.routing.diff_pair": "routing", "desk.routing.rf_line": "routing", "desk.routing.keepout": "routing",
    "desk.copper.return_path": "copper", "desk.copper.ground_plane": "copper", "desk.copper.zone_clearance": "copper", "desk.copper.connection_rule": "copper",
    "desk.copper.islands": "copper", "desk.copper.zone_boundary": "copper", "desk.copper.edge_setback": "copper", "desk.spec.strap_pins": "quality.gate",
}.items():
    def _make(sub: str):
        def _deferred(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
            return _ev(rule, "DEFERRED", f"applied by the {sub} subsystem when the board exists ({rule.verification_method[:90]})")
        return _deferred
    EVALUATORS[_name] = _make(_sub)


@evaluator("advisory")
def _advisory(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    return _ev(rule, "ADVISORY", "no deterministic evaluator; review item")


def evaluate_rule(rule: Rule, ctx: EvalContext) -> RuleEvaluation:
    if not applies(rule.applicability, ctx.inputs()):
        return _ev(rule, "NOT_EVALUATED", "applicability conditions not met")
    fn = EVALUATORS.get(rule.evaluation_method)
    if fn is None:
        return _ev(rule, "UNSUPPORTED", f"unknown evaluation_method {rule.evaluation_method}")
    try:
        return fn(rule, ctx)
    except Exception as e:  # an evaluator bug must surface, never pass silently
        return _ev(rule, "FAIL", f"evaluator error: {type(e).__name__}: {e}")


def evaluate_rules(rules: Iterable[Rule], ctx: EvalContext) -> List[RuleEvaluation]:
    return [evaluate_rule(r, ctx) for r in sorted(rules, key=lambda r: r.rule_id)]
