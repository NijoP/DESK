# Product Capability Matrix

**Status values:** VERIFIED (reproducible test or recorded live run), IMPLEMENTED_UNVERIFIED (code present, no evidence of correct behaviour against the real target), PARTIALLY_IMPLEMENTED, MISSING, BROKEN, NEEDS_HARDWARE_VALIDATION (correct in software, needs a fabricated board or live ECAD to confirm).
**Evidence date:** 2026-11-11. Test suite executed: 352 passed, 3 skipped. Live EasyEDA mutation has never been executed (`docs/09_STATUS.md`).

| # | Capability | Status | Evidence | Gap / owner |
|---|---|---|---|---|
| 1 | Requirements gate R (10 dimensions, power budget, voltage tree) | PARTIALLY_IMPLEMENTED | Template and docs only; no validator. `projects/WATCH/LEDGER.jsonl` L-0003 is a hand-typed "gate passed" | PX-02 validator (Product Experience) |
| 2 | Component selection gate B (F1–F7 matrix) | PARTIALLY_IMPLEMENTED | `docs/00b`; `tools/resolve.py` resolves MPN→EasyEDA device; `library/devices.json` has empty footprints | H-09 symbol↔footprint check (Hardware) |
| 3 | Datasheet verification | MISSING | pin maps come from EasyEDA/LCSC symbols (`tools/pins.py`), no datasheet cross-check | H-09 |
| 4 | Schematic block build (`build.py`) | IMPLEMENTED_UNVERIFIED | offline tests on spec compile; live build is a documented workflow in INC records but no recorded verification transcript in repo | QA-05 |
| 5 | Offline ERC | VERIFIED (narrow) | `desk/erc.py` 6 checks, tests in `test_core.py` | H-11 ERC breadth (driver conflicts, floating inputs, I/O voltage) |
| 6 | Live EasyEDA ERC/DRC bridge | IMPLEMENTED_UNVERIFIED | `tools/erc.py`, `tools/drc.py`, `drc_engine.DRCParser` tested on fixtures | QA-05 |
| 7 | Placement rules and routability gate | VERIFIED (offline) | `test_placement.py` (12), `test_perf_engineering.py`; 0.015 ms per evaluation | PX-06 project-agnostic defaults |
| 8 | Pad-escape analysis | VERIFIED (offline) | B2: 349 pads in 11.75 ms, 86 constrained | — |
| 9 | Trace width from current (IPC-2221, labelled 2152) | VERIFIED formula, BROKEN integration | values match 2221 (11.9 mil at 1 A); three inconsistent implementations; `tools/route.py` ignores the profile and hard-codes widths | H-03, H-10 |
| 10 | Unknown-current fail-closed | BROKEN | `allow_unknown_default=False` never called; unknown rails sized at 1 A | H-02 (P0) |
| 11 | Voltage clearance / creepage | BROKEN above 50 V | `profile.py:272-283` tops out at 24 mil | H-01 (P0) |
| 12 | Differential pairs | PARTIALLY_IMPLEMENTED | profile + stage scheduling + EasyEDA rule objects; `DiffPairVerification` never instantiated; no skew/impedance | H-04 |
| 13 | Controlled impedance (microstrip/stripline/CPWG) | MISSING | stackup fields unused | H-05 |
| 14 | Via ampacity / thermal via farms | MISSING | fixed 24/12 mil vias everywhere | H-06 |
| 15 | Copper pour planning, thermal relief | IMPLEMENTED_UNVERIFIED | `desk/copper.py` geometry tests pass; pour creation API never live-run; regex "L"/"SW" misclassifies | H-07, QA-05 |
| 16 | Return-path / plane-split verification | PARTIALLY_IMPLEMENTED | 5 sample points against zone outline; ignores poured copper, antipads, other-net zones | H-07 |
| 17 | Autorouting via Freerouting with supervision | VERIFIED (offline supervision), NEEDS_HARDWARE_VALIDATION (results) | `test_routing_*` (29); WATCH rev B stalled at 108/320 unrouted (INC-007); SES import deletes all tracks with no rollback | PX-04 undo, PCB-01 planes from dump |
| 18 | Pre-flight congestion veto | VERIFIED (M1) | `tools/route.py` phase 9c, `--force` override | — |
| 19 | Physical pad-to-pad connectivity verifier | IMPLEMENTED_UNVERIFIED | B5 reports 1/59 nets connected on Project One: dataset mismatch or verifier defect | QA-03 |
| 20 | DRC diagnosis and recovery planner | VERIFIED (offline) | `test_evolution.py` | — |
| 21 | Manufacturing readiness report | VERIFIED (M1 fail-closed) | previously fabricated verified=True; now reports checks not performed | — |
| 22 | 8 fail-closed quality gates | VERIFIED (offline) | `test_quality_fail_closed.py`; `copper_zones_connected` input is never computed from the live board | H-07 |
| 23 | Rework mode (baseline, audit, plan, approve, execute, report) | PARTIALLY_IMPLEMENTED | 25 tests; `execute` mutates an in-memory snapshot, not EasyEDA; board dims default 50×50 mm | PX-07 live executor |
| 24 | Single-writer lock and ops journal | VERIFIED (M1) | reclaim race closed; mutation timeout journaled dirty; two-process test still open | QA-02 |
| 25 | Atomic state writes | PARTIALLY_IMPLEMENTED | `desk/fsutil.py` used for project.json, port cache, pcb_dump.json; 28 sites remain | SW-02 |
| 26 | Durable task inbox / scheduler | IMPLEMENTED_UNVERIFIED, unused | in-memory only; nothing in production calls it | SW-04 |
| 27 | Process liveness reconciliation after restart | MISSING for tasks | only the dashboard projection marks INTERRUPTED | SW-04 |
| 28 | Mission Control dashboard | PARTIALLY_IMPLEMENTED | real hardware metrics; stage status from file heuristics; routing progress is a time formula; WATCH hard-coded | PX-05 |
| 29 | Credential vault and redaction | VERIFIED (offline) | `test_auth_system.py` (7) | — |
| 30 | Component intelligence (LCSC, Mouser, JLCPCB PCBA BOM/CPL) | VERIFIED (offline, mocked HTTP) | `test_ci_*`, `test_jlcpcb_integration.py` | PX-09 CLI for BOM/CPL export |
| 31 | Release (gerber, PnP, IPC-D-356A, manifest) | IMPLEMENTED_UNVERIFIED | `tools/release.py`; exports only after all gates; no live run recorded | QA-05 |
| 32 | L0-L4 model router | VERIFIED (M1, mock + one live L1/L2 run) | 1.1 s L1, 31.8 s L2 via direct NVIDIA adapter; not wired into any stage | AI-01 |
| 33 | Model capability registry | VERIFIED (3 NVIDIA models probed) | `capabilities.py` | — |
| 34 | Context engine (token-budgeted packs) | VERIFIED (offline) | `test_context.py` (16) | SW-10 index `learning/` |
| 35 | Learning engine (human-gated rules) | VERIFIED (offline) | `test_learn.py` (16) | SW-10 consolidate stores |
| 36 | Environment doctor | VERIFIED (M1) | `desk.py doctor` 12 ok / 2 warn on this machine | — |
| 37 | KiCad import | MISSING | skill references non-existent `desk/adapters/kicad_adapter.py` | PX-10 (P4) |
| 38 | Panelisation | MISSING in code | INC-005 human dialog | P4 |
| 39 | Undo of a DESK mutation | MISSING | checkpoints save/load only | PX-04 (P1) |
| 40 | Engineering report (MD/PDF) | PARTIALLY_IMPLEMENTED | rework `final_report.md` only | PX-09 |
| 41 | Non-rectangular board outline to router | MISSING | DSN boundary overwritten with a rectangle | H-08 |
| 42 | CI | MISSING | no workflow directory | QA-06 |

**Summary counts:** VERIFIED 14 (several narrow or offline-only), IMPLEMENTED_UNVERIFIED 7, PARTIALLY_IMPLEMENTED 10, MISSING 8, BROKEN 3.
