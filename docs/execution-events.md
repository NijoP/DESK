# Event-Driven Execution Monitoring Architecture

This document specifies the event streaming primitives, message schemas, REST endpoints, and state projection architecture powering DESK Mission Control.

---

## 1. Event Model & Schema

All operations in DESK emit structured lifecycle events onto a centralized, thread-safe in-memory `EventBus` (`desk/runtime/events.py`):

```json
{
  "event_id": "evt_7f8a9b0c1d2e",
  "execution_id": "exec_1794163867_28696",
  "project_id": "projects/WATCH",
  "timestamp": 1794163870.125,
  "iso_timestamp": "2026-11-09T00:31:10.125000+00:00",
  "event_type": "stage.progress",
  "stage": "pcb_routing",
  "task": "route_critical_nets",
  "task_id": "tsk_route_pass_4",
  "status": "RUNNING",
  "progress": 75.0,
  "message": "Routed 36 of 48 nets; optimizing clearance",
  "metrics": {
    "nets_completed": 36,
    "total_nets": 48,
    "vias_count": 142
  },
  "artifacts": [
    { "type": "checkpoint", "id": "chk_1794163870_routing_a1b2c3.json" }
  ],
  "error": null
}
```

---

## 2. Event Types Catalog

| Event Type | Emitted When | Typical Payload / Attributes |
|---|---|---|
| `stage.start` | An engineering stage begins execution | `stage`, `message`, `status="RUNNING"` |
| `stage.progress` | Measurable subtasks advance | `progress` (0–100%), `message`, `metrics` |
| `stage.complete` | A stage finishes and passes validation | `duration_s`, `artifacts`, `status="COMPLETED"` |
| `stage.fail` | A stage halts on hard DRC or rule violation | `error`, `status="FAILED"` |
| `stage.skip` | An optional stage is skipped by design profile | `status="SKIPPED"`, `message` |
| `task.queued` | A task is admitted to the scheduler queue | `task_id`, `priority`, `task_type` |
| `checkpoint.saved`| An atomic state snapshot is written to disk | `checkpoint_id`, `state_hash` |
| `results.update` | Physical artifacts or DRC counts change | `tracks_generated`, `drc_violations`, `quality_gates` |
| `log.info` / `log.warn` / `log.error` | Informational or diagnostic logging | `level`, `message` (redacted), `stage` |

---

## 3. Server-Sent Events (SSE) Stream

### Endpoint: `GET /api/v1/events/stream`
Clients connect via standard HTML5 `EventSource`.

#### Features:
1. **Zero-Configuration Handshake:**
   ```http
   GET /api/v1/events/stream HTTP/1.1
   Host: 127.0.0.1:49620
   Accept: text/event-stream
   ```
2. **Event Delivery:**
   ```text
   id: evt_7f8a9b0c1d2e
   event: message
   data: {"event_id": "evt_7f8a9b0c1d2e", "event_type": "stage.progress", "progress": 75.0, ...}
   ```
3. **Automatic Reconnection & History Replay:**
   When re-establishing connection after a network blip or browser refresh, the client passes `Last-Event-ID`:
   ```http
   Last-Event-ID: evt_7f8a9b0c1d2e
   ```
   The server immediately replays any missed events from its bounded history buffer.
4. **Periodic Keepalive Heartbeats:**
   Every 15 seconds of inactivity, the server transmits a lightweight comment line:
   ```text
   : heartbeat
   ```
5. **Non-Blocking Clean Teardown:**
   When the client closes the connection, the listener is unregistered cleanly without raising unhandled socket exceptions or stalling active calculations.

---

## 4. REST API Endpoints Reference

All endpoints are strictly read-only and return JSON formatted data.

| Endpoint | Method | Description |
|---|---|---|
| `/` | `GET` | Serves the Mission Control dashboard single-page web app. |
| `/api/v1/health` | `GET` | Health check returning service status, version, and uptime. |
| `/api/v1/status` | `GET` | Consolidated state summary (overall progress, stage statuses, metrics, results). |
| `/api/v1/projects` | `GET` | Discovers available project directories in `projects/`. |
| `/api/v1/metrics` | `GET` | Physical hardware telemetry (RAM, CPU cores, memory pressure, resource tier). |
| `/api/v1/executions` | `GET` | Active and recent execution sessions. |
| `/api/v1/executions/{id}` | `GET` | Full execution record for specific session ID. |
| `/api/v1/executions/{id}/events` | `GET` | Chronological activity feed (supports `?limit=100`). |
| `/api/v1/executions/{id}/logs` | `GET` | Sanitized diagnostic logs (supports `?level=INFO` and `?search=GND`). |
| `/api/v1/executions/{id}/artifacts` | `GET` | Checkpoint references and generated release files. |
| `/api/v1/events/stream` | `GET` | Real-time Server-Sent Events (SSE) push stream. |

---

## 5. Restart Recovery & Reconciliation

If DESK is shut down while an operation is in-flight:
1. The state file `projects/<P>/state/execution_state.json` records the active process ID (`pid`) and status (`RUNNING`).
2. Upon restart, `ExecutionProjection` compares the recorded `pid` with the current running process.
3. If the process is dead, DESK **honestly reconciles the status as `INTERRUPTED`**.
4. The evidence state is flagged `STALE`, and incomplete stages are marked `INTERRUPTED`.
5. Missing verification evidence is **never assumed to have passed**. Safe recovery is performed explicitly via `python desk.py recover projects/<P>`.
