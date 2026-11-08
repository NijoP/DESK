# DESK System Architecture & Current State Audit
**Repository:** https://github.com/NijoP/DESK  
**Date:** November 2026  
**Auditor:** Principal Software Architect, Electronics Engineering Automation Architect & Performance Engineer  
**Status:** COMPLETE AUDIT BASELINE  

---

## Executive Summary

The DESK repository was audited under the Master Engineering Directive. DESK is an actively developed, high-precision automation system for electronic computer-aided design (ECAD) targeting EasyEDA Pro.

The core philosophy—**"A schematic is data first, drawing second; the netlist is truth; engineering decisions precede geometry"**—is robustly reflected in the codebase. The project currently has 74 passing automated tests executing in under 2.3 seconds across 6 test suites with zero external dependencies.

However, the repository currently exhibits three fundamental architectural gaps:
1. **Implicit Heuristics vs. Profile-Driven Constraints:** Critical electrical assumptions (trace widths, currents, stackups, layer assignments, keepouts) are hardcoded into regex heuristics and fixed constants rather than driven by a versioned **Engineering Design Profile**.
2. **Missing Copper & Plane Intelligence:** The system has advanced routing and placement schedulers, but lacks plane generation, ground continuity verification, return-path discontinuity analysis, and copper pour automation.
3. **Absence of Unified Multi-Model Orchestration:** The recent addition of the Backpass-inspired learning engine provides human-gated rule proposals, but AI interaction currently occurs outside a deterministic DESK orchestration framework. The local environment features `AGY CLI` (Google/Gemini) and `Pi Agent` inside `Herdr`, but DESK does not yet possess the common dispatch, health check, schema validation, and capability-based routing required for autonomous multi-model collaboration.

This audit provides a factual, evidence-backed evaluation of the existing repository, identifies bottlenecks and risks, maps proposed changes to existing modules, and establishes a phased execution roadmap.

---

## 1. Existing Capabilities

| Capability Domain | Description | Evidence / Verification |
|---|---|---|
| **Block-Spec Workflow** | Subsystem-level JSON specifications containing ICs, passives, pin-to-net mappings, and datasheet QA formulas (`qa[]`). | `desk/spec.py`, `templates/block.template.json`, `tests/test_core.py` |
| **Deterministic Schematic Drawing** | Algorithmic schematic drawing directly into EasyEDA Pro with strict geometric rules: 100-mil grid, titled frames, port stubs, staggered net labels, and NC flags. | `desk/draw.py`, `tools/build.py` |
| **Netlist & Schematic Verification** | Pin-by-pin topological comparison between live EasyEDA Pro sheet netlist and JSON block specification; detects label collisions and stray parts. | `desk/netcheck.py`, `tools/verify.py`, `tests/test_core.py` |
| **Task-Aware Context Engine** | Structural indexer providing token-budgeted context packs (`brief`, `block`, `delta`, `api`, `find`) with live linting and next-gate derivation. | `desk/context.py`, `tools/ctx.py`, `tests/test_context.py` (16 tests) |
| **Durable Project Memory** | Append-only ledger (`LEDGER.jsonl`) recording decisions, facts, assumptions, corrections, and verifications with mandatory sources and SHA-1 spec-hash staleness tracking. | `desk/ledger.py`, `tools/ledger.py`, `tests/test_context.py` |
| **Single-Writer Safety & Journal** | Process-level write lock (`write.lock`) with configurable TTL and operation journal (`ops.jsonl`) distinguishing clean stops from dirty failures for crash recovery. | `desk/ops.py`, `tests/test_core.py` |
| **Component Intelligence & Footprint Invariants** | Automatic classification of component roles; extraction of immutable pad count, pad pitch, relative positions, and drill definitions to prevent footprint distortion. | `desk/component_intel.py`, `tests/test_evolution.py`, `tests/test_perf_engineering.py` |
| **Mechanical-First Placement Rules** | Class-based pad/body spacing, board edge clearances, connector mating envelopes, screw-terminal screwdriver cones and wire entry corridors, sensor-heat isolation. | `desk/placement.py`, `desk/placement_intel.py`, `tests/test_placement.py` (12 tests) |
| **Routability Evaluation & Freeze Gate** | O(V²) distance-table Prim MST wirelength estimation, sweep-line ratsnest crossing detection, pin escape congestion scoring, and placement freeze snapshot gate. | `desk/routability.py`, `tests/test_perf_engineering.py`, `tests/test_placement.py` |
| **6-Stage Routing Priority Scheduler** | Net classification into 6 stages: GND preparation, Connector escapes, Critical/diff-pairs/clocks, Control/sensors, Power distribution, Remaining nets. | `desk/router.py`, `tests/test_evolution.py` |
| **DSN Tuning & Freerouting Pipeline** | EasyEDA DSN boundary rectification, fine-pitch escape clearance tuning, power class track widening, Freerouting subprocess execution, and SES import. | `desk/router.py`, `tools/route.py`, `tests/test_perf_engineering.py` |
| **DRC Closed-Loop Convergence Engine** | Live EasyEDA DRC parsing into structured violations, root-cause diagnoser, selective track rip-up, and progress-aware convergence loops. | `desk/drc_engine.py`, `tools/drc.py`, `tests/test_perf_engineering.py` |
| **Manufacturing Release Integrity** | Cross-verification of BOM designators, Pick-and-Place centroids, Gerber layer completeness, and SHA-256 manifest generation. | `desk/release.py`, `tools/release.py`, `tests/test_core.py` |
| **Corroborated Learning Engine** | Read-only session mining from AI transcripts via Backpass adapters; deterministic error detection; ≥2-session corroboration; human-gated proposals with regression rollbacks. | `desk/learn/engine.py`, `tools/learn.py`, `tests/test_learn.py` (16 tests) |
| **High-Precision Profiler & Telemetry** | Nanosecond-level wall-clock, CPU time, memory delta, and cache hit/miss tracking with 10-scenario representative benchmark suite. | `desk/profiler.py`, `desk/telemetry.py`, `tools/benchmarks.py`, `tools/profile_perf.py` |

