# DESK

### An AI-Assisted Electronics Design Engineering Workbench
**THE SENTINEL — A Homeostatic Engineering Organism**

*Protect the design. Repair the damage. Preserve the integrity.*

<p align="center">
  <img src="assets/branding/desk-sentinel.svg" alt="THE SENTINEL — Homeostatic Engineering Organism" width="850"/>
</p>

[![Python](https://img.shields.io/badge/python-3.9%2B-informational.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero%20external-success.svg)](desk/)
[![ECAD](https://img.shields.io/badge/ecad-EasyEDA%20Pro-orange.svg)](https://pro.easyeda.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 1. What DESK Is

**DESK** is an open-source, AI-assisted engineering workbench built specifically for hardware and electronics engineers working with **EasyEDA Pro**.

It is not a replacement for the ECAD tool or for engineering judgment. DESK works alongside your EDA environment as a physics-guided co-pilot that enforces a hardware-first principle:

> **Knowledge before geometry. Physical electrical laws before layout appearance. Deterministic verification before automated board mutation.**

DESK helps you design, route, audit, and prepare boards for fabrication — from requirements to manufacturing readiness — with deterministic confidence and human approval at every stage.

---

## 2. Architecture Overview

DESK is built as a set of Python modules with **zero external pip dependencies** (100% Python standard library).

```
┌────────────────────────────────────────────────────────────────────────┐
│                        HARDWARE ENGINEER                               │
│           (Reviews constraints, inspects results, approves work)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         DESK WORKBENCH                                 │
│                                                                        │
│  Context Engine ─── AI Orchestrator ─── Mission Control Telemetry      │
│       │                   │                      │                     │
│  ┌────┴────┐    ┌────────┴────────┐     ┌───────┴──────┐              │
│  │ Profile  │    │ Routing Intel V2│     │ Local Server │              │
│  │ & Specs  │    │ Dense PCB Intel │     │ :49630       │              │
│  └─────────┘    │ Congestion      │     └──────────────┘              │
│                  │ Escape Analysis │                                    │
│  ┌─────────┐    │ Priority Router │     ┌──────────────┐              │
│  │Component│    │ Power-Aware     │     │ Quality Gates│              │
│  │ Intel   │    │ Width Engine    │     │ (8 domains)  │              │
│  │ & BOM   │    └─────────────────┘     └──────────────┘              │
│  └─────────┘                                                           │
│  ┌─────────┐    ┌─────────────────┐     ┌──────────────┐              │
│  │Placement│    │ Copper & Ground │     │ Rework Mode  │              │
│  │ Intel   │    │ Plane Engine    │     │ Surgical     │              │
│  └─────────┘    └─────────────────┘     │ Repair       │              │
│                                          └──────────────┘              │
│  ┌─────────┐    ┌─────────────────┐     ┌──────────────┐              │
│  │ IPC-2152│    │ DRC / ERC       │     │ Learning &   │              │
│  │ Calc    │    │ Engines         │     │ Decision Log │              │
│  └─────────┘    └─────────────────┘     └──────────────┘              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               EASYEDA PRO (Desktop or Web ECAD Canvas)                 │
│          FreeRouting (External Routing Engine via DSN/SES)              │
└────────────────────────────────────────────────────────────────────────┘
```

### Core Modules

| Module | Location | Purpose |
|---|---|---|
| **Profile & Design Specs** | [`desk/profile.py`](desk/profile.py), [`desk/spec.py`](desk/spec.py) | Design profiles, IPC-2152 trace width calculation, electrical constraints |
| **Component Intelligence** | [`desk/component_intelligence/`](desk/component_intelligence/) | LCSC/JLCPCB parametric search, lifecycle auditing, BOM generation, procurement |
| **Placement Intelligence** | [`desk/placement_intel.py`](desk/placement_intel.py), [`desk/placement.py`](desk/placement.py) | Mechanical-first placement hierarchy, functional clustering, decoupling proximity |
| **Routing Intelligence V2** | [`desk/routing/`](desk/routing/) | S-expr DSN parser, pad escape analysis, congestion analysis, priority scheduling, process supervisor |
| **Dense PCB Intelligence** | [`desk/routing/density.py`](desk/routing/density.py) | Grid-based supply/demand modelling, hotspot detection, escape-first strategies |
| **Congestion Analysis** | [`desk/routing/congestion.py`](desk/routing/congestion.py) | Layer-specific congestion grid, corridor reservations, routing density |
| **Pad Escape Analysis** | [`desk/routing/escape.py`](desk/routing/escape.py) | Per-pad escape feasibility, fine-pitch classification, legal exit direction analysis |
| **Priority Routing** | [`desk/routing/priority.py`](desk/routing/priority.py) | 6-stage net priority scheduling (ground → power → high-speed → analog → digital) |
| **Routing Recovery** | [`desk/routing/recovery.py`](desk/routing/recovery.py) | Plateau detection, multi-pass recovery, rip-up and reroute strategies |
| **Power Distribution** | [`desk/power_distribution.py`](desk/power_distribution.py) | Rail current analysis, copper sizing, via arrays, voltage-drop estimation |
| **Power-Aware Trace Widths** | [`desk/routing/width.py`](desk/routing/width.py) | Profile-driven width enforcement for power and signal nets |
| **Copper & Ground Planes** | [`desk/copper.py`](desk/copper.py) | Reference plane allocation, return-path verification, island detection, zone management |
| **Physical Connectivity** | [`desk/routing/connectivity.py`](desk/routing/connectivity.py) | True post-route connectivity verification |
| **DRC Engine** | [`desk/drc_engine.py`](desk/drc_engine.py) | Design-rule and clearance checking |
| **ERC Engine** | [`desk/erc.py`](desk/erc.py) | Electrical rules check (netlist continuity, pin types) |
| **Rework Mode** | [`desk/rework/`](desk/rework/) | 8-domain audit, baseline capture, surgical repair planner, executor |
| **Quality Gates** | [`desk/quality.py`](desk/quality.py) | 8 fail-closed acceptance gates for manufacturing readiness |
| **Context Engine** | [`desk/context.py`](desk/context.py) | Structural indexing, task-pack assembly under token budgets |
| **AI Orchestrator** | [`desk/orchestrator/`](desk/orchestrator/) | Multi-model orchestration (local/cloud), capability routing |
| **EasyEDA Bridge** | [`desk/bridge.py`](desk/bridge.py) | EasyEDA Pro window/socket discovery and communication |
| **Learning Engine** | [`desk/learn/`](desk/learn/), [`learning/`](learning/) | Incident capture, lesson extraction, engineering experience repository |
| **Mission Control** | [`desk/runtime/server.py`](desk/runtime/server.py) | Local telemetry dashboard on port 49630 |
| **Routing Profiling** | [`desk/routing/profiling.py`](desk/routing/profiling.py) | Per-phase wall-clock instrumentation across 20 routing phases |

---

## 3. Implemented Capabilities

### 3.1 Hardware Engineering Intelligence

- **IPC-2152 Trace Width Calculation:** Trace widths computed from physical thermal formulas based on copper weight, maximum current, and temperature rise.
- **Design Profiles:** Per-project electrical constraints — voltage rails, current limits, impedance targets, fabricator minimums.
- **Mental Model Compiler:** Requirements → schematic → placement → routing mental model pipeline.

### 3.2 Requirements-Driven Development

- **Functional Block Decomposition:** Circuits decomposed into subsystem blocks (Power, MCU, RF, Sensors, Audio, Display).
- **Power Tree Synthesis:** Voltage rail mapping with regulator sequencing.
- **Block-level specifications** with pin maps, device selections, and requirement traceability.

### 3.3 Component Intelligence & BOM

- **LCSC Parametric Search:** Component sourcing via LCSC with pricing, stock levels, and JLCPCB basic/extended part classification.
- **Lifecycle Auditing:** End-of-Life and Not-Recommended-for-New-Designs detection.
- **PCBA BOM Generation:** Fabrication-ready BOMs with LCSC C-codes and CPL centroid coordinates.
- **Multi-supplier architecture** with extensible supplier provider contracts.

### 3.4 EasyEDA Pro Integration

- **Bridge Discovery:** Automatic detection of running EasyEDA Pro desktop and web instances via localhost port scanning.
- **PCB Adapter:** Read and write operations for component placement, routing, copper zones, and design rules.
- **Session Safety:** Customer project quarantine — active projects are protected against uncontrolled automated mutation.

### 3.5 Mechanical-First Component Placement

- **Placement Hierarchy:** Mechanical integrity → Footprint integrity → Electrical integrity → Functional placement → Routability → Area optimisation.
- **Mechanical Envelopes:** Connector mating clearances, mounting hole standoffs, screw terminal access cones.
- **Functional Clustering:** Power, MCU, sensor, and RF/comms grouping with topological passive snapping.
- **Decoupling Proximity:** Automatic placement of decoupling capacitors adjacent to IC power pins.

### 3.6 Dense PCB Routing Intelligence

- **Grid-based Density Analysis:** Supply/demand modelling per routing layer with adaptive cell sizing.
- **Hotspot Detection:** Automatic identification of congested regions with measured causes and recommended strategies.
- **Fine-Pitch Escape Analysis:** Per-pad escape feasibility with direction classification (CLEAR / RESTRICTED / CRITICAL / NO_LEGAL_ESCAPE).
- **Corridor Discovery:** Identification of quiet routing channels adjacent to hotspots.

### 3.7 Pad Escape & Congestion Analysis

- **Pad Escape Engine:** Geometry-based escape feasibility for every pad, including fine-pitch BGA/QFN components.
- **Congestion Grid:** Layer-specific capacity modelling with corridor reservations and incremental updates.

### 3.8 Routing Priority & Recovery

- **6-Stage Priority Scheduling:** Ground → High-speed differential → Power → Analog → Low-speed digital → Non-critical I/O.
- **Routing Intelligence V2:** S-expression DSN serialiser, process supervisor, multi-pass execution.
- **Plateau Detection:** Monitors routing completion across passes; triggers recovery strategies when progress stalls.
- **Per-Pass Progress Reporting:** Wall-clock instrumentation across 20 canonical routing phases.
- **Recovery Strategies:** Rip-up and reroute, parameter adjustment, mode escalation.

### 3.9 Power Distribution & Trace-Width Intelligence

- **Rail Current Analysis:** Per-rail copper sizing proposals based on declared currents (fail-closed for undeclared rails).
- **Profile-Driven Widths:** `trace_width = max(profile_class, IPC_2152_width, fabricator_minimum)`.
- **Via Array Proposals:** Copper-to-layer transition via arrays for power distribution.
- **Voltage-Drop Estimation:** Analytical estimates based on trace geometry and copper properties.

### 3.10 Ground Planes & Copper Engineering

- **Reference Plane Allocation:** Based on actual physical stackup declarations.
- **Return-Path Continuity:** 2D polygon containment checks for unbroken reference planes under signal traces.
- **Island Detection:** Unconnected copper island identification and edge setback enforcement.
- **Zone Priority Hierarchy:** Power polygon zones with thermal relief control.
- **Grid-Based Ground Stitching:** Via array synthesis for ground connectivity.

### 3.11 Physical Connectivity Verification

- **Post-route connectivity check** verifying actual routed copper paths match netlist intent.
- **Unrouted net detection** with severity classification.

### 3.12 Design-Rule & Manufacturing Checks

- **DRC Engine:** Clearance, annular ring, solder mask dam, and fabricator minimum checks.
- **ERC Engine:** Netlist continuity, pin-type verification, floating input detection.
- **8 Fail-Closed Quality Gates:** Manufacturing readiness blocked by missing evidence; gates never pass on assumptions.

### 3.13 AI Model Orchestration

- **Multi-model router:** Dispatches tasks to local (Ollama) or cloud (Anthropic, OpenAI) models based on capability requirements.
- **Pi adapter:** Raspberry Pi integration for local inference orchestration.
- **Context Engine:** Structural indexing with token-budgeted task packs — deterministic retrieval for engineering data, BM25 for free-text.
- **Agent skill architecture** with capability declarations and tool routing.

### 3.14 Local Mission Control

- **Telemetry Server:** Zero-dependency HTTP server on port 49630 with in-browser real-time monitoring.
- **Server-Sent Events (SSE):** Streaming telemetry of engineering stages, DRC convergence, routing states.
- **Dashboard CLI:** `python desk.py dashboard` launches the monitoring cockpit.

### 3.15 Engineering Safety & Human Approval

- **Baseline Capture:** SHA-256 multi-domain hashing before any operation.
- **Single-Writer Canvas Mutex:** Reentrant locks prevent concurrent process collisions.
- **Atomic Rollback Checkpoints:** Pre-mutation checkpoints for instant rollback on verification failure.
- **Independent Readback:** Post-mutation canvas geometry re-read for physical truth verification.
- **Cryptographic Approval Tokens:** In Rework Mode, mutations require explicit human approval tokens (`RW-APR-XXXX`).
- **Customer Project Quarantine:** Active client projects protected against automated mutation.

---

## 4. Verification Status

> **Important:** DESK is actively developed. Many capabilities have been implemented and tested offline but have not yet been verified against live EasyEDA Pro hardware workflows.

| Capability | Status | Evidence |
|---|---|---|
| IPC-2152 Trace Width Sizing | `OFFLINE TESTED` | Physical copper formula tests (`test_profile_hardening.py`) |
| Routing Intelligence V2 & S-Expr DSN | `OFFLINE TESTED` | DSN parser, process supervisor, connectivity tests (`test_routing_*.py`) |
| Dense PCB Intelligence & Congestion | `OFFLINE TESTED` | Grid density, hotspot detection, escape analysis (`test_dense_intelligence.py`) |
| Pad Escape Analysis | `OFFLINE TESTED` | Feasibility classification per pad geometry (`test_routing_escape.py`) |
| Priority Net Routing | `OFFLINE TESTED` | 6-stage scheduling with dependency ordering (`test_routing_priority.py`) |
| Routing Recovery & Plateau Detection | `OFFLINE TESTED` | Multi-pass recovery strategies (`test_routing_recovery.py`, `test_routing_pass_tracker.py`) |
| Power Distribution Intelligence | `OFFLINE TESTED` | Rail analysis, copper sizing, via proposals (`test_power_distribution.py`) |
| Power-Aware Trace Widths | `OFFLINE TESTED` | Profile-driven width enforcement (`test_routing_width.py`) |
| Copper Planes & Return Paths | `OFFLINE TESTED` | Ray-casting polygon intersection (`test_copper_geometry.py`, `test_copper_engine.py`) |
| Physical Connectivity Verification | `OFFLINE TESTED` | Post-route netlist checking (`test_routing_connectivity.py`) |
| 8 Fail-Closed Quality Gates | `OFFLINE TESTED` | Blocks unrouted/shorted nets (`test_quality_fail_closed.py`) |
| Component Intelligence & BOM | `OFFLINE TESTED` | Parametric search, pricing, lifecycle (`test_ci_*.py`) |
| Mechanical-First Placement | `OFFLINE TESTED` | Hierarchy enforcement, clustering (`test_placement.py`, `test_phase6_placement_policy.py`) |
| Rework Mode & 8-Domain Audit | `OFFLINE TESTED` | Audit, baseline, planner, executor (`test_rework_*.py`) |
| Local Mission Control | `OFFLINE TESTED` | HTTP server on :49630 (`test_server.py`) |
| Context Engine | `OFFLINE TESTED` | Structural index, token-budgeted packs (`test_context.py`) |
| EasyEDA Pro Bridge Discovery | `OFFLINE TESTED` | Port scanning, session inspection (`test_easyeda_pro_integration.py`) |
| AI Orchestrator | `OFFLINE TESTED` | Multi-model routing, capability dispatch (`test_orchestrator.py`) |
| DRC / ERC Engines | `OFFLINE TESTED` | Rule-based checking (`test_core.py`) |
| **EasyEDA Pro Live Mutation** | `IMPLEMENTED — NOT LIVE VERIFIED` | Adapter signatures implemented; live execution on production boards quarantined |
| **FreeRouting + Java 25** | `INTEGRATION STARTED` | Freerouting 2.5.0 invoked with bundled JDK 25; SES output obtained; full proof-of-routing not yet confirmed |

### Outstanding Limitations

- **No live EasyEDA verification:** Board mutation through the EasyEDA Pro bridge has not completed a controlled live test cycle on a production board. The adapter code exists and is offline-tested but should not be considered production-verified.
- **FreeRouting integration is in progress:** Java 25 is installed locally and Freerouting 2.5.0 has been exercised, but the stopped-job SES proof-of-routing has not been confirmed as fully passing.
- **WATCH power-profile validation is incomplete:** Some engineering inputs (rail currents, thermal constraints) may require manual review before the power distribution output can be trusted for fabrication.
- **No universal PCB compatibility claim:** DESK has been developed and tested primarily against the WATCH (ESP32-S3 smartwatch) and sensor patch boards. Other board classes have not been validated.
- **No manufacturing approval claim:** DESK generates manufacturing readiness reports but does not replace fabricator review and approval.
- **Test count is approximate:** The repository contains 73 test files. Historical badge counts (e.g., "332 tests") may not reflect the current state; run the test suite to confirm.

---

## 5. Projects

DESK includes two reference engineering projects:

| Project | Description | Status |
|---|---|---|
| [**WATCH**](projects/WATCH/) | ESP32-S3-based smartwatch — 13 functional blocks, full BOM, placement plan, routing attempts | Active development; routing and power validation in progress |
| [**LIGHT**](projects/LIGHT/) | 230V mains LED dropper — single-block high-voltage design with placement plan | Block specification and placement complete |

---

## 6. Quick Start

### System Requirements

- **Operating System:** Windows 10/11 (recommended), Linux, or macOS.
- **Python:** 3.9 or higher.
- **Dependencies:** Zero external pip packages.
- **Optional:** Java 17+ for FreeRouting external routing engine.
- **Optional:** EasyEDA Pro (Desktop or Web) for live ECAD integration.

### Installation

```powershell
# Clone repository
git clone https://github.com/NijoP/DESK.git
cd DESK

# Verify installation (runs all automated tests)
python -m unittest discover -s tests -p "test_*.py"
```

### Essential CLI Commands

```powershell
# Check workbench status
python desk.py status

# Launch Local Mission Control dashboard
python desk.py dashboard

# Route a board with Routing Intelligence V2
python tools/route.py projects/WATCH --mode BALANCED

# Run routing benchmarks
python tools/routing_benchmarks.py

# Start Rework Mode (captures baseline snapshot)
python desk.py rework start projects/WATCH

# Audit existing PCB across 8 domains
python desk.py rework audit projects/WATCH

# Generate surgical repair plan
python desk.py rework plan projects/WATCH

# Evaluate quality gates and manufacturing readiness
python desk.py rework report projects/WATCH

# Component search
python tools/bom.py projects/WATCH

# PCB design-rule check
python tools/drc.py projects/WATCH
```

---

## 7. Documentation

### Architecture & Design
- [**Routing Intelligence V2**](docs/ROUTING_INTELLIGENCE_V2.md) — DSN parser, process supervisor, physical connectivity
- [**Dense PCB Intelligence**](docs/engineering/DENSE_PCB_INTELLIGENCE.md) — Hotspot detection, escape-first strategies
- [**Congestion Optimisation**](docs/engineering/CONGESTION_OPTIMISATION.md) — Layer-specific routing density
- [**Power Distribution Intelligence**](docs/engineering/POWER_DISTRIBUTION_INTELLIGENCE.md) — Rail analysis, copper sizing
- [**Copper Zone Generation**](docs/engineering/COPPER_ZONE_GENERATION.md) — Ground plane and zone management
- [**Placement-Routing Co-optimisation**](docs/engineering/PLACEMENT_ROUTING_COOPTIMISATION.md) — Mechanical-first placement with routing feedback

### Identity & Philosophy
- [**THE SENTINEL Character Identity**](docs/identity/DESK_CHARACTER_IDENTITY.md) — Engineering guardian persona
- [**Biomimetic Design Philosophy**](docs/identity/BIOMIMETIC_DESIGN_PHILOSOPHY.md) — Homeostasis, immunology, wound healing in EDA
- [**Biological to Engineering Mapping**](docs/identity/BIOLOGICAL_TO_ENGINEERING_MAPPING.md) — Source-level verification

### Ecosystem Integration
- [**EasyEDA Pro Integration**](docs/ecosystem/02_EASYEDA_PRO_INTEGRATION.md) — Bridge architecture, API map
- [**LCSC Integration**](docs/ecosystem/LCSC_INTEGRATION_ARCHITECTURE.md) — Component sourcing
- [**JLCPCB Manufacturing**](docs/ecosystem/JLCPCB_MANUFACTURING_ARCHITECTURE.md) — Fabrication and assembly

### Product Assessment
- [**Capability Matrix**](docs/product_assessment/PRODUCT_CAPABILITY_MATRIX.md) — Full feature status
- [**Hardware Compatibility**](docs/product_assessment/HARDWARE_COMPATIBILITY_MATRIX.md) — Tested board classes
- [**Software Architecture Assessment**](docs/product_assessment/SOFTWARE_ARCHITECTURE_ASSESSMENT.md) — Code quality and structure

### Rework Mode
- [**Rework Mode Overview**](docs/rework/01_REWORK_MODE_OVERVIEW.md) — 16-part technical specification for PCB recovery

### Operational
- [**Getting Started**](docs/getting-started.md) — First-time setup guide
- [**Local Mission Control**](docs/local-dashboard.md) — Telemetry dashboard operation
- [**Routing Benchmark Report**](docs/ROUTING_BENCHMARK_REPORT.md) — Performance metrics

### Engineering Learning
- [**Learning Repository**](learning/README.md) — Incidents, lessons, and known failure patterns

---

## 8. Engineering Safety

Hardware engineers are rightly protective of their layout artwork. DESK implements strict safeguards:

1. **Baseline Capture:** Multi-domain SHA-256 hashes record every footprint, trace, and copper boundary before any operation.
2. **Single-Writer Mutex:** Reentrant canvas locks prevent concurrent process collisions.
3. **Atomic Rollback:** Checkpoints stored before every mutation, enabling instant rollback on failure.
4. **Independent Readback:** Geometry re-read from the CAD engine to confirm physical truth.
5. **Fail-Closed Gates:** Missing verification evidence blocks manufacturing release.
6. **Human Approval Required:** Rework mutations require explicit cryptographic approval tokens.

---

## 9. Contributing

We welcome contributions from electronics engineers and software developers:

1. All code must use **100% Python standard library** (zero external pip packages).
2. Base trace width and clearance rules on physical equations or documented fabricator standards.
3. Run all automated tests before submitting: `python -m unittest discover -s tests -p "test_*.py"`.
4. See [AGENTS.md](AGENTS.md) for development conventions and agent-system architecture.

---

## 10. License

[MIT License](LICENSE) — See [NOTICE](NOTICE) for attribution.

---

<p align="center">
  <b>DESK is actively developed. Some live hardware workflows still require validation.</b><br>
  <b>A healthy PCB is not merely a board without visible errors. It is a design whose intent, structure, and physical constraints remain intact.</b><br>
  <b>DESK exists to protect that integrity.</b>
</p>
