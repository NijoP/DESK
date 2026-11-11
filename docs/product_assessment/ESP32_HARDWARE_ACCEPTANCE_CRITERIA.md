# ESP32 Hardware Acceptance Criteria and Senior Engineer Scorecard

Independent evaluation is mandatory: a senior engineer may reject a design that DESK's internal gates pass. DESK's reports are inputs to the review, never proof.

## Evaluators (roles to be assigned by the Founder)

Embedded hardware · PCB layout · Power electronics · Signal integrity · Analogue/RF (C3) · Manufacturing engineering.

## Scorecard (0-10 each; a 0-3 in any row rejects the design)

| Dimension | What the evaluator inspects (actual output, not the report) | Evidence DESK must attach |
|---|---|---|
| Schematic correctness | every block against the datasheet reference circuit; power sequencing; strapping pins; reset/boot | block specs with datasheet page citations, ERC output, netlist compare |
| Component suitability | ratings vs rails (voltage, current, temperature), package, lifecycle, availability | selection matrix F1-F7, LCSC data with retrieval timestamps, datasheet references |
| Pin mapping | symbol pin numbers vs datasheet; footprint pad numbers vs symbol; polarity | `library/pins/<MPN>.json` provenance, footprint check report |
| Placement quality | anchors respected, decoupling loops, crystal, feedback, RF keep-out, thermal spacing, routability | placement check output, dense-board report, refinement log with authoriser |
| Routing quality | widths vs calculated, clearances vs standards tables, diff pairs, return paths, via usage, neckdowns | routing plan, DSN rules, connectivity report, DRC report, engine pass history |
| Power integrity | rail currents declared, widths and vias per `desk/ipc.py`, drop budget, loop areas | power distribution report |
| Grounding | continuous reference, stitching, no accidental splits, islands | copper-zone report, poured-copper readback |
| Copper quality | net/layer correctness, reliefs vs solid, clearances | ZoneCheck results |
| DRC/ERC | EasyEDA DRC and ERC clean or waivers justified | reports with counts and locations |
| Manufacturing outputs | Gerber, drill, stackup, BOM with LCSC ids, CPL rotations, assembly classes | release manifest, preflight report; fabricator DFM separate |
| Maintainability | ledger decisions with sources, readable specs, no hand edits lost | `LEDGER.jsonl`, project docs |

## Hard acceptance rules per stage

- **Stage 1:** no undeclared rail current or voltage (`validate_electrical_inputs` empty); no invented part (every MPN resolves); pin maps verified against the datasheet for every IC; ERC clean or waived with reason.
- **Stage 2:** placement check errors = 0; no overloaded region with a placement cause left unauthorised; locked parts unchanged.
- **Stage 3:** `PhysicalConnectivityVerifier` 100 % with pours as conductors (SW-11 required for plane nets); zero illegal connections; DRC delta ≤ 0 critical; diff-pair skew/gap within profile (H-04 required); widths ≥ calculated.
- **Stage 4:** every `ZoneCheck` OK; ground continuity verified on poured copper; stitching present where declared.
- **Stage 5:** readiness report `approved` with an empty `checks_not_performed` list for the applicable checks; exports validated; human approval recorded before any order.

## Rejection reasons the evaluator must be able to record

Electrical error · unsafe clearance · unverified pin map · placement violates a client constraint · routing not physically continuous · copper island or missing return path · manufacturing file defect · insufficient evidence (DESK claimed what it did not verify).

## Where DESK is today against these criteria

Stage 1 and 5 criteria are checkable offline; Stage 3 criteria for plane nets and differential pairs cannot be fully checked yet (SW-11, H-04 open); Stage 4 needs live pour readback (never executed). The scorecard therefore cannot be filled for any design yet; this document defines the bar.
