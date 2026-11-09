# DESK Routing Intelligence V2: Technical Architecture Specification

**Document:** `docs/ROUTING_INTELLIGENCE_V2.md`  
**Author:** Principal PCB Routing Algorithm Engineer, EDA Systems Architect & Quality Lead  
**Date:** November 2026  
**Status:** Implemented, Integrated, and Verified across 332 Automated Tests  
**Target Subsystem:** `desk/routing/`, `desk/router.py`, `tools/route.py`, `tools/routing_benchmarks.py`

---

## 1. Executive Overview & The Problem We Solved

During empirical engineering reworks on complex multilayer hardware (specifically **Project One**, an 89-component, 4-layer, 59-net Voice-Interactive Wearable PCB featuring an ESP32-S3, fine-pitch QFN power management, USB, SPI, and audio circuitry), DESK's autonomous routing pipeline experienced severe execution delays (>45 minutes cumulative runtime), modal GUI process hangs, QFN maze search collapses, and unverified connectivity claims.

Deep technical disassembly and JVM thread analysis revealed that these failures were caused by six architectural bottlenecks:
1. **Modal GUI Hangs (`BN-004`):** Freerouting defaulted to GUI mode and spawned a modal Swing dialog on pass completion, freezing headless background subprocesses indefinitely.
2. **QFN Pin Traps (`BN-005`):** High-current power trace rules (35 mil) were rigidly injected into global DSN net classes, physically colliding with 9.8 mil pad gaps on 0.50 mm QFNs and collapsing Freerouting's maze search algorithm.
3. **Search Space Explosions (`BN-006`):** Specifying a 0.25 mil grid multiplied A* state space by $16\times$, triggering `TIME_LIMIT_TO_PREVENT_ENDLESS_LOOP` timeouts on cross-board traces.
4. **Pass 999 Runaway Loops (`BN-007`):** In Freerouting v2.1.0, `stop_pass_no` defaulted to 999 in bytecode, ignoring `-mp` flags and executing until process kill or 100% completion.
5. **Naive Net-Name Verification (`BN-009`):** The previous verifier marked any net "routed" if a single track segment existed with that net name, falsely claiming incomplete routes as complete.
6. **IPC Error Masking (`BN-008`):** EasyEDA JavaScript HTTP 500 exceptions were caught as generic network disconnects in `desk/bridge.py`, obscuring underlying errors.

**DESK Routing Intelligence V2** completely replaces these heuristics with a deterministic, resource-allocation-driven engineering architecture.

---

## 2. Core Mental Model: Routing as Dynamic Resource Allocation

PCB routing is not a simple geometric shortest-path problem. A real PCB is a dynamic resource-allocation ecosystem involving competing nets, fine-pitch escape corridors, thermal ampacity requirements, reference plane continuity, and manufacturing limits.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ROUTING AS RESOURCE ALLOCATION                       │
├─────────────────────────────────────────────────────────────────────────┤
│  1. SENSE & UNDERSTAND  │ Build accurate spatial model of physical PCB  │
│  2. PREDICT DIFFICULTY  │ Pad escape feasibility before routes consume  │
│  3. ALLOCATE SCARCITY   │ Soft corridor reservations for critical nets │
│  4. SELECT STRATEGY     │ Strategy A-G tailored per net requirements    │
│  5. SUPERVISE PROCESS   │ Real-time streaming, watchdog, headless locks │
│  6. SAFE WIDENING       │ Decouple DSN escape from post-route widening  │
│  7. PROVE CORRECTNESS   │ Pad-to-pad physical connectivity & DRC diff   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Architecture (The 12 Core Engines)

Routing Intelligence V2 is modularized under [`desk/routing/`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/):

### Subsystem 1: Board Intelligence Engine ([`board.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/board.py))
- Ingests `pcb_dump.json` into normalized coordinates (`mil` and `mm`).
- Constructs a 2D `SpatialHashIndex` (50 mil buckets) for sub-millisecond obstacle lookups, pad coordinate queries, and collision detection.
- Fast bounding-box filtering eliminates repetitive full-board scans.

### Subsystem 2: Real Pad Escape Feasibility Engine ([`escape.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/escape.py))
- Evaluates individual component pad pitch, adjacent pad edge spacing, and via drop feasibility.
- Probes 8 cardinal and diagonal corridor vectors (`NORTH`, `SOUTH`, `EAST`, `WEST`, and diagonals).
- Classifies each pad into: `EASY_ESCAPE`, `MODERATE_ESCAPE`, `RESTRICTED_ESCAPE`, `CRITICAL_ESCAPE`, or `NO_LEGAL_ESCAPE_FOUND`.
- Calculates available exit width without violating fine-pitch clearances ($4.02\text{ mil}$).

### Subsystem 3: Adaptive Routing Priority Engine ([`priority.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/priority.py))
- Replaces static regex priority with multidimensional dynamic constrainedness scoring:
  $$\text{Priority} = w_c \cdot \text{Crit} + w_e \cdot \text{Escape} + w_r \cdot \text{Congestion} + w_s \cdot \text{LayerScarcity} + w_t \cdot \text{Topology} + w_u \cdot \text{Urgency}$$
- Schedules escape-constrained nets early (Stage 2) before flexible digital nets consume exit corridors.
- Treats differential pairs as coupled, highest-criticality routing units (Stage 3).

### Subsystem 4: Congestion-Aware Global Planner ([`congestion.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/congestion.py))
- Layer-aware 2D grid tracking occupied copper, obstacle density, and available routing capacity.
- Applies soft corridor reservations for constrained high-priority nets.
- Supports incremental updates after each routed track.

