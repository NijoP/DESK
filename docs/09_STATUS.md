# 09 — Capability status (evidence-based)

This document provides the authoritative, evidence-based status of all DESK capabilities.

### Capability Status Labels
- **`IMPLEMENTED_AND_TESTED_OFFLINE`**: Fully implemented and validated via offline deterministic tests, contract tests, and benchmarks.
- **`IMPLEMENTED_BUT_NOT_LIVE_VERIFIED`**: Full code paths and API adapters prepared with exact signatures, but live execution against EasyEDA Pro has not yet been executed.
- **`PARTIALLY_IMPLEMENTED`**: Core architecture or data structures present, but specific workflows or edge cases remain in progress.
- **`NOT_IMPLEMENTED`**: Capability defined in architecture but no functional implementation exists.

---

## Capability Status Table

| # | Capability | Status | Acceptance Criteria | Test Evidence / Implementation |
|---|---|---|---|---|
| **1a** | Knowledge & Ledger System | `IMPLEMENTED_AND_TESTED_OFFLINE` | Source-required decisions, append-only ledger, corrections supersede, profile-hash staleness tracking | `desk/ledger.py`, `tests/test_context.py` (16), `tests/test_decision_memory.py` (3) |
| **1b** | Context Engine & Mental-Model Retrieval | `IMPLEMENTED_AND_TESTED_OFFLINE` | Compact token packs (< 300 tokens), profile-driven constraint injection, prompt compilation | `desk/mental/compiler.py`, `desk/context.py`, `tests/test_mental_compiler.py` (5) |
| **1c** | Engineering Design Profile | `IMPLEMENTED_AND_TESTED_OFFLINE` | Physical stackup, layer copper oz, per-net current limits, IPC-2152 trace sizing, RF lines, diff pairs | `desk/profile.py`, `tests/test_profile_and_mental_models.py` (5) |
| **1d** | Multi-Model Orchestration | `IMPLEMENTED_AND_TESTED_OFFLINE` | Unified protocol, AGY adapter (`agy.exe`), Pi adapter (`pi.cmd`), L0-L4 capability router | `desk/orchestrator/`, `tests/test_orchestrator.py` (6) |
| **2** | Schematic Generation & Block Specs | `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED` | Block spec compilation, drawing generation, schematic netlist compare; live build/verify not yet run | `desk/spec.py`, `desk/models.py`, `tests/test_core.py` |
| **3a** | Offline Electrical & ERC Checks | `IMPLEMENTED_AND_TESTED_OFFLINE` | Computed QA, voltage tree, capacitor ratings, electrical pin types | `desk/spec.py`, `tests/test_core.py` |
| **3b** | EasyEDA Pro ERC Bridge | `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED` | `sch_Drc.check(..., true)` bridge execution and error parsing | `desk/drc_engine.py`, `tools/pcb_check.py` |
| **4a** | Placement Intelligence & Invariants | `IMPLEMENTED_AND_TESTED_OFFLINE` | Footprint invariants, mechanical access verification, connector orientation, cluster anchors | `desk/placement.py`, `desk/placement_intel.py`, `desk/component_intel.py`, `tests/test_placement.py` (12), `tests/test_phase6_placement_policy.py` (2) |
| **4b** | Routability Evaluation & Escape Congestion | `IMPLEMENTED_AND_TESTED_OFFLINE` | O(V²) Prim MST wirelength, pin escape congestion scoring, placement freeze snapshot hashing | `desk/routability.py`, `tests/test_perf_engineering.py` |
| **5a** | EasyEDA Pro PCB Adapter & Batch Readback | `IMPLEMENTED_AND_TESTED_OFFLINE` | Single-roundtrip batch extraction of components, pads, tracks, vias, zones, poured regions, stackup, DRC rules | `desk/adapters/easyeda_pcb_adapter.py`, `tests/test_easyeda_pcb_adapter.py` (6) |
| **5b** | Trace Width Calculation (IPC-2152) | `IMPLEMENTED_AND_TESTED_OFFLINE` | Profile-driven per-net currents, actual layer copper thickness (oz), inner vs outer layers, removal of hardcoded 1.0A power fallbacks | `desk/profile.py`, `desk/router.py`, `tests/test_copper_and_routing_intelligence.py` |
| **5c** | Autonomous PCB Routing & DSN Tuning | `IMPLEMENTED_AND_TESTED_OFFLINE` | 6-stage priority scheduling (GND -> Connectors -> Critical/RF/Diff -> Power -> Control -> Remaining), DSN tuning | `desk/router.py`, `tools/route.py`, `tests/test_evolution.py` |
| **5d** | Offline Copper & Ground Engine | `IMPLEMENTED_AND_TESTED_OFFLINE` | Ground-plane generation, power-polygon planning, solid vs thermal relief rules, stitching via synthesis, island detection, return-path continuity, revision caching | `desk/copper.py`, `tests/test_copper_engine.py` (6), `tests/test_copper_and_routing_intelligence.py` (5) |
| **5e** | EasyEDA Copper Zone Mutations & Repour | `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED` | `pcb_MathPolygon.createPolygon`, `pcb_PrimitivePour.create`, `modify`, `rebuildCopperRegion` prepared with exact API signatures | `desk/adapters/easyeda_pcb_adapter.py`, `tools/live_disposable_test.py` |
| **5f** | DRC Diagnosis & Recovery Planner | `IMPLEMENTED_AND_TESTED_OFFLINE` | Native EasyEDA DRC error parser, collision diagnoser, selective track rip-up, convergence evaluator | `desk/drc_engine.py`, `tools/drc.py`, `tests/test_evolution.py` |
| **6** | Fail-Closed Quality & Manufacturing Verification | `IMPLEMENTED_AND_TESTED_OFFLINE` | 8 hard acceptance gates fail-closed on missing evidence (`None`), weighted score (0-100), stackup & manufacturing limits validation | `desk/quality.py`, `desk/release.py`, `tests/test_quality_and_mfg_verification.py` (10) |
| **7** | Bridge Execution & Guard Optimization | `IMPLEMENTED_AND_TESTED_OFFLINE` | Sub-millisecond TCP discovery, single-writer lock, redundant 600ms `openDocument` bypass when document active | `desk/bridge.py`, `tests/test_perf_engineering.py` |
| **8** | Performance Benchmarking Suite | `IMPLEMENTED_AND_TESTED_OFFLINE` | 10 micro-scenarios (7.0ms) + 5 complete offline engineering pipelines (1.1ms), total runtime < 10ms | `tools/benchmarks.py` |
| **9** | Learning Engine & Human-Gated Rules | `IMPLEMENTED_AND_TESTED_OFFLINE` | 2-session corroboration, human approval gate, regression rollback safety | `desk/learn/`, `tests/test_learn.py` (16) |

---

## Live Integration Readiness

A dedicated test harness and checklist have been prepared for live verification on a disposable test project:
- Script: `tools/live_disposable_test.py` (protected with `--execute-live` safety flag).
- Checklist: `docs/LIVE_INTEGRATION_CHECKLIST.md` (covering all 9 verification milestones).

**Live testing has NOT yet been run.** All customer projects (`WATCH`, `BEEBOX`) remain untouched and protected.
