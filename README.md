# DESK — AI-Assisted Electronics Engineering Execution System

[![Tests](https://img.shields.io/badge/tests-120%20passing-brightgreen.svg)](tests/)
[![Performance](https://img.shields.io/badge/benchmarks-%3C10ms%20pipeline-blue.svg)](tools/benchmarks.py)
[![Python](https://img.shields.io/badge/python-3.9%2B-informational.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero%20external-success.svg)](desk/)
[![ECAD](https://img.shields.io/badge/ecad-EasyEDA%20Pro-orange.svg)](https://pro.easyeda.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**DESK** is an intelligent electronics engineering execution system for **EasyEDA Pro**. It transforms unstructured hardware requirements into neat, verified, and manufacturing-ready schematics and PCB designs.

By combining deterministic engineering engines with versioned **Engineering Design Profiles**, structured **Mental Models (M1–M6)**, and multi-model AI orchestration, DESK guarantees that engineering decisions precede geometry and that every layout decision is strictly evidence-backed.

---

## Core Engineering Philosophy: Knowledge Before Geometry

```
CLIENT REQUIREMENT
       │
       ▼
[ M1: SCHEMATIC INTELLIGENCE ] ─────────► Block Decomposition, Power Tree & Netlist Spec
       │
       ▼
[ M2: PLACEMENT INTELLIGENCE ] ─────────► Mechanical Anchors, Invariants & Thermal Clusters
       │
       ▼
[ M3: ROUTING INTELLIGENCE ]   ─────────► 6-Stage Priority Scheduler & IPC-2152 Sizing
       │
       ▼
[ M4: COPPER & GROUND ]        ─────────► Stackup-Driven Planes, Power Polygons & Stitching
       │
       ▼
[ M5: MANUFACTURING & DRC ]    ─────────► Fabricator Limits & Native DRC Diagnosis
       │
       ▼
[ M6: VERIFICATION & AUDIT ]   ─────────► Fail-Closed Hard Gates & Quality Scoring
```

1. **A schematic is data first, drawing second.** The netlist is authoritative truth; the schematic drawing is visual convenience.
2. **Engineering decisions precede geometry.** Track widths, copper thickness, thermal relief, and layer stackups are calculated from physical electrical parameters before placing traces.
3. **Never build on an unverified previous stage.** Each stage enforces deterministic entry and exit criteria.
4. **Single-writer mutation safety.** EasyEDA Pro canvas mutations are strictly serialized and protected against dirty state.
5. **Fail-closed verification.** Missing validation evidence (e.g. unexecuted DRC or unverified netlist connectivity) strictly blocks manufacturing approval.

---

## Architectural Subsystems

### 1. Engineering Design Profile (`desk/profile.py`)
A single, machine-readable contract defining all physical and electrical parameters for a board:
- **Layer Stackup**: Physical layer count, inner/outer layer classification, dielectric heights, and copper thickness (`copper_thickness_oz`).
- **IPC-2152 Trace Width Engine**: Dynamic derivation of track widths based on actual per-net current limits, ambient temperature, allowed temperature rise, and layer placement.
- **RF & Impedance Profiles**: Coplanar waveguide and microstrip configurations with target characteristic impedance ($50\,\Omega$, $90\,\Omega$ differential) and dedicated ground keepout clearances.
- **Fabricator Constraints**: Manufacturer capability profiles (minimum clearance, trace width, drill sizes, annular rings, and copper-to-edge setbacks).

### 2. Mental-Model Policy Compiler (`desk/mental/compiler.py`)
Transforms high-level engineering mental models (M1 through M6) into compact, task-specific, token-budgeted policies (< 300 tokens) for AI agents and deterministic engines:
- **M1 (Schematic)**: Functional block decomposition, component selection, pin mapping, protection networks.
- **M2 (Placement)**: Mechanical anchors, connector orientations, thermal dissipation clusters, decoupling capacitor proximity, footprint invariance.
- **M3 (Routing)**: 6-stage routing priority, pin escape stubs, differential pair skew matching, return paths.
- **M4 (Copper & Ground)**: Reference plane allocation, power polygon synthesis, solid vs. thermal relief connection rules, return-path continuity verification.
- **M5 (Electrical & Manufacturing)**: IPC-2221 electrical clearances, creepage, annular ring verification, fabricator capability boundaries.
- **M6 (Verification & Review)**: 8 non-negotiable hard acceptance gates separated from weighted design quality scoring.

### 3. Autonomous 6-Stage Routing Planner (`desk/router.py`)
Deterministic net scheduling and routing strategy:
- **Stage 1**: Ground reference nets (`GND`, `PGND`, `AGND`).
- **Stage 2**: Edge and connector interfaces (`USB`, headers, screw terminals).
- **Stage 3**: High-speed critical signals (differential pairs, RF lines, clocks, analog).
- **Stage 4**: Sensitive controls (feedback loops, sense lines, resets, enables).
- **Stage 5**: Power distribution rails (`VIN`, `VBAT`, `VBUS`, `3V3`, `5V`).
- **Stage 6**: General non-critical digital interconnects.
- Automatic Specctra DSN tuning, Freerouting execution, and selective rip-up recovery.

### 4. Offline Copper & Ground Engine (`desk/copper.py`)
- **Ground Planes**: Synthesizes edge-setback reference planes on designated internal or bottom plane layers.
- **Power Polygons**: Calculates bounding convex hulls around high-current power stages (MOSFETs, inductors, switch nodes) with configurable margins.
- **Connection Rule Resolver**: Configures solid copper connections for high-current thermal pads and thermal relief with current-proportional spoke widths for passives.
- **Via Stitching Synthesis**: Computes collision-free arrays of ground stitching vias across plane boundaries while avoiding keepouts and components.
- **Return-Path Continuity**: Detects reference plane discontinuities and slot crossings beneath critical tracks.
- **Copper Island Detection**: Ray-casting point-in-polygon analysis to identify and eliminate unconnected floating copper and slivers.
- **Revision Tracking**: SHA-1 fingerprinting of copper zones for targeted invalidation and re-pour tracking.

### 5. Fail-Closed Quality Verification Engine (`desk/quality.py`)
Separates non-negotiable hard gates from weighted design scoring:
- **8 Hard Acceptance Gates** (Fail-Closed):
  1. Zero unintended short circuits.
  2. Zero unconnected populated pads.
  3. Zero hard clearance violations.
  4. All critical nets 100% connected.
  5. Valid physical layer stackup configuration.
  6. Verified copper-zone and ground plane continuity.
  7. Electrical constraints satisfied.
  8. Manufacturing capability thresholds respected.
- **Weighted Quality Score (0–100)**: Evaluates electrical correctness (25%), routing quality (20%), placement quality (15%), RF & power constraints (20%), manufacturability (10%), and geometry optimization (10%).

### 6. EasyEDA Pro Fast Bridge & PCB Adapter (`desk/adapters/easyeda_pcb_adapter.py`)
- **Sub-millisecond socket discovery** across candidate ports (`49620..49629`).
- **Redundant delay elimination**: Bypasses the 600ms document reload delay when the target PCB is already active.
- **Batch Readback**: Extracts components, pads, tracks, vias, copper zones, poured regions, physical stackup, and DRC net classes in a single round-trip.
- **Single-Writer Mutex**: Prevents race conditions and dirty document corruption.

---

## Performance Benchmarks

DESK is engineered for sub-millisecond execution with zero external Python dependencies.

```bash
python tools/benchmarks.py
```

### Benchmark Results (Intel/AMD x86_64, Windows 11)

| Benchmark Category | Scenario / Pipeline | Execution Time |
|---|---|---|
| **Part A: Micro-Scenarios** | 01 Small Sensor PCB MST | `0.40 ms` |
| | 02 Medium 4-Layer Controller (WATCH) | `5.04 ms` |
| | 03 Fine-Pitch FPC Connector (0.5mm) | `0.05 ms` |
| | 04 Screw-Terminal Power Access | `0.02 ms` |
| | 05 High-Current Power DSN Tuning | `0.27 ms` |
| | 06 Mixed-Signal Scheduling | `0.58 ms` |
| | 07 Dense Multi-Terminal MST (120 pins) | `1.92 ms` |
| | 08 DRC Collision Diagnosis & Recovery | `0.15 ms` |
| | 09 Orphan Via Convergence Check | `0.03 ms` |
| | 10 Pin Escape Congestion Evaluation | `0.05 ms` |
| **Subtotal (Part A)** | **10 Micro-Scenarios** | **`8.51 ms`** |
| **Part B: Offline Pipelines** | P1 Ingestion & Mental-Model Compilation | `0.09 ms` |
| | P2 Placement, Invariants & Mechanical Access | `0.45 ms` |
| | P3 Multi-Stage Routing & IPC-2152 Planning | `0.38 ms` |
| | P4 Copper Planes, Stitching & Return-Path Audit | `0.13 ms` |
| | P5 Fail-Closed Quality Verification & Acceptance | `0.02 ms` |
| **Subtotal (Part B)** | **5 End-to-End Engineering Pipelines** | **`1.06 ms`** |
| **Total** | **Combined Benchmark Suite** | **`9.58 ms`** |

---

## Repository Map

| Path | Description |
|---|---|
| [`desk/profile.py`](desk/profile.py) | `DesignProfile`, physical layer stackup, IPC-2152 trace sizing, RF & diff-pair specs |
| [`desk/mental/`](desk/mental/) | Mental-model registry (`models.py`, `registry.py`) and compiler (`compiler.py`) for M1–M6 |
| [`desk/router.py`](desk/router.py) | 6-stage priority scheduler, DSN tuning engine, native maze router, IPC-2152 calculator |
| [`desk/copper.py`](desk/copper.py) | Ground-plane generator, power polygon planner, stitching via synthesizer, island detector |
| [`desk/quality.py`](desk/quality.py) | Fail-closed `HardAcceptanceGates`, `WeightedQualityScore`, and verification evaluator |
| [`desk/ledger.py`](desk/ledger.py) | Append-only engineering ledger, decision memory, and profile-hash staleness tracking |
| [`desk/adapters/`](desk/adapters/) | EasyEDA Pro batch PCB extraction, copper zone mutation, and repour adapter |
| [`desk/orchestrator/`](desk/orchestrator/) | Multi-model task protocol, AGY adapter (`agy.exe`), Pi adapter (`pi.cmd`), capability router |
| [`desk/bridge.py`](desk/bridge.py) | High-performance TCP bridge, document identity guards, and single-writer mutex |
| [`tools/route.py`](tools/route.py) | CLI autonomous routing driver with profile-driven constraints and recovery rip-up |
| [`tools/benchmarks.py`](tools/benchmarks.py) | Micro-scenario and complete offline pipeline benchmark suite |
| [`tools/live_disposable_test.py`](tools/live_disposable_test.py) | Safety-guarded 9-step disposable project integration runner |
| [`docs/09_STATUS.md`](docs/09_STATUS.md) | Authoritative, evidence-based capability status table |
| [`docs/LIVE_INTEGRATION_CHECKLIST.md`](docs/LIVE_INTEGRATION_CHECKLIST.md) | Pre-flight safety gates and verification protocol for live testing |

---

## Quick Start

### 1. Prerequisites
- **Python 3.9+** (Standard library only; zero pip dependencies).
- **Node.js 18+** (Required only for the optional EasyEDA Pro live bridge server).

### 2. Run Tests & Verification
Run the complete automated offline test suite (120 tests in ~5 seconds):
```bash
python -m unittest discover -s tests -v
```

Execute performance benchmarks:
```bash
python tools/benchmarks.py
```

### 3. Initialize a New Engineering Project
```bash
python tools/new_project.py MY_PRODUCT
```
1. Define client requirements in `projects/MY_PRODUCT/REQUIREMENTS.md`.
2. Configure physical constraints in `projects/MY_PRODUCT/design_profile.json`.
3. Create subsystem blocks in `projects/MY_PRODUCT/blocks/`.
4. Run offline lint and schematic checks:
   ```bash
   python tools/lint.py projects/MY_PRODUCT 01_POWER_SUPPLY
   ```

### 4. Autonomous PCB Placement & Routing
```bash
# Read footprints and pad coordinates
python tools/pcb_dump.py projects/MY_PRODUCT

# Audit footprint invariants and verify mechanical clearances
python tools/pcb_check.py projects/MY_PRODUCT

# Execute profile-driven 6-stage routing
python tools/route.py projects/MY_PRODUCT --passes 30
```

---

## Live Integration Protocol

To protect customer schematics and production boards, **live EasyEDA Pro testing is strictly quarantined**.

- **Safety Guard**: Any script mutating live canvas primitives requires explicit confirmation and is locked to disposable test workspaces.
- **Checklist**: See [docs/LIVE_INTEGRATION_CHECKLIST.md](docs/LIVE_INTEGRATION_CHECKLIST.md) for pre-flight gates, document verification, and rollback procedures.
- **Status Ledger**: See [docs/09_STATUS.md](docs/09_STATUS.md) for audited capability statuses (`IMPLEMENTED_AND_TESTED_OFFLINE`, `IMPLEMENTED_BUT_NOT_LIVE_VERIFIED`).

---

## Agent Development Memory & Continuous Improvement (Backpass)

DESK integrates **Backpass** (`v0.1.44`) as an offline development-memory optimization layer to continuously improve agent understanding from actual development history.

- **Offline Optimization**: Backpass analyzes session transcripts from Claude Code, OpenCode, Codex, and Pi, identifies recurring mistakes and tool errors, and proposes evidence-backed edits to `AGENTS.md` and specialized engineering skills under `.agents/skills/`.
- **Zero Runtime Dependency**: Backpass is strictly a development utility; it is not imported by `desk.*` and does not run during production PCB execution.
- **Human-in-the-Loop Gate**: Analysis never writes automatically. Proposed changes require human review and approval.

### Memory Optimization Workflow (Windows PowerShell)

```powershell
# 1. Inspect memory budget, cache, and skill triggers
backpass status

# 2. Scan recent agent sessions associated with DESK
backpass scan --since 7d

# 3. Run backward pass (collects samples, calculates loss, synthesizes edits - read-only)
backpass

# 4. Review and approve proposed memory edits
backpass apply --no-ui
```

Comprehensive architecture, security, and workflow guides are available in [docs/development_memory/](docs/development_memory/).

---

## License

This project is licensed under the [MIT License](LICENSE).
Third-party notices and acknowledgments are documented in [NOTICE](NOTICE).