---

## 2. Actual Source Modules

| Subsystem | Core Engine Module | CLI Tool / Script | Test Module |
|---|---|---|---|
| **Data Contracts & Models** | `desk/models.py` | — | `tests/test_evolution.py` |
| **Schematic Specification & Style** | `desk/spec.py`, `desk/draw.py` | `tools/lint.py`, `tools/build.py`, `tools/clear_block.py` | `tests/test_core.py` |
| **Electrical Checks & Netlist** | `desk/calc.py`, `desk/netcheck.py`, `desk/erc.py` | `tools/verify.py`, `tools/erc.py` | `tests/test_core.py` |
| **Context & Ledger Memory** | `desk/context.py`, `desk/ledger.py` | `tools/ctx.py`, `tools/ledger.py` | `tests/test_context.py` |
| **ECAD Bridge & Live Operations** | `desk/bridge.py`, `desk/ops.py` | `tools/ping.py`, `tools/desk.py` | `tests/test_core.py`, `tests/test_perf_engineering.py` |
| **Component & Footprint Intel** | `desk/component_intel.py` | `tools/resolve.py`, `tools/pins.py` | `tests/test_evolution.py`, `tests/test_perf_engineering.py` |
| **Placement Rules & Geometry** | `desk/placement.py`, `desk/placement_intel.py` | `tools/pcb_place.py`, `tools/pcb_dump.py` | `tests/test_placement.py` |
| **Routability & Acceptance Gates** | `desk/routability.py`, `desk/snapshot.py` | `tools/pcb_check.py` | `tests/test_perf_engineering.py` |
| **Routing & DSN Tuning** | `desk/router.py` | `tools/route.py`, `tools/pcb_rules.py` | `tests/test_evolution.py`, `tests/test_perf_engineering.py` |
| **DRC Convergence & Recovery** | `desk/drc_engine.py` | `tools/drc.py` | `tests/test_perf_engineering.py` |
| **Manufacturing Release** | `desk/release.py` | `tools/release.py`, `tools/bom.py` | `tests/test_core.py` |
| **Learning & Continuous Rework** | `desk/learn/engine.py`, `desk/learn/collect.mjs` | `tools/learn.py` | `tests/test_learn.py` |
| **Performance Profiling & Benchmarking** | `desk/profiler.py`, `desk/telemetry.py` | `tools/profile_perf.py`, `tools/benchmarks.py` | `tests/test_perf_engineering.py` |

---

## 3. Missing Capabilities

