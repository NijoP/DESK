# Rule-engine architecture (DDIS M3)

**Code:** `desk/domain_intelligence/` — `registry.py` (indexed, mtime-cached library access), `rule_engine.py` (applicability + evaluators), `rule_composer.py` (scope, precedence, conflicts), `profile_compiler.py` (DesignProfile extension), `provenance.py` (evidence states), `validation.py` (schemas and cross-references), `api.py` (facade).
**Data:** `library/pcb_domains/rule_sets/<domain>.json`, `overlays/*.json`, `archetypes/*.json`, `component_families/families.json`, `references/references.json`, `schemas/*.schema.json`.

## Principle

AI reasons. DESK calculates. Independent validators verify. Humans approve.

The engine never interprets prose. Every rule names a deterministic evaluator; the evaluator is Python in `rule_engine.EVALUATORS`, or the rule is `advisory`. Nothing is reported as enforced unless a DESK subsystem applies it.

## Rule contract

```json
{
  "rule_id": "DCDC-ISAT-120", "name": "...", "version": "1.0.0",
  "domain": "dcdc_power", "category": "electrical",
  "scope": {"archetypes": ["buck_converter"], "overlays": [], "component_families": []},
  "severity": "BLOCKING",
  "applicability": {"all": [{"field": "cells", "op": ">=", "value": 1}], "any": []},
  "required_inputs": ["output_current_a", "inductor_isat_a"],
  "evaluation_method": "desk.rules.inductor_margin",
  "parameters": {"ripple_ratio_default": 0.3, "margin_pct": 20},
  "source_references": ["MFR-DATASHEET"],
  "verification_method": "Deterministic: ... tests/test_rule_engine.py",
  "status": "OFFLINE_TESTED",
  "enforcement": {"subsystem": "quality.gate", "mode": "ENFORCED"},
  "human_review_required": false,
  "rationale": "..."
}
```

| Field | Meaning |
|---|---|
| `scope` | Where the rule is in scope: `"*"` for every board, archetype ids, overlay ids, component-family ids. The composer records why each rule entered scope. |
| `applicability` | Declarative conditions on the normalised requirement features (`==, !=, >, >=, <, <=, in, intersects, between, exists`). Empty = always. |
| `evaluation_method` | Evaluator id. `advisory` means no engine. Unknown ids evaluate to `UNSUPPORTED` and fail library validation. |
| `enforcement.mode` | `ENFORCED` (a DESK subsystem applies it), `ADVISORY` (reported, reviewed by a human), `UNSUPPORTED` (DESK cannot evaluate it yet). |
| `enforcement.subsystem` | `routing.width`, `routing.clearance`, `routing`, `placement`, `copper`, `power.distribution`, `quality.gate`, `none`. |
| `status` | Evidence state, see `EVIDENCE_AND_MATURITY_POLICY.md`. ENFORCED requires IMPLEMENTED or better. |

## Evaluation outcomes

| Outcome | Meaning |
|---|---|
| PASS / FAIL | The deterministic evaluator ran on the supplied inputs. BLOCKING + FAIL blocks the compiled profile. |
| NOT_EVALUATED | Applicability not met, or a required input is missing. Missing inputs on fail-closed rules return FAIL instead (e.g. `BAT-CHEM-130`, `MOTOR-PEAK-140`). |
| DEFERRED | The owning subsystem applies the rule when the board exists (placement refiner, route width/clearance, copper engine). |
| ADVISORY | No engine; review item. |
| UNSUPPORTED | Unknown evaluator (should never appear for a validated library). |

Evaluation order is sorted by rule id, so results are reproducible regardless of composition order.

## Evaluators implemented today

Profile-backed: `desk.ipc.trace_width`, `desk.profile.validate_electrical_inputs`, `desk.profile.clearance`, `desk.profile.creepage` (working voltage, PD, material group, reinforced = 2x), `desk.profile.manufacturing_floor`, `desk.ipc.via_current`.
Rule-specific deterministic checks: `desk.rules.harmonic_check`, `rail_headroom`, `band_plan`, `inductor_margin` (buck vs boost input current), `range_within`, `charge_voltage` (per chemistry, fail-closed), `family_present`, `peak_margin`, `usbc_cc`, `field_present`.
Deferred to subsystems: `desk.power_distribution.*`, `desk.placement.*`, `desk.routing.*`, `desk.copper.*`, `desk.spec.strap_pins`.

## Composition

`compose(lib, archetypes, overlays, families)`:

1. Collect every rule whose scope matches; record the reason per rule.
2. Order by severity, then overlay precedence (mains 100 > galvanic isolation 80 > high current 70 ...), then id.
3. Conflicts: two rules about the same subject (same category, same evaluator, same component-family scope) with the same numeric parameter key and different values. The stricter value wins when the direction is known (`max_*` smaller, `min_*`/`margin` larger); otherwise `review_required` and both rules stay. A rule more severe than the winner is never dropped.
4. Output: ordered rules, conflicts, dropped ids, sources.

## Delivery to subsystems

| Subsystem | How the rule reaches it |
|---|---|
| routing.width / routing.clearance | `DesignProfile.derive_trace_width_mil` / `derive_clearance_mil` already drive `tools/route.py`; the compiled profile is a DesignProfile. |
| placement | keep-outs and proximity live in `placement.json` and `PlacementRefiner`; DDIS reports them as DEFERRED. |
| copper | `CopperPlaneEngine` reads the profile (clearance, edge setback). |
| power.distribution | `PowerDistributionPlanner` strategies. |
| quality.gate | `CompiledDomainProfile.blocking_issues` and `RoutingPlan.blocking_issues` stop `tools/route.py`. |

A rule DESK cannot apply stays ADVISORY or UNSUPPORTED and is listed as such in every report and in the agent context.
