# 01 — DESK Local Mission Control & Telemetry Pre-Implementation Audit

**Date:** 2026-11-09  
**Repository:** `https://github.com/NijoP/DESK`  
**Host Environment:** Windows 11 (x64), Python 3.11+, Node.js v24.21.0, Git 2.55.0  

---

## 1. Existing Architecture & Entry Points

- **Primary Language & Runtime:** Pure Python 3.9+ with zero external mandatory dependencies. All internal tools and engines run standard library Python (`http.server`, `threading`, `queue`, `json`, `socket`, `time`).
- **Autonomous Task Scheduling:** `desk/runtime/scheduler.py` manages a bounded priority queue with worker threads and concurrency limits.
- **State Machine:** `desk/runtime/task_state.py` defines 12 discrete lifecycle states (`QUEUED`, `PREPARING`, `RUNNING`, `PAUSED_RESOURCE`, `PAUSED_EXTERNAL`, `NEEDS_DECISION`, `RECOVERING`, `VALIDATING`, `COMPLETED`, `FAILED`, `UNKNOWN`, `CANCELLED`).
- **Telemetry & Hardware Detection:** `desk/runtime/resource_profile.py` measures real system memory, CPU cores, process RAM, and resource pressure cross-platform without third-party libraries.
- **Atomic Persistence & Journaling:** `desk/ops.py` maintains an append-only transaction journal (`projects/<P>/state/ops.jsonl`) and OS-level write locks. `desk/runtime/checkpoints.py` provides atomic snapshots.
- **CLI Entry Points:**
  - `tools/desk.py`: Discovers tools, manages credentials, audits settings, recovers dirty operations.
  - `tools/ctx.py`: Context engine for agent intake and brief generation.

---

## 2. Existing Progress Reporting Capabilities

- **In-Memory Event Bus (`desk/runtime/events.py`):**  
  `EventBus` emits events with `event_type`, `task_id`, `timestamp`, and `payload`. However, events are currently volatile in-memory and lack HTTP delivery, durable cross-session replay, and SSE streaming.
- **Operation Journal (`ops.jsonl`):**  
  Logs phase transitions (`begin`, `end`, `fail`) with millisecond timestamps and operation IDs.
- **Telemetry Collector (`desk/profiler.py`):**  
  Records operation latency, cache hits, and execution times to `.desk_learn/runs.jsonl`.

---

## 3. Missing Execution Telemetry & Gaps

1. **No Client-Facing Web UI:** No local HTTP server exists to visualize live operations in real time.
2. **Missing Real-Time SSE Stream:** Clients cannot stream live state without manually polling disk files.
3. **No Centralized State Projection:** While events and journals exist, there is no consolidated projection aggregating the 12 engineering stages (from Gate R to M6 Manufacturing release).
4. **Disconnected Execution Tracking:** CLI scripts (`tools/route.py`, `tools/verify.py`, `tools/build.py`) log to stdout but do not uniformly broadcast step-by-step progress to a monitoring layer.
5. **No Localhost Security Layer:** No origin validation, path sanitization, or port collision recovery for local server binding.

---

## 4. Suitable Integration Points

1. **`desk/runtime/events.py` Enhancement:** Extend `Event` schema to match the standard contract (`event_id`, `execution_id`, `project_id`, `stage`, `task`, `status`, `progress`, `message`, `metrics`, `artifacts`, `error`). Add a bounded replay buffer supporting `Last-Event-ID`.
2. **New Module `desk/runtime/server.py`:** A zero-dependency, multi-threaded HTTP server utilizing `http.server.ThreadingHTTPServer` bound to `127.0.0.1:49620` with port collision fallback.
3. **New Module `desk/runtime/projection.py`:** An in-memory and disk-reconciled state projector that models the 12 canonical engineering stages and calculates honest progress from measurable task units.
4. **Dashboard Frontend (`desk/ui/assets/index.html`):** A zero-dependency, high-density, accessible single-page web app with SSE auto-reconnect, dark/light themes, stage visualization cards, active task gauges, log viewers, and engineering artifact summaries.
5. **CLI Integration (`tools/desk.py`):** Add `desk dashboard`, `desk serve`, `desk status`, and `desk status --json`.
6. **Execution Instrumentation:** Wire the 12 engineering pipeline stages into the execution event bus.

---

## 5. Implementation Plan

```
Step 1: Event System & State Projection
  ├── Extend desk/runtime/events.py with standardized event schemas & replay buffer
  └── Create desk/runtime/projection.py to maintain live and durable execution state

Step 2: Local HTTP Server & SSE Engine
  ├── Implement desk/runtime/server.py (REST API + SSE streaming)
  ├── Enforce localhost-only security, origin checks, port collision resolution
  └── Add persistent checkpoint reconciliation upon restart

Step 3: Client Mission Control Web Dashboard
  └── Build desk/ui/assets/index.html (modern, responsive, dark/light engineering UI)

Step 4: CLI Integration
  └── Update tools/desk.py to provide `dashboard`, `serve`, and `status` commands

Step 5: Pipeline Telemetry Wiring
  └── Instrument schematic, routing, placement, DRC, and manufacturing operations

Step 6: Comprehensive Automated Tests
  └── Test event bus, SSE streaming, API security, state projection, and crash recovery

Step 7: Firstmate-Style README & Documentation Overhaul
  └── Reorganize README.md, docs/local-dashboard.md, docs/execution-events.md, etc.
```

---

## 6. Files Expected to Change / Be Added

- **Modified:**
  - `desk/runtime/events.py` (enhanced schema, bounded replay buffer)
  - `tools/desk.py` (added `serve`, `dashboard`, `status` subcommands)
  - `README.md` (complete Firstmate-style restructuring)
- **New Files:**
  - `desk/runtime/server.py` (local HTTP server + SSE engine)
  - `desk/runtime/projection.py` (execution state projector & stage tracker)
  - `desk/ui/assets/index.html` (single-page dashboard)
  - `docs/local-dashboard.md` (dashboard reference guide)
  - `docs/execution-events.md` (event-driven monitoring architecture)
  - `tests/test_server.py` (HTTP API, SSE, security, and lifecycle tests)
  - `tests/test_events.py` (event bus, ordering, queue saturation, and replay tests)
  - `tests/test_projection.py` (stage tracking, progress calculation, restart recovery)
