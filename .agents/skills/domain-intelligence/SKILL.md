---
name: domain-intelligence
description: Understand the hardware before designing it - classify client requirements into PCB archetypes, overlays, component families and the deterministic rules DESK will enforce.
triggers:
  - "what kind of board"
  - "requirements"
  - "classify"
  - "archetype"
  - "which rules apply"
  - "new project"
---

# Domain Intelligence Skill

## Purpose
Every design request goes through the Domain Intelligence System (DDIS) first: `desk/domain_intelligence/` plus `library/pcb_domains/` (14 domains, 100 archetypes, 17 overlays, 206 component families, 66 rules, 46 references).

## When to Use
- Any request to design, review or plan a PCB, before part selection, schematic, placement or routing.
- When requirements arrive as prose: extract, classify, list missing information, ask.

## Procedure (model-independent)
1. `python tools/desk.py domains classify "<requirements>"` (or the `classify_requirements` tool). Read: primary, secondary, overlays, families, conflicts, missing information.
2. If status is `REVIEW_REQUIRED` or `UNCLASSIFIED`, stop and ask the Captain the listed questions. Never pick a mains/HV, motor or battery category silently.
3. `python tools/desk.py domains rules <archetype> --overlays a,b` (or the `domain_rules` tool): note which rules are ENFORCED (and by which subsystem), ADVISORY, UNSUPPORTED.
4. Collect declared values (voltage_rails, current_limits_A, chemistry/cells, peak currents, isolation voltage and grade, RF region) and run `python tools/desk.py domains validate requirements.json --project projects/<P>`. A BLOCKED result lists exactly what is missing.
5. Save `compiled.design_profile` as `projects/<P>/design_profile.json`; proceed with the block workflow (`docs/03_BLOCK_WORKFLOW.md`). The existing engines apply the enforced rules; keep the advisory list for the review.
6. In every report state: the domain identified, the archetype and overlays loaded, the enforced rules, the advisory/unsupported rules, and open decisions.

## Hard Rules
- AI reasons, DESK calculates, validators verify, humans approve. Never override `desk.ipc`, `DesignProfile`, pin maps or quality gates with a model-produced number.
- Never treat a board as a generic digital board; never apply RF assumptions to power electronics or low-voltage clearances to mains.
- Never guess component values, pin maps or routing constraints; never claim an UNSUPPORTED rule was enforced.
- No live EasyEDA mutation from this skill; it is read-only.

## Relevant Modules
- `desk/domain_intelligence/api.py` (facade), `classifier.py`, `rule_engine.py`, `rule_composer.py`, `profile_compiler.py`, `provenance.py`, `validation.py`
- `desk/orchestrator/tools_manifest.py` tools `classify_requirements`, `domain_rules`
- Docs: `docs/domain_intelligence/*.md`

## Validation
- `python tools/desk.py domains check`
- `python -m unittest tests.test_domain_taxonomy tests.test_requirement_classifier tests.test_rule_engine tests.test_rule_composition tests.test_profile_compiler tests.test_cross_domain_cases`