1. **Mental-Model Compiler & Task-Specific Policy Retrieval (M1–M6):**
   - Mental models currently exist only as human-readable Markdown documents (`docs/00` to `docs/05`) or scattered hardcoded constants.
   - Missing: A structured compiler that resolves project design constraints against mental models to generate compact, task-specific policies with strict JSON output schemas and deterministic verification requirements.
2. **Versioned Engineering Design Profile (`design_profile.json`):**
   - The project currently relies on unversioned `project.json` and loose markdown in `REQUIREMENTS.md`.
   - Missing: A centralized, versioned engineering contract capturing operating voltages, currents, power tree, switching frequencies, actual layer stackup, copper weights, dielectric parameters, thermal envelopes, and manufacturer design rules.
3. **Copper & Ground Plane Intelligence (M4):**
   - No automated generation or verification of copper pours and ground zones.
   - No stackup-aware ground reference plane validation (currently assumes Layer 2 is always GND on 4-layer boards).
   - Missing polygon priority rules, thermal relief vs. solid connection management, stitching via arrays, return-path discontinuity checks, and copper-to-edge isolation rules.
4. **Unified Multi-Model Orchestration Layer:**
   - Both `AGY CLI` (Google Gemini) and `Pi Agent` are installed and accessible via Herdr, but DESK has no orchestration layer to dispatch tasks, validate structured responses, enforce timeouts, handle worker failures, or record latency telemetry.
5. **Capability-Based Task Scheduling (L0–L4):**
   - No execution router that determines whether a task is L0 (deterministic code only), L1 (fast single model), L2 (capable model + verification), L3 (independent dual-model review + verification), or L4 (frontier model escalation).
6. **Manufacturer Capability Integration:**
   - DRC rules and DSN tuning use hardcoded constants (e.g. 4.02 mil clearance, 5.0 mil width) rather than loading exact capability matrices from target PCB fabricators (e.g., JLCPCB standard vs. advanced pool, PCBWay, Eurocircuits).
7. **Weighted Quality Score & Formal Acceptance Gate:**
   - Quality evaluation is limited to a binary DRC check (0 errors) and a placement routability score (0.0 to 1.0).
   - Missing: A comprehensive weighted quality score (Electrical 25%, Routing 20%, Placement 15%, RF/Power 20%, Manufacturability 10%, Geometry 10%) strictly separated from non-negotiable hard acceptance gates.

---

## 4. Duplicate and Overlapping Responsibilities

1. **Dual Placement Implementations:**
   - `desk/placement.py` (legacy rule checker) and `desk/placement_intel.py` (advanced placement engine) contain overlapping bounding-box calculations, component classification routines, and duplicate clearance dictionaries.
   - `tools/pcb_check.py` invokes both engines sequentially, causing redundant computation.
2. **Data Representation Divergence (Dataclasses vs. Primitives):**
   - `desk/models.py` defines comprehensive dataclasses (`PlacementPlan`, `PlacementIntent`, `RoutingConstraint`, `ComponentRequirement`).
   - However, `tools/pcb_place.py` and `projects/WATCH/placement.json` continue to serialize and deserialize raw untyped tuples: `["U1", x, y, rot, side, "reason"]`.
3. **Telemetry & Profiler Redundancy:**
   - `desk/profiler.py` and `desk/telemetry.py` represent a single cohesive subsystem split across two files. `desk/telemetry.py` consists of 48 lines solely formatting data collected by `desk/profiler.py`.
4. **Ad-hoc Regex in Tool Scripts:**
   - `tools/route.py`, `tools/pcb_rules.py`, and `desk/router.py` each independently classify nets using variations of regular expressions (`re.search(r"VCC|VDD|3V3...", net)`), leading to inconsistent classification of borderline nets (e.g. `VSYS`, `VBAT_SENSE`).

---

## 5. Performance Bottlenecks

Based on live telemetry profiling (`tools/profile_perf.py` and `tools/benchmarks.py`):

1. **Sequential TCP Socket Port Discovery (708 ms):**
   - When the EasyEDA bridge is not running or slow to respond, port scanning across 49620–49629 sequentially consumes up to 708 ms before timing out.
2. **Pair-Wise Placement Collision Checking (504 ms):**
   - `desk/placement.py` checks pairwise distances between all pad pairs without hierarchical spatial clustering or R-tree partitioning, causing quadratic growth as component count increases.
