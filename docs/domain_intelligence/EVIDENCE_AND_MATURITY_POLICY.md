# Evidence and maturity policy

Every archetype and every rule carries an evidence state. The state says how far the claim has been checked; it never says the claim is true.

| State | Meaning | Who can set it |
|---|---|---|
| DRAFT | Written, not exercised | anyone |
| ADVISORY | Deliberately a review item; no deterministic evaluator | anyone |
| IMPLEMENTED | An evaluator or subsystem applies it; no test proves it | engineer |
| OFFLINE_TESTED | Exercised by the unit/fixture tests in `tests/` | engineer, with the test named in `verification_method` |
| VERIFIED_AGAINST_SOURCE | A human compared the values with the cited standard/datasheet text | human reviewer only |
| LIVE_VERIFIED | Confirmed on a real board or live ECAD run | human reviewer only |
| NEEDS_HARDWARE_VALIDATION | Offline evidence exists; a hardware test is required before trust | engineer |
| BLOCKED | Known wrong or unsafe; must not be applied | anyone |

Transitions (`desk/domain_intelligence/provenance.py`): DRAFT → ADVISORY/IMPLEMENTED/BLOCKED; IMPLEMENTED → OFFLINE_TESTED; OFFLINE_TESTED → VERIFIED_AGAINST_SOURCE (human) / NEEDS_HARDWARE_VALIDATION; VERIFIED → LIVE_VERIFIED (human); anything → BLOCKED; BLOCKED → DRAFT.

## Coupling to enforcement

* `ENFORCED` requires IMPLEMENTED, OFFLINE_TESTED, VERIFIED_AGAINST_SOURCE or LIVE_VERIFIED, and a real evaluator.
* `UNSUPPORTED` rules stay DRAFT/ADVISORY/BLOCKED; a BLOCKING rule DESK cannot evaluate must be `human_review_required`.
* Nothing in the library may claim VERIFIED_AGAINST_SOURCE while `desk/ipc.py` `verified_against_standard` is False (`tests/test_rule_provenance.py`).

## Standards and references

`library/pcb_domains/references/references.json` stores identifiers, titles, organisations, clause notes and the derived values DESK uses. No copyrighted standard text is stored (`copyrighted_text_stored: false` is validated). IPC-2221B and IEC 60664-1 table values live in `desk/ipc.py` as transcriptions marked unverified; the human check that flips `verified_against_standard` is roadmap item QA-05.

## Fail-closed inputs

Rules whose safety depends on an input return FAIL, not NOT_EVALUATED, when the input is missing: charge voltage without chemistry (`BAT-CHEM-130`), peak current for a motor stage (`MOTOR-PEAK-140`), insulation grade for a barrier (`MAINS-INS-163`), undeclared mains nets (`MAINS-DECL-160` via `DesignProfile.validate_electrical_inputs`). A BLOCKING failure sets the compiled profile to BLOCKED and `tools/route.py` stops.

## Current library status (2026-11-12)

66 rules: 39 ENFORCED (OFFLINE_TESTED or IMPLEMENTED), 25 ADVISORY, 2 UNSUPPORTED (`ELEC-RATING-007`, `THERM-TJ-050`). 100 archetypes: 13 OFFLINE_TESTED (the M4 priority set plus wearable, isolated and non-isolated AC-DC and USB-C, whose rules are exercised by the fixture tests; nothing is live-verified), 87 DRAFT. Counts are produced by `python tools/desk.py domains check --json` and the rule catalogue.
