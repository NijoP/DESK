# Local Mission Control & Real-Time Monitoring

DESK includes a built-in, local monitoring dashboard that runs directly on your machine with **zero external dependencies** (100% Python standard library).

When you start an engineering execution—such as schematic synthesis, component selection, placement, routing, copper generation, or manufacturing verification—you can open a local browser tab and observe real-time engineering telemetry, stage progress, DRC gates, and system resource consumption.

```text
Default Preferred URL: http://127.0.0.1:49630
```

---

## 1. Port Architecture & Collision Avoidance

To prevent interference between DESK's ECAD Bridge and Mission Control:
- **EasyEDA Pro Bridge Port Range:** `49620..49629` (reserved for IPC bridge communications).
- **Mission Control Port Range:** `49630..49640` (dedicated exclusively to the monitoring HTTP/SSE server).

If port `49630` is occupied, DESK automatically attempts the next available port sequentially (`49631..49640`) and prints the active URL to your terminal.

---

## 2. Quick Launch Commands

Start or inspect the dashboard from your terminal:

```bash
# Launch Mission Control and open in default browser (port 49630)
python desk.py dashboard

# Launch on a specific custom port
python desk.py dashboard --port 49635

# Start background HTTP and SSE server without auto-opening browser
python desk.py serve --port 49630

# Display formatted terminal status snapshot
python desk.py status

# Output machine-readable JSON status matching /api/status
python desk.py status --json
```

During any engineering run (e.g. `desk run`, `desk pipeline`, or benchmarks), DESK emits the live URL directly:
```text
[DESK] Mission Control live at http://127.0.0.1:49630
```

---

## 3. REST API Reference

All endpoints are strictly **read-only** (`GET` and `OPTIONS` only) and bound exclusively to loopback (`127.0.0.1`). Any mutating HTTP methods (`POST`, `PUT`, `DELETE`) return `405 Method Not Allowed`.

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Serves the single-page HTML5/CSS/JS Mission Control interface |
| `/api/status` | `GET` | Overall system status, project, active profile, bridge port, stages, DRC gates, and hardware metrics |
| `/api/execution` | `GET` | Current active execution session, stage progress percentage, elapsed duration, active task |
| `/api/events` | `GET` | Paginated or recent execution event stream (`?limit=100&since=<id>`) |
| `/api/events/live` | `GET` | Server-Sent Events (SSE) live push stream with automatic client reconnection |
| `/api/v1/health` | `GET` | Service health status and version verification |
| `/api/v1/metrics` | `GET` | Host and process hardware telemetry (CPU cores, RAM MB, memory pressure) |
| `/api/v1/projects` | `GET` | Discovers available hardware projects under `projects/` |

---

## 4. Server-Sent Events (SSE) Protocol

Mission Control streams live execution events over standard HTTP using SSE (`text/event-stream`):

```http
GET /api/events/live HTTP/1.1
Host: 127.0.0.1:49630
Accept: text/event-stream
Last-Event-ID: evt_03a9f1b2c4d5
```

### Protocol Features
- **Replay on Reconnection:** If the client connection drops, the browser sends `Last-Event-ID`. The server replays missed events from its bounded history buffer.
- **Heartbeats:** Sends periodic `: heartbeat` comments every 10 seconds to maintain alive state through local proxies.
- **Backpressure & Bounded Memory:** Event replay history is strictly capped (last 500-1000 events) to prevent memory growth during long runs.
- **Decoupled Execution:** If the browser tab is closed or disconnected, background routing, placement, or verification runs to completion without interruption or socket exceptions.

---

## 5. Dashboard Interface Overview

The UI provides a dense, real-time electronics engineering cockpit:

### A. Executive Header
- **Active Project:** Path of the board currently being engineered (`projects/WATCH`).
- **Execution State:** `IDLE`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`.
- **Connection Status Pill:** Real-time stream state (`CONNECTED`, `RECONNECTING`, `OFFLINE`).
- **Theme Toggle:** Dark (default) and Light engineering color palettes.

### B. High-Density Metrics Grid
- **Overall Progress:** Real, weighted percentage calculated strictly from verified stage task units (no fake timers).
- **Active Stage:** Currently executing stage and sub-task activity.
- **Hardware Telemetry:** Physical process RAM, available system RAM, logical CPU cores, and memory tier (`LOW`, `NORMAL`, `HIGH`).

### C. 12-Stage Engineering Pipeline
1. `requirement_ingestion`: Ingest mechanical dimensions, power rails, net budget.
2. `schematic_intelligence`: Netlist extraction and hierarchical block decomposition.
3. `component_intelligence`: BOM MPN resolution and LCSC inventory validation.
4. `electrical_verification`: ERC pin rules, voltage compatibility, power tree.
5. `pcb_ingestion`: Outline geometry, layer stackup, copper thickness.
6. `placement_intelligence`: Mechanical anchors, decoupling capacitors, thermal clusters.
7. `routing_preparation`: Net priority ordering and BGA/QFN escape stubs.
8. `pcb_routing`: Deterministic maze routing, differential pairs, IPC-2152 power widths.
9. `copper_generation`: Return-path ground planes and power copper pours.
10. `drc_verification`: Clearance checks, short-circuit validation, annular rings.
11. `manufacturing_verification`: 8 fail-closed hard gates and JLCPCB DFM validation.
12. `engineering_report`: Sign-off summary, diagnostic report, release archive.

### D. Acceptance & DRC Gate Panel
- **8 Hard Quality Gates:** Gate 1 (Shorts), Gate 2 (Unconnected Nets), Gate 3 (Clearances), Gate 4 (Critical Nets), Gate 5 (Stackup Integrity), Gate 6 (Return-Path Continuity), Gate 7 (IPC-2152 Power Widths), Gate 8 (Manufacturing DFM).
- **Fail-Closed Guarantee:** Unrun verification checks remain `NOT_RUN` and never turn into `PASS`.

### E. Diagnostic Log Stream & Telemetry
- Real-time scrollable log stream.
- Severity filtering (`ALL`, `INFO`, `WARNING`, `ERROR`).
- One-click log copy to clipboard.
- Diagnostic report download as JSON.
- **Automatic Redaction:** API keys, authentication tokens, passwords, and private paths are masked (`[REDACTED]`).

---

## 6. Localhost Security Model

Mission Control is an **offline, local-only** monitoring surface:
1. **Loopback Binding Only:** Binds strictly to `127.0.0.1`. Never listens on `0.0.0.0` or external network adapters.
2. **Host / Origin Validation:** Rejects non-localhost `Host` or `Origin` headers with `403 Forbidden` to prevent DNS rebinding or CSRF attacks.
3. **Path Traversal Protection:** Rejects paths containing `..`, null bytes, or Windows drive delimiters with `400 Bad Request`.
4. **Strictly Read-Only:** Zero mutating endpoints. Web clients cannot trigger writes, modify files, or alter engineering decisions.
5. **Zero Credential Leakage:** API responses recursively sanitize sensitive keys before transmission.

---

## 7. Browser Compatibility & Keyboard Shortcuts

- **Compatibility:** Modern evergreen browsers (Chrome, Edge, Firefox, Safari) supporting CSS Grid and Server-Sent Events.
- **Shortcuts:**
  - `T` — Toggle Dark / Light theme.
  - `L` — Focus log search input.
  - `C` — Copy logs to clipboard.
  - `D` — Download diagnostic report JSON.