3. **Regex-Based String Rewriting in DSN Tuning:**
   - Parsing and modifying entire multi-megabyte DSN files using regex substitutions (`BOUNDARY_RX`, `CLASS_BLOCK_RX`) creates excessive string allocations and memory churn.
4. **Unbounded Subprocess Execution:**
   - Freerouting execution (`tools/route.py`) defaults to a high pass count when not dynamically budgeted, risking minutes of unneeded iterations after route convergence.

---

## 6. Engineering Risks

1. **Hardcoded Four-Layer Stackup Assumption:**
   - `desk/router.py` (`StackupManager.detect_stackup`) assumes every four-layer board uses `["Top", "Inner1_GND", "Inner2_PWR", "Bottom"]`. This assumption fails on designs requiring Layer 3 as a ground reference for controlled impedance on Layer 4, or multi-rail designs using split power planes.
2. **Current Capacity Inferred from Net Names:**
   - `TraceWidthCalculator.get_width_mil` assigns trace widths based solely on string matching (e.g. `VBUS` → 1.5A, `3V3` → 0.8A). This is dangerous: a 3.3V rail powering an MCU in sleep consumes 15 µA, while a 3.3V rail driving motor drivers or RF power amplifiers may draw 3A. Current limits must come from the Engineering Design Profile.
3. **Unvalidated Microstrip Impedance & RF Routing:**
   - Current RF routing treats 50-ohm lines with generic widths (e.g. 5 mil default signal) without calculating dielectric height ($H$), dielectric constant ($\epsilon_r$), or trace thickness ($T$), leading to massive return losses and RF signal degradation.
4. **Hardcoded Keepout Injection (Unstaged Hack):**
   - An unstaged edit in `desk/router.py` manually injected a hardcoded antenna keepout rectangle `(keepout "ANTENNA" (polygon signal 0 0 1456.69 ...))` for a specific board. This bypasses the project's data-driven model and corrupts other designs.
5. **Absence of Ground Return Path Continuity:**
   - High-speed differential pairs (USB, CAN) and fast switching nodes (buck converters) are routed without verifying that an adjacent, continuous ground return plane exists directly beneath the tracks.

---

## 7. Live Integration Gaps

1. **EasyEDA Bridge Execution Pre-conditions:**
   - When EasyEDA Pro is closed or the `Run API Gateway` extension is inactive, all bridge calls fail immediately (`WinError 10061`). DESK tools must provide structured diagnostic reporting and offline simulation fallbacks rather than crashing unhandled.
2. **Document UUID & Multi-Window Switching:**
   - EasyEDA Pro API method `dmt_Project.openProject` previously returned `false` if another document was dirty or open in the client. The bridge relies on window ID matching which requires manual synchronization if EasyEDA reloads.
3. **Copper Pour API Unexercised:**
   - The live API commands for creating polygons (`pcb_PrimitiveCopperPour.create`), assigning nets, and triggering recalculation (`pcb_Document.rebuildCopperPours`) exist in `library/api_map.json` but have not been implemented or verified in DESK tools.
4. **Stale Capability Status:**
   - `docs/09_STATUS.md` records 41 tests passing and lists several completed offline features as AMBER. The status document must be synchronized with the actual verified state (74 passing tests).

---

## 8. Proposed Changes Mapped to Existing Modules

```
Existing Module            Proposed Evolution / Mapped Change
---------------------------------------------------------------------------------------------------------
desk/models.py             -> Add DesignProfile, CompiledPolicy, TaskSchema, ResultSchema,
                              CopperZoneSpec, StackupDefinition, QualityScoreReport models.
desk/context.py            -> Integrate compiled policy retrieval into context engine;
                              cache compiled policies by design profile & model version hash.
desk/router.py             -> Eliminate hardcoded stackups & regex currents. Drive stackup,
                              widths, clearances, and layer preferences from DesignProfile.
desk/placement_intel.py    -> Drive spacing, keepouts, and decap distances from DesignProfile;
                              unify legacy rules from desk/placement.py.
desk/placement.py          -> Refactor as deterministic execution engine powered by compiled policies.
desk/drc_engine.py         -> Enhance with hard gates vs weighted quality scoring.
desk/bridge.py             -> Retain fast socket discovery; add connection health check and
                              structured bridge error reporting.
desk/ops.py                -> Preserve single-writer lock; enforce immutable audit trail for
                              all AI-proposed modifications.
desk/telemetry.py          -> Consolidate profiler and telemetry reporting into unified service.
NEW: desk/profile.py       -> Engineering Design Profile parser, validator, and version manager.
NEW: desk/mental/          -> Unified Mental-Model Registry (M1-M6) and Mental-Model Compiler.
NEW: desk/orchestrator/    -> Multi-model worker protocol, AGY adapter, Pi adapter,
                              capability scheduler (L0-L4), and dispatch engine.
NEW: desk/copper.py        -> Copper and ground plane intelligence, return-path continuity,
                              and stitching via generator.
```

