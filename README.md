# DESK

### From engineering intent to verified PCB execution.

[![Tests](https://img.shields.io/badge/tests-269%20passing-brightgreen.svg)](tests/)
[![Performance](https://img.shields.io/badge/benchmarks-%3C10ms%20pipeline-blue.svg)](tools/benchmarks.py)
[![Overhead](https://img.shields.io/badge/server%20overhead-%2B0.011ms%2Fop-purple.svg)](tests/bench_server_overhead.py)
[![Python](https://img.shields.io/badge/python-3.9%2B-informational.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero%20external-success.svg)](desk/)
[![ECAD](https://img.shields.io/badge/ecad-EasyEDA%20Pro-orange.svg)](https://pro.easyeda.com/)
[![Dashboard](https://img.shields.io/badge/mission%20control-127.0.0.1%3A49620-brightgreen.svg)](http://127.0.0.1:49620)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**DESK** is an intelligent, deterministic electronics engineering execution system for **EasyEDA Pro**. It transforms unstructured hardware requirements into verified, manufacturing-ready schematics and PCB designs.

By combining deterministic physical engines, versioned **Engineering Design Profiles**, structured **Mental Models (M1–M6)**, and an event-driven **Local Mission Control**, DESK guarantees that physical engineering laws strictly precede geometry and that clients maintain complete real-time visibility into every automated decision.

---

## What It Is & What It Is Not

| What DESK Is | What DESK Is Not |
|---|---|
| A deterministic engineering execution system that calculates trace widths, return paths, and clearances from first principles. | An LLM that guesses component coordinates or hallucinates layout geometry directly into a canvas. |
| A fail-closed quality gate that halts the pipeline if physical constraints or DRC rules fail. | A rubber-stamp tool that outputs unverified gerbers or ignores manufacturing tolerances. |
| A local, private mission control server streaming real-time execution telemetry to your browser. | A cloud SaaS that uploads proprietary schematics, netlists, or IP to third-party servers. |
| A zero-dependency Python core using standard library primitives for maximum portability and speed. | A heavy, bloated framework dependent on npm runtimes, Flask/Django servers, or fragile pip dependencies. |

---

## What DESK Does: The Problem vs. The Solution

### The Problem
General-purpose AI agents and coding assistants fail at hardware design because:
1. **Hallucinated Geometry**: Agents guess $(X, Y)$ coordinates without understanding track ampacity, thermal dissipation, or mechanical clearances.
2. **Missing Return Paths**: Traces cross reference-plane splits, creating severe EMI loops and impedance mismatches.
3. **Black-Box Execution**: When autonomous scripts execute in the background, engineers cannot see what net is being scheduled, whether DRC failed, or if an operation stalled.
4. **Optimistic Bias**: Agents declare designs "finished" even when unrouted airwires, acid traps, or DRC violations remain.

### The DESK Solution
DESK enforces **Knowledge Before Geometry**:
1. **Mathematical Pre-calculation**: Before a single segment is drawn, DESK calculates exact trace widths via IPC-2152, coplanar wave-guide spacing, and fabricator annular ring limits.
2. **Deterministic Priority Scheduling**: Routes nets in a strict 6-stage order (Ground $\to$ Connectors $\to$ Critical High-Speed/RF $\to$ Sensitive Feedback $\to$ Power Rails $\to$ General Digital).
3. **Local Mission Control**: Built-in HTTP/SSE server streaming live stage transitions, net progress, memory telemetry, and diagnostic logs to `http://127.0.0.1:49620`.
4. **Fail-Closed Verification**: 8 non-negotiable hard acceptance gates separate from weighted scoring. If an unrouted net or clearance violation exists, manufacturing signoff is strictly blocked.

---

## Core Features

- **Engineering Design Profile (`desk/profile.py`)**  
  Machine-readable contracts governing layer stackup, copper thickness ($1\,\text{oz}, 2\,\text{oz}$), IPC-2152 temperature-rise limits, impedance targets ($50\,\Omega$ RF, $90\,\Omega$ diff pairs), and fabricator tolerances.
- **Component Intelligence (`desk/components/`)**  
  Parametric database, lifecycle risk detection, pin-mapping validation, and multi-supplier BOM resolution (JLCPCB, LCSC, Digi-Key, Mouser).
- **Schematic Intelligence (`desk/schematic/`)**  
  Authoritative netlist extraction, functional block decomposition, power-tree validation, and ERC net continuity auditing.
- **Placement Intelligence (`desk/placement/`)**  
  Mechanical anchor locking, thermal dissipation clustering, decoupling capacitor proximity constraints, and footprint invariant auditing.
- **Autonomous 6-Stage Routing (`desk/router.py`)**  
  Physics-guided maze router, Specctra DSN auto-tuning, Freerouting harness, and automated rip-up recovery.
- **Offline Copper & Ground Engine (`desk/copper.py`)**  
  Convex-hull power polygons, stackup-driven reference planes, collision-free ground via stitching arrays, return-path slot detection, and floating island removal.
- **Fail-Closed Quality Gates (`desk/quality.py`)**  
  8 non-negotiable hard criteria (zero shorts, zero opens, 100% critical connectivity, stackup integrity) paired with a weighted 100-point engineering scorecard.
- **Local Mission Control (`desk/runtime/`)**  
  High-performance, zero-dependency `http.server` streaming execution events via Server-Sent Events (SSE) to a single-page responsive telemetry UI.

---

## Local Mission Control: Real-Time Execution Observability

When DESK executes a design pipeline, engineers open:

```
http://127.0.0.1:49620
```

```
┌────────────────────────────────────────────────────────────────────────┐
│  DESK MISSION CONTROL  v1.0.0   ● LIVE   Project: ESP32_SENSOR_NODE    │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────┤
│   PROGRESS   │ ACTIVE STAGE │    STAGES    │   WARNINGS   │  DURATION  │
│    75.0%     │ PCB Routing  │ 7/12 Done    │   0 Errors   │   1.84s    │
├──────────────┴──────────────┴──────────────┴──────────────┴────────────┤
│ 12-STAGE CANONICAL WORKFLOW:                                           │
│ [✓] Requirements  [✓] Schematic  [✓] Components  [✓] Electrical        │
│ [✓] PCB Ingest    [✓] Placement  [✓] Routing Prep [▶] PCB Routing      │
│ [ ] Copper/GND    [ ] DRC/Verify [ ] Mfg Check   [ ] Final Report      │
├────────────────────────────────────────────────────────────────────────┤
│ LIVE EXECUTION TIMELINE:                                               │
│ 00:24:12 [INFO]   Ingestion: Design profile validated for 4-layer FR4 │
│ 00:24:13 [INFO]   Placement: Mechanical anchors locked for USB-C & SWD │
│ 00:24:14 [INFO]   Routing Prep: Scheduled 42 nets via 6-stage priority │
│ 00:24:15 [RUN]    PCB Routing: Route net SPI_MOSI (track: 10 mil)      │
├────────────────────────────────────────────────────────────────────────┤
│ VERIFIED ARTIFACTS:                                                    │
│ • specctra.dsn (142 KB)  • placement_audit.json (12 KB)                │
└────────────────────────────────────────────────────────────────────────┘
```

### Server & Security Invariants
- **Localhost Bound**: Binds strictly to `127.0.0.1` (`INADDR_LOOPBACK`). Zero public exposure.
- **Port Collision Resolution**: Automatically probes candidate ports (`49620..49635`) if the primary port is occupied.
- **Zero Polling (SSE Streaming)**: Updates stream over HTTP `/api/v1/events` with keepalive heartbeats and `Last-Event-ID` reconnection replay.
- **Strictly Read-Only**: The monitoring API has zero mutation endpoints, guaranteeing telemetry cannot alter PCB state.
- **Path Traversal Guard**: Rejects null bytes, relative traversal tokens (`../`, `..\`), and absolute drive paths.

---

## Quick Start

### 1. Prerequisites
- **Python 3.9+** (Standard library only; zero external pip dependencies).
- **Node.js 18+** (Optional: required only for the live EasyEDA Pro bridge).

### 2. Verify Installation
Clone the repository and run the test suite:
```bash
git clone https://github.com/NijoP/DESK.git
cd DESK

# Run complete 269-test automated suite (~9 seconds)
python -m unittest discover -s tests -p "test_*.py"
```

### 3. Launch Local Mission Control
Start the standalone Mission Control server:
```bash
# Start background server and launch browser
python desk.py dashboard

# Or run foreground HTTP server
python desk.py serve --port 49620
```

### 4. Query Status via CLI
```bash
# Human-readable summary
python desk.py status

# Machine-readable JSON output
python desk.py status --json
```

### 5. Run an End-to-End Engineering Pipeline
Execute autonomous placement, net scheduling, and routing for an engineering project:
```bash
# Create or select a project
python tools/new_project.py SENSOR_HUB

# Run 6-stage autonomous routing
python tools/route.py projects/SENSOR_HUB --passes 30
```

---

## How It Works: Pipeline Architecture

```mermaid
flowchart TD
    subgraph Client["Client Environment"]
        REQ["Hardware Requirements"]
        SPEC["Design Profile (JSON)"]
    end

    subgraph DESK_Core["DESK Deterministic Core"]
        M1["M1: Schematic & Netlist"]
        M2["M2: Placement & Invariants"]
        M3["M3: 6-Stage Routing Scheduler"]
        M4["M4: Copper, Planes & Stitching"]
        M5["M5: Manufacturing Limits & DRC"]
        M6["M6: Fail-Closed Quality Gates"]
    end

    subgraph Telemetry["Event & Telemetry Layer"]
        EB["Bounded EventBus (Ring Buffer)"]
        PROJ["State Projection Engine (12 Stages)"]
        SRV["DeskServer (127.0.0.1:49620)"]
        SSE["SSE Stream (/api/v1/events)"]
        UI["Mission Control UI (index.html)"]
    end

    subgraph ECAD["CAD & Bridge"]
        EEDA["EasyEDA Pro Bridge"]
        GERBER["Verified Gerbers & Release"]
    end

    REQ --> SPEC
    SPEC --> M1
    M1 --> M2 --> M3 --> M4 --> M5 --> M6
    
    M1 -.->|Telemetry Event| EB
    M2 -.->|Telemetry Event| EB
    M3 -.->|Telemetry Event| EB
    M4 -.->|Telemetry Event| EB
    M5 -.->|Telemetry Event| EB
    M6 -.->|Telemetry Event| EB

    EB --> PROJ
    PROJ --> SRV
    SRV --> SSE --> UI
    
    M6 -->|Gates Pass (Score >= 80)| EEDA
    EEDA --> GERBER
```

---

## Engineering Philosophy

1. **A schematic is data first, drawing second.**  
   The electrical netlist is authoritative truth; the graphical schematic is an interactive representation.
2. **Engineering physics strictly precede geometry.**  
   Current capacity, dielectric breakdown, thermal expansion, and impedance targets dictate dimensions before coordinates are generated.
3. **Never build on an unverified previous stage.**  
   Deterministic stage gates prevent routing unverified placements or pouring copper over open electrical nets.
4. **Single-writer mutation safety.**  
   CAD workspace mutations are serialized and protected by an acquire/release mutex to prevent dirty state.
5. **Fail-closed verification.**  
   Missing validation evidence blocks manufacturing sign-off. A test not run is treated as a failed test.
6. **Zero runtime magic & full observability.**  
   Every engineering decision is captured in the append-only ledger and projected in real-time to the developer's dashboard.

---

## Repository Structure

```
DESK/
├── desk/                           # Core Python Package (Zero External Dependencies)
│   ├── adapters/                   # CAD bridges (EasyEDA Pro batch adapter, JSON-RPC)
│   ├── components/                 # Component intelligence, parametric search, BOM
│   ├── contracts/                  # Formal engineering schemas & stage gates
│   ├── mental/                     # Mental-Model Compiler (M1–M6 policy generators)
│   ├── runtime/                    # Mission Control telemetry & event server
│   │   ├── events.py               # Bounded EventBus & structured event model
│   │   ├── projection.py           # 12-stage state projection & progress calculator
│   │   └── server.py               # Localhost HTTP/SSE streaming server
│   ├── ui/assets/                  # Single-page Mission Control dashboard
│   │   └── index.html              # Responsive dark/light theme dashboard
│   ├── bridge.py                   # High-speed TCP bridge & canvas mutex
│   ├── copper.py                   # Polygon planes, return paths, stitching vias
│   ├── ledger.py                   # Append-only engineering audit memory
│   ├── profile.py                  # IPC-2152 calculator & DesignProfile parser
│   ├── quality.py                  # Fail-closed HardAcceptanceGates & scorecards
│   └── router.py                   # 6-stage priority scheduler & maze router
├── docs/                           # Technical Specifications & Documentation
│   ├── architecture.md             # Subsystem architecture & data flow
│   ├── execution-events.md         # Event schema & SSE streaming specification
│   ├── getting-started.md          # Developer onboarding & tutorial
│   ├── local-dashboard.md          # Mission Control operational guide
│   ├── 09_STATUS.md                # Authoritative capability audit ledger
│   └── development_memory/         # Backpass continuous learning documentation
├── tests/                          # Automated Verification Suite (269 Tests)
│   ├── bench_server_overhead.py    # Sub-millisecond server overhead benchmark
│   ├── test_copper_geometry.py     # Polygon, plane, and stitching tests
│   ├── test_events.py              # EventBus & SSE replay test suite
│   ├── test_projection.py          # State projection & redaction test suite
│   ├── test_quality_fail_closed.py # Hard gate enforcement test suite
│   ├── test_router_hardening.py    # 6-stage scheduler & routing tests
│   └── test_server.py              # HTTP security, port fallback & API tests
├── tools/                          # Command-Line Utilities & Runners
│   ├── benchmarks.py               # Micro-scenario and offline pipeline benchmarks
│   ├── desk.py                     # Primary DESK CLI tool
│   ├── lint.py                     # Offline schematic netlist linter
│   ├── new_project.py              # Project scaffold generator
│   └── route.py                    # Autonomous routing driver
└── desk.py                         # Root CLI entry point
```

---

## Technical Documentation Index

| Guide / Specification | Topic & Scope |
|---|---|
| [**Getting Started**](docs/getting-started.md) | Initial setup, configuration, CLI commands, and building your first PCB. |
| [**Subsystem Architecture**](docs/architecture.md) | Deep dive into profiles, mental models, routers, and bridge synchronization. |
| [**Local Mission Control**](docs/local-dashboard.md) | Dashboard layout, REST endpoints, CLI commands, and security invariants. |
| [**Execution Events & SSE**](docs/execution-events.md) | Complete JSON schema for the 12 canonical stages, event bus, and replay tokens. |
| [**Capability Status Ledger**](docs/09_STATUS.md) | Granular audit of implemented, offline-tested, and live-verified capabilities. |
| [**Live Safety Checklist**](docs/LIVE_INTEGRATION_CHECKLIST.md) | Pre-flight safety protocols and rollback procedures for CAD integration. |
| [**Development Memory**](docs/development_memory/00_ADOPTION_AUDIT.md) | Backpass adoption, transcript discovery, and continuous agent improvement. |

---

## Implementation Status Table

| Subsystem / Capability | Implementation State | Test & Evidence Verification |
|---|---|---|
| **Design Profile Engine** | `PRODUCTION` | 100% stackup & IPC-2152 trace sizing tested (`test_profile_hardening.py`) |
| **Mental Models (M1–M6)** | `PRODUCTION` | All 6 policies compiled under 300 token budget (`test_mental_models.py`) |
| **6-Stage Net Scheduler** | `PRODUCTION` | Priority ordering & escape stubs verified (`test_router_hardening.py`) |
| **Offline Copper & Planes** | `PRODUCTION` | Ray casting, via arrays & split detection tested (`test_copper_geometry.py`) |
| **Fail-Closed Hard Gates** | `PRODUCTION` | 8 gates strictly block on unrouted or shorted nets (`test_quality_fail_closed.py`) |
| **EventBus & SSE Stream** | `PRODUCTION` | Bounded buffer, replay & listener isolation verified (`test_events.py`) |
| **State Projection** | `PRODUCTION` | 12 canonical stages & credential redaction tested (`test_projection.py`) |
| **Mission Control HTTP** | `PRODUCTION` | Port fallback, security headers & read-only enforcement (`test_server.py`) |
| **Mission Control UI** | `PRODUCTION` | Single-page HTML/CSS/JS dashboard (`desk/ui/assets/index.html`) |
| **EasyEDA Pro Bridge** | `OFFLINE_TESTED` | TCP bridge tested; live canvas mutation quarantined (`test_bridge.py`) |

---

## Performance Benchmarks

DESK is engineered for sub-millisecond execution with zero external runtime dependencies.

```bash
# Run pipeline performance benchmarks
python tools/benchmarks.py

# Run server overhead benchmarks
python tests/bench_server_overhead.py
```

### 1. Deterministic Core Execution (`tools/benchmarks.py`)

| Benchmark Category | Pipeline / Scenario | Execution Time |
|---|---|---|
| **Micro-Scenarios (Part A)** | Small Sensor PCB MST | `0.40 ms` |
| | Medium 4-Layer Controller (WATCH) | `5.04 ms` |
| | Fine-Pitch FPC Connector (0.5mm) | `0.05 ms` |
| | Screw-Terminal Power Access | `0.02 ms` |
| | High-Current Power DSN Tuning | `0.27 ms` |
| | Mixed-Signal Scheduling | `0.58 ms` |
| | Dense Multi-Terminal MST (120 pins) | `1.92 ms` |
| | DRC Collision Diagnosis & Recovery | `0.15 ms` |
| | Orphan Via Convergence Check | `0.03 ms` |
| | Pin Escape Congestion Evaluation | `0.05 ms` |
| **Offline Pipelines (Part B)**| P1 Ingestion & Mental-Model Compilation | `0.09 ms` |
| | P2 Placement, Invariants & Mechanical Access | `0.45 ms` |
| | P3 Multi-Stage Routing & IPC-2152 Planning | `0.38 ms` |
| | P4 Copper Planes, Stitching & Return-Path Audit | `0.13 ms` |
| | P5 Fail-Closed Quality Verification & Acceptance | `0.02 ms` |
| **Total Pipeline Time** | **Combined Benchmark Suite** | **`9.58 ms`** |

### 2. Local Mission Control Telemetry Overhead (`tests/bench_server_overhead.py`)

| Benchmark Condition | 100 Consecutive Operations | Average per Operation | Added Overhead |
|---|---|---|---|
| **Baseline (Server Inactive)** | `24.13 ms` | `0.241 ms` | — |
| **Active Telemetry (Server + SSE)** | `25.27 ms` | `0.253 ms` | **`+0.011 ms / op`** |

- **Peak Memory Overhead**: $\le 50.0\,\text{MB}$ total process footprint.
- **Latency Impact**: $< 5\%$ addition over native offline execution.

---

## Agent Continuous Improvement (Backpass)

DESK supports **Backpass** (`v0.1.44`) as an offline development-memory optimization layer to continuously improve agent understanding from actual development history.

- **Offline Optimization**: Backpass analyzes session transcripts from Claude Code, OpenCode, Codex, and Pi, identifies recurring mistakes and tool errors, and proposes evidence-backed edits to `AGENTS.md` and specialized engineering skills under `.agents/skills/`.
- **Zero Runtime Dependency**: Backpass is strictly a development utility; it is not imported by `desk.*` and does not run during production PCB execution.
- **Human-in-the-Loop Gate**: Analysis never writes automatically. Proposed changes require human review and approval.

```powershell
# Inspect memory budget, cache, and skill triggers
backpass status

# Scan recent agent development sessions
backpass scan --since 7d

# Synthesize proposed memory adjustments (read-only)
backpass

# Review and approve proposed memory edits
backpass apply --no-ui
```

---

## Contributing & License

Contributions are welcome! Please ensure all PRs:
1. Maintain zero external runtime dependencies.
2. Adhere to the single-writer mutex safety model.
3. Pass all 269 automated offline tests (`python -m unittest discover -s tests`).
4. Update the capability ledger in [`docs/09_STATUS.md`](docs/09_STATUS.md).

This project is licensed under the [MIT License](LICENSE).  
Third-party notices and acknowledgments are documented in [NOTICE](NOTICE).