### Subsystem 5: Routing Strategy & Topology Selection ([`strategy.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/strategy.py))
Assigns one of seven formal routing strategies per net:
- **Strategy A (Two-Terminal):** Direct point-to-point path search.
- **Strategy B (Multi-Terminal):** Obstacle-aware Minimum Spanning Tree / Steiner tree.
- **Strategy C (Fine-Pitch Escape):** Escape-first fanout with neckdowns.
- **Strategy D (Differential Pair):** Coupled microstrip routing with length, skew, and impedance bounds.
- **Strategy E (Power Delivery):** Decoupled escape width in DSN followed by post-import trunk widening.
- **Strategy F (Plane Stitching):** Priority via stitching into continuous internal planes.
- **Strategy G (RF Isolated):** High-frequency transmission lines over continuous ground reference planes.

### Subsystem 6: Mature Routing Engine Orchestrator ([`orchestrator.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/orchestrator.py))
- **Java Compatibility Probing:** Tests bytecode compatibility, automatically bypassing Java 25 JARs (`UnsupportedClassVersionError`) on Java 23 systems.
- **Mandatory Headless Configuration:** Injects `--gui.enabled=false` and generates `freerouting.json` with `"gui": {"enabled": false}` and strict job timeouts.
- **Process Supervision:** Line-by-line streaming of stdout/stderr, pass completion tracking, and watchdog-driven stagnation termination.

### Subsystem 7: Execution Time Profiling ([`profiling.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/profiling.py))
- Context-managed stopwatch tracking all 20 canonical routing phases.
- Separates CPU execution from IPC latency, process startup, and CAD readback.

### Subsystem 8: Proper Trace Width & Neckdown Management ([`width.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/width.py))
- Decouples DSN escape width ($10.0\text{ mil}$) from physical heavy copper trunk width ($25\text{--}35\text{ mil}$).
- Evaluates clearance along the proposed widened envelope for every segment.
- Preserves escape neckdowns in fine-pitch IC corridors while safely widening open-board power trunks.

### Subsystem 9: True Physical Connectivity Verification ([`connectivity.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/connectivity.py))
- Replaces naive net-name occurrence checks with full topological copper graph analysis.
- Connects track segments, T-junctions, pads, and multilayer vias using a Disjoint Set Union (DSU) graph.
- Distinguishes: `FULLY_CONNECTED`, `PARTIALLY_CONNECTED`, `MISSING_ROUTE`, `ILLEGAL_CONNECTION`, and `UNCONNECTED_PADS`.

### Subsystem 10: DRC-First Quality & Acceptance Engine ([`quality.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/quality.py))
- Baseline-aware DRC diff analysis: categorizes violations into `pre_existing`, `resolved`, and `newly_introduced`.
- Enforces a fail-closed gate: if any critical violation is newly introduced, the route is strictly rejected.

### Subsystem 11: Intelligent Recovery ([`recovery.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/recovery.py))
- Classifies failures into 16 structured diagnostic categories.
- Selectively rips up only minimal conflicting segments, preserving verified and accepted copper artwork.
- Stagnation detector terminates unproductive retry loops.

### Subsystem 12: Fast but Safe Execution Modes ([`modes.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/modes.py))
- `FAST_MODE` (12 passes, bounded optimization, routine boards).
- `BALANCED_MODE` (30 passes, production default, full escape/congestion planning).
- `PRECISION_MODE` (60 passes, demanding boards, extensive optimization).
- *Strict Rule:* Modes adjust computational budgets, never electrical safety or acceptance criteria.

---

## 4. DSN S-Expression Parser & Invariant Verifier ([`dsn.py`](file:///C:/Users/HP/OneDrive/Documents/DESK/desk/routing/dsn.py))

Replacing fragile regex string replacements, `SExprParser` and `DSNTree` provide a balanced recursive S-expression parser:
- Preserves 100% of unknown nodes, vendor comments, padstack polygons, and coordinate units.
- Safely modifies `(boundary ...)`, `(grid wire 1.25)`, `(rule ...)`, and `(class ... (rule ...))` without corrupting adjacent nodes like `(circuit (use_via via0))`.
- Cryptographic invariant checking verifies that component counts, net counts, and layer definitions remain strictly identical before and after transformation.

---

## 5. Summary of Bottleneck Fixes

| Bottleneck ID | Empirical Symptom | Root Cause | Routing Intelligence V2 Resolution |
|---|---|---|---|
| **BN-004** | Subprocess stuck indefinitely (>16 min) | Freerouting modal `WindowUserSettings` Swing dialog | Injected `--gui.enabled=false` & headless `freerouting.json` |
| **BN-005** | 143+ unrouted pin maze search failures | 35 mil power trace forced into 9.8 mil QFN pad gap | Decoupled DSN escape (10 mil) from post-import widening |
| **BN-006** | A* search timeout on cross-board traces | 0.25 mil grid multiplied search space by $16\times$ | Standardized grid to 1.25 mil with 4.02 mil fine-pitch clearance |
| **BN-007** | Autorouter ran past target passes to 999 | Freerouting `stop_pass_no` defaults to 999 | Implemented watchdog supervision with plateau termination |
| **BN-008** | Obscured JavaScript runtime exceptions | `desk/bridge.py` caught HTTP 500 as generic `OSError` | Decoded HTTPError payload to surface exact JS errors |
| **BN-009** | Incomplete routes falsely reported complete | Naive string check: `trk.get('net') in readback` | Pad-to-pad physical connectivity engine with DSU graph |
