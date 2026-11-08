# System Architecture & Technical Index

DESK transforms unstructured hardware requirements into verified, manufacturing-ready schematics and PCB designs using deterministic engineering engines, structured mental models, and local execution monitoring.

---

## 1. High-Level Architecture

```text
Client / Hardware Engineer
       │
       ▼
DESK CLI & Tools (desk.py, tools/*.py)
       │
       ▼
Engineering Orchestrator & Task Scheduler (desk/runtime/scheduler.py)
       │
       ├─► M1: Schematic & Component Intelligence (desk/component_intelligence/)
       ├─► M2: Mechanical & Placement Intelligence (desk/placement.py)
       ├─► M3: Autonomous 6-Stage Priority Router (desk/router.py)
       ├─► M4: Copper Plane & Polygon Synthesizer (desk/copper.py)
       ├─► M5: DRC & Electrical Clearances (desk/quality.py)
       └─► M6: Fail-Closed Quality Acceptance Gates (desk/quality.py)
       │
       ▼
Execution Event Bus (desk/runtime/events.py)
       │
       ▼
State Projection Engine (desk/runtime/projection.py)
       │
       ▼
Local Mission Control HTTP & SSE Server (desk/runtime/server.py)
       │
       ▼
Client Web Browser Dashboard (http://127.0.0.1:49620)
```

---

## 2. Core Subsystems

1. **Engineering Design Profile (`desk/profile.py`):** Authoritative contract defining physical layer stackups, dielectric constants, and IPC-2152 trace width formulas.
2. **Mental-Model Compiler (`desk/mental/compiler.py`):** Compiles high-level engineering models (M1–M6) into compact, budgeted policies.
3. **Autonomous 6-Stage Router (`desk/router.py`):** Prioritizes Ground -> Interface -> High-Speed -> Controls -> Power -> General nets.
4. **Copper & Ground Engine (`desk/copper.py`):** Synthesizes reference planes, power polygons, thermal spokes, and stitching vias.
5. **Fail-Closed Verification Engine (`desk/quality.py`):** Enforces 8 hard acceptance gates with zero exceptions.
6. **Local Mission Control (`desk/runtime/server.py`):** Read-only localhost HTTP server with real-time SSE streaming.
7. **Development Memory Optimization (`docs/development_memory/`):** Backpass gradient descent for continuous agent learning.

---

## 3. Technical Documentation Index

- [00_REQUIREMENTS.md](00_REQUIREMENTS.md) — 10-dimension requirement intake specification (Gate R).
- [00b_COMPONENT_SELECTION.md](00b_COMPONENT_SELECTION.md) — BOM comparison matrix and part justification (Gate B).
- [01_MENTAL_MODEL.md](01_MENTAL_MODEL.md) — Mental models M1 through M6 theory and pipeline gates.
- [03_BLOCK_WORKFLOW.md](03_BLOCK_WORKFLOW.md) — Procedural loop for schematic block creation.
- [04_PLACEMENT.md](04_PLACEMENT.md) — Physical placement invariants and thermal clustering.
- [05_ROUTING.md](05_ROUTING.md) — 6-stage net scheduling and Specctra DSN tuning.
- [06_EASYEDA_API.md](06_EASYEDA_API.md) — Socket bridge integration and API discovery.
- [07_CONTEXT_ENGINE.md](07_CONTEXT_ENGINE.md) — Dynamic context querying (`tools/ctx.py`).
- [08_LEARNING_ENGINE.md](08_LEARNING_ENGINE.md) — Developer transcript analysis and telemetry.
- [09_STATUS.md](09_STATUS.md) — Implementation and capability status ledger.
- [LIVE_INTEGRATION_CHECKLIST.md](LIVE_INTEGRATION_CHECKLIST.md) — Pre-flight quarantine and safety rules for live EDA.
- [local-dashboard.md](local-dashboard.md) — Local Mission Control web dashboard guide.
- [execution-events.md](execution-events.md) — Event streaming and SSE protocol reference.
- [getting-started.md](getting-started.md) — Quick start and project initialization guide.
