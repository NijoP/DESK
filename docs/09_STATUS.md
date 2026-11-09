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
| **1c** | Engineering Design Profile | `IMPLEMENTED_AND_TESTED_OFFLINE` | CurrentConfidence (`VERIFIED`, `ESTIMATED`, `UNKNOWN`), fail-closed power current sizing, physical stackup with dielectric thickness & reference layers, versioned manufacturer profiles | `desk/profile.py`, `tests/test_profile_hardening.py` (5), `tests/test_profile_and_mental_models.py` (5) |
| **1d** | Multi-Model Orchestration | `IMPLEMENTED_AND_TESTED_OFFLINE` | Unified protocol, AGY adapter (`agy.exe`), Pi adapter (`pi.cmd`), L0-L4 capability router | `desk/orchestrator/`, `tests/test_orchestrator.py` (6) |
| **2** | Schematic Generation & Block Specs | `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED` | Block spec compilation, drawing generation, schematic netlist compare; live build/verify not yet run | `desk/spec.py`, `desk/models.py`, `tests/test_core.py` |
| **3a** | Offline Electrical & ERC Checks | `IMPLEMENTED_AND_TESTED_OFFLINE` | Computed QA, voltage tree, capacitor ratings, electrical pin types | `desk/spec.py`, `tests/test_core.py` |
| **3b** | EasyEDA Pro ERC Bridge | `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED` | `sch_Drc.check(..., true)` bridge execution and error parsing | `desk/drc_engine.py`, `tools/pcb_check.py` |
| **4a** | Placement Intelligence & Invariants | `IMPLEMENTED_AND_TESTED_OFFLINE` | Footprint invariants, mechanical access verification, connector orientation, cluster anchors | `desk/placement.py`, `desk/placement_intel.py`, `desk/component_intel.py`, `tests/test_placement.py` (12), `tests/test_phase6_placement_policy.py` (2) |
| **4b** | Routability Evaluation & Escape Congestion | `IMPLEMENTED_AND_TESTED_OFFLINE` | O(V²) Prim MST wirelength, pin escape congestion scoring, placement freeze snapshot hashing | `desk/routability.py`, `tests/test_perf_engineering.py` |
| **5a** | EasyEDA Pro PCB Adapter & Batch Readback | `IMPLEMENTED_AND_TESTED_OFFLINE` | Single-roundtrip batch extraction of components, pads, tracks, vias, zones, poured regions, stackup, DRC rules | `desk/adapters/easyeda_pcb_adapter.py`, `tests/test_easyeda_pcb_adapter.py` (6) |
| **5b** | Trace Width Calculation (IPC-2152) | `IMPLEMENTED_AND_TESTED_OFFLINE` | Profile-driven per-net currents, actual layer copper thickness (oz), inner vs outer layers, max(net_class, IPC-2152, mfg) guarantee | `desk/profile.py`, `desk/router.py`, `tests/test_copper_and_routing_intelligence.py` |
| **5c** | Autonomous PCB Routing & DSN Tuning (V2) | `IMPLEMENTED_AND_TESTED_OFFLINE` | Routing Intelligence V2: pad escape feasibility, AST S-expr DSN parser, process supervisor, decoupled power widening, true physical pad-to-pad connectivity verification, zero-new-violation gate | `desk/routing/`, `desk/router.py`, `tests/test_routing_*.py` (29 tests), `tools/routing_benchmarks.py` |
| **5d** | Offline Copper & Ground Engine | `IMPLEMENTED_AND_TESTED_OFFLINE` | 2D polygon-polygon intersection, keepout engulfment detection, edge crossing, true polygon containment return-path verification | `desk/copper.py`, `tests/test_copper_geometry.py` (4), `tests/test_copper_engine.py` (6) |
| **5e** | EasyEDA Copper Zone Mutations & Repour | `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED` | `pcb_MathPolygon.createPolygon`, `pcb_PrimitivePour.create`, `modify`, `rebuildCopperRegion` prepared with exact API signatures | `desk/adapters/easyeda_pcb_adapter.py`, `tools/live_disposable_test.py` |
| **5f** | DRC Diagnosis & Recovery Planner | `IMPLEMENTED_AND_TESTED_OFFLINE` | Native EasyEDA DRC error parser, collision diagnoser, selective track rip-up, convergence evaluator | `desk/drc_engine.py`, `tools/drc.py`, `tests/test_evolution.py` |
| **6a** | Fail-Closed 5-State Quality Gates | `IMPLEMENTED_AND_TESTED_OFFLINE` | Traceable `VerificationEvidence`, 8 hard acceptance gates with independent proofs, zero default discontinuities, strict revision/profile hash matching | `desk/quality.py`, `tests/test_quality_fail_closed.py` (5), `tests/test_quality_and_mfg_verification.py` (13) |
| **6b** | Adaptive Resource Management & Scheduler | `IMPLEMENTED_AND_TESTED_OFFLINE` | Hardware detection (cores, RAM, pressure), budgets (LOW, NORMAL, HIGH), task classification, single serialized writer | `desk/runtime/`, `tests/test_runtime_and_resources.py` (6) |
| **6c** | Incremental Snapshot & Spatial Grid Index | `IMPLEMENTED_AND_TESTED_OFFLINE` | 2D Spatial hash grid, multi-domain fingerprinting, incremental update equivalence invariant (`INCREMENTAL == REBUILD`) | `desk/snapshot.py`, `tests/test_incremental_snapshot.py` (3) |
| **7** | Bridge Execution & Mutation Safety | `IMPLEMENTED_AND_TESTED_OFFLINE` | Atomic `O_CREAT \| O_EXCL` lock, OS-level PID liveness detection, op classifications, 600ms bypass when sheet active | `desk/ops.py`, `desk/bridge.py`, `tests/test_perf_engineering.py` |
| **8** | Performance Benchmarking Suite | `IMPLEMENTED_AND_TESTED_OFFLINE` | 10 micro-scenarios + 5 complete offline pipelines + 4 runtime benchmarks + complete T01-T13 pipeline telemetry | `tools/benchmarks.py` |
| **9** | Learning Engine & Human-Gated Rules | `IMPLEMENTED_AND_TESTED_OFFLINE` | 2-session corroboration, human approval gate, regression rollback safety | `desk/learn/`, `tests/test_learn.py` (16) |
| **10a**| OS-Native Credential Security Vault | `IMPLEMENTED_AND_TESTED_OFFLINE` | Windows Credential Manager (`Advapi32.dll`), macOS Keychain, POSIX 0600 storage, zero pip dependencies | `desk/auth/storage.py`, `tests/test_auth_system.py` (7) |
| **10b**| Credential Broker & Secret Redaction | `IMPLEMENTED_AND_TESTED_OFFLINE` | Zero raw secrets in prompts, automated scrubbing (`[REDACTED_SECRET]`), fail-closed provider health | `desk/auth/broker.py`, `tests/test_auth_system.py` |
| **11** | EasyEDA Pro Official CLI & Safety Barrier | `IMPLEMENTED_AND_TESTED_OFFLINE` | CLI discovery (`easyeda-pro`), session inspection, protected project pattern rejection (`WATCH`, `BEEBOX`), pre-mutation snapshots | `desk/eda/easyeda_pro.py`, `tests/test_easyeda_pro_integration.py` (8) |
| **12** | JLCPCB Manufacturing & SMT Integration | `IMPLEMENTED_AND_TESTED_OFFLINE` | PCB fabrication pricing, PCBA SMT setup & joint modeling, Basic ($0) vs Extended ($3) parts, rotation offset normalization, Absolute Order Guard | `desk/manufacturing/jlcpcb/`, `tests/test_jlcpcb_integration.py` (6) |
| **13** | Universal Component Intelligence | `IMPLEMENTED_AND_TESTED_OFFLINE` | Canonical component identity, LCSC provider, Mouser provider, JLCPCB PCBA BOM, CPL Centroid exports | `desk/component_intelligence/`, `tests/test_ci_*.py` |
| **14** | Local Mission Control Cockpit & Telemetry Streaming | `IMPLEMENTED_AND_TESTED_OFFLINE` | Localhost loopback (`127.0.0.1:49630`), zero external pip dependencies, 12 canonical stages, SSE streaming with heartbeats & `Last-Event-ID` replay, path traversal guard, sensitive token sanitization | `desk/runtime/server.py`, `desk/runtime/projection.py`, `desk/ui/assets/index.html`, `tests/test_server.py` (14), `tests/test_events.py` (6), `tests/test_projection.py` (6), `tests/bench_server_overhead.py` |
| **15** | Rework Mode for Existing Boards & 8-Domain Audit | `IMPLEMENTED_AND_TESTED_OFFLINE` | Multi-domain baseline snapshots, 8-domain defect audit (`RW-0001..`), surgical repair planner, human approval tokens (`RW-APR-XXXX`), live readback verification, fail-closed manufacturing readiness engine | `desk/rework/`, `tests/test_rework_session.py`, `tests/test_rework_audit.py`, `tests/test_rework_baseline.py`, `tests/test_rework_connection.py`, `tests/test_rework_planner.py`, `tests/test_rework_executor.py`, `tests/test_rework_readiness.py`, `tests/test_rework_e2e.py` (25 tests) |

---

## Live Integration Readiness

A dedicated test harness and checklist have been prepared for live verification on a disposable test project:
- Script: `tools/live_disposable_test.py` (protected with `--execute-live` safety flag, real acceptance assertions, and automated primitive rollback on failure).
- Checklist: `docs/LIVE_INTEGRATION_CHECKLIST.md` (covering all 9 verification milestones).

**Live testing has NOT yet been run.** All customer projects (`WATCH`, `BEEBOX`) remain untouched and protected.