---

## 9. Phased Implementation Plan

### Phase 0: Baseline Verification & Environment Stabilization (Current)
- Complete comprehensive audit (`docs/architecture/CURRENT_STATE_AUDIT.md`).
- Verify existing 74 unit tests pass cleanly.
- Reconcile unstaged working tree diffs safely without altering customer project data.

### Phase 1: Documentation & Capability Status Synchronization
- Update `docs/09_STATUS.md` with current evidence (74 passing tests, actual verified offline modules).
- Document verified API boundaries and bridge requirements in `docs/06_EASYEDA_API.md`.

### Phase 2: Formal Engineering Design Profile & Mental-Model Registry
- Create `desk/profile.py` implementing the versioned `DesignProfile` data contract.
- Create `desk/mental/` defining the primary mental models (M1 Schematic, M2 Placement, M3 Routing, M4 Copper/Ground, M5 Manufacturing, M6 Verification).
- Unit test profile validation and invalidation hooks.

### Phase 3: Mental-Model Policy Compiler & Context Integration
- Build `desk/mental/compiler.py` to compile full mental models into compact, task-specific policies with output schemas and verification rules.
- Connect compiled policies to `desk/context.py` so agents receive compact, relevant instructions without doc bloat.
- Implement policy cache with automatic invalidation on profile change.

### Phase 4: Unified Multi-Model Orchestration (AGY + Pi Adapters)
- Define `desk/orchestrator/protocol.py` (common task and result schemas).
- Implement `desk/orchestrator/agy_adapter.py` for `agy.exe` (--print, JSON schema enforcement).
- Implement `desk/orchestrator/pi_adapter.py` for `pi.cmd` (--mode json, non-interactive execution).
- Implement health checks, execution timeouts, error recovery, and latency telemetry.

### Phase 5: Capability-Based Model Routing (L0–L4)
- Implement `desk/orchestrator/router.py` with execution tiers:
  - L0: Deterministic code execution (no LLM).
  - L1: Fast single-model reasoning.
  - L2: Capable model with deterministic validation.
  - L3: Independent dual-model review + deterministic validation.
  - L4: Frontier model escalation.
- Add test harness verifying L0 bypass and fallback mechanics.

### Phase 6: Profile-Driven Placement & Schematic Enhancement
- Refactor `desk/placement_intel.py` and `desk/spec.py` to consume `DesignProfile`.
- Eliminate hardcoded clearance constants in favor of profile-driven rules.
- Validate against representative test cases.

### Phase 7: Mature RF, Power, Routing & Copper Intelligence
- Upgrade `desk/router.py` to eliminate hardcoded stackup and current heuristics.
- Implement `desk/copper.py` for ground reference zones, copper pouring, stitching vias, and return-path checking.
- Connect copper pour automation to DSN tuning and EasyEDA export.

### Phase 8: Electrical & Manufacturing Verification Hardening
- Implement manufacturer capability loading (e.g. JLCPCB standard/advanced rules).
- Build the formal acceptance gate in `desk/drc_engine.py` separating hard gates from weighted quality scores (Electrical 25%, Routing 20%, Placement 15%, RF/Power 20%, Manufacturability 10%, Geometry 10%).

### Phase 9: Decision Memory & Learning Engine Maturation
- Extend `LEDGER.jsonl` to track mental-model versions, requirement IDs, and multi-model consensus evidence.
- Connect verified learning patterns into compiler policy updates with human sign-off.

### Phase 10: System Benchmarking & Controlled Live Verification
- Execute full 10-scenario benchmark suite and measure latency deltas.
- Run controlled live test sequence against disposable EasyEDA test project.
- Validate Definition of Done across all 14 criteria.
