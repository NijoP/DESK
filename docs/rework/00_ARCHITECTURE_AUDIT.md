# DESK REWORK MODE: ARCHITECTURE AUDIT & EXTENSION BLUEPRINT

**Document ID:** `docs/rework/00_ARCHITECTURE_AUDIT.md`  
**Date:** 2026-11-09  
**Author:** Principal Software Architect & Systems Engineering Agent  
**Target Repository:** https://github.com/NijoP/DESK  
**Status:** Approved for Implementation  

---

## 1. Executive Summary

This architecture audit evaluates the existing DESK platform against the requirements of **Rework Mode**—a first-class engineering recovery and completion operating mode designed to take an existing, unfinished electronics design and bring it to verified manufacturing readiness without losing original engineering intent.

The core philosophy of Rework Mode is **Preserve Existing Engineering Intent**:
- An unfinished PCB already contains valuable engineering decisions (placement anchors, thermal groupings, high-speed routes, tuned copper pours).
- DESK must **never rebuild an entire board from scratch** when only surgical fixes are required.
- DESK distinguishes strictly between:
  1. *Correct and accepted work* (protected from modification)
  2. *Incomplete work* (unconnected nets, missing bypass caps)
  3. *Incorrect work* (clearance violations, pin mapping mismatches)
  4. *Unknown work* (unspecified power rail current, missing fabricator rules)
  5. *Deliberate design exceptions* (intentional no-connects, DNI components, approved test pads)

---

## 2. Audit of Existing DESK Subsystems

| Subsystem | Existing Path | Current Capability | Rework Mode Integration & Reuse |
|---|---|---|---|
| **ECAD Bridge & Ports** | `desk/bridge.py` | 5-tier port discovery (EDA_PORT, memory cache, disk cache, default 49620, concurrent probe across 49620..49629), window tracking (`_find_window_for_project`), `BridgeSession`, `SessionRegistry`. | **Reuse 100%.** Extend session validation to bind exact project identity (`ProjectBinding`), preventing cross-project mutation. |
| **Atomic Lock & Journal** | `desk/ops.py` | Atomic cross-process lock via `O_CREAT \| O_EXCL`, Windows & POSIX PID liveness, PID start-time recycling detection, verified owner release, operation classification (`OP_NON_IDEMPOTENT_MUTATION`), durable journal (`ops.jsonl`), pending recovery. | **Reuse 100%.** Wrap every rework mutation in `write_op(project, "rework_repair", repair_id)` ensuring strict single-writer execution. |
| **PCB Snapshot & Revisions** | `desk/snapshot.py` | Spatial 2D hash grid (`SpatialGridIndex`), `IndexedPCBSnapshot` with 5 domain revision fingerprints (`geometry_rev`, `connectivity_rev`, `stackup_rev`, `copper_rev`, `rules_rev`), composite `fingerprint`, incremental updates. | **Reuse 100%.** Baseline capture will record the immutable baseline snapshot and detect external modifications in EasyEDA Pro outside DESK. |
| **Atomic Checkpoints** | `desk/runtime/checkpoints.py` | Atomic JSON state dumps (`chk_<ts>_<stage>_<hash>.json`), atomic replace via `.tmp`, pruning, history recovery. | **Reuse 100%.** Every repair mutation saves a checkpoint before applying changes to live ECAD. |
| **Quality & Manufacturing Gates** | `desk/quality.py` | 5-state lifecycle (`PASS`, `FAIL`, `UNKNOWN`, `NOT_RUN`, `STALE`), `VerificationEvidence` with revision/profile matching, 8 hard non-negotiable gates, weighted scorecard. | **Reuse 100%.** Authoritative engine for manufacturing readiness assessment (`READY_FOR_MANUFACTURING`, `CONDITIONALLY_READY`, `NOT_READY`). |
| **DRC & Recovery Planner** | `desk/drc_engine.py` | Structured `DRCParser`, `FailureDiagnoser`, `RecoveryPlanner` (identifies conflicting tracks, suggested layer shifts, escape vias). | **Reuse 100%.** Integrated into Audit Domain H (DRC and Manufacturing) and repair planning. |
| **6-Stage Routing Engine** | `desk/router.py` | Specctra DSN tuning, IPC-2152 dynamic trace width sizing, `NativeMazeRouter`, differential pair routing, `RoutingConvergenceController`. | **Reuse 100%.** Used for surgical net routing without disturbing protected accepted tracks. |
| **Copper & Ground Engine** | `desk/copper.py` | 2D ray-casting polygon boundary checks, 3-way keepout collision, return-path continuity verification, zone revision tracking. | **Reuse 100%.** Used for return-path continuity audit, copper repour tracking, and ground plane repair. |
| **EventBus & Telemetry** | `desk/runtime/events.py` | Thread-safe `EventBus`, bounded ring buffer, subscriber dispatch, ISO timestamps, `Last-Event-ID` replay. | **Reuse 100%.** Emit structured `rework.*` lifecycle events. |
| **State Projection** | `desk/runtime/projection.py` | 12 canonical engineering stages, honest weighted progress, credential redaction, log stream. | **Extend.** Add rework session summary projection (active session, issue counts, repair queue). |
| **Local Mission Control** | `desk/runtime/server.py` | Threaded HTTP/SSE server on port `49630`, loopback security, REST API (`/api/status`, `/api/execution`, `/api/events/live`). | **Extend.** Add `/api/rework/session`, `/api/rework/issues`, `/api/rework/plan` endpoints. |
| **Release & Manufacturing Verification** | `desk/release.py`, `tools/release.py` | BOM check, pick-and-place coordinate validation, Gerber layer check, manifest checksums. | **Reuse 100%.** Final release assessment verification. |

---

## 3. Missing Capabilities for Rework Mode

The audit identifies the following new components required:

1. **Rework Session Lifecycle (`desk/rework/session.py`):**
   - Explicit state machine: `IDLE` $\to$ `REWORK_REQUESTED` $\to$ `INTAKE` $\to$ `CONNECTING` $\to$ `IDENTITY_CONFIRMATION` $\to$ `BASELINE_CAPTURE` $\to$ `ENGINEERING_AUDIT` $\to$ `ISSUE_REVIEW` $\to$ `REPAIR_PLANNING` $\to$ `AWAITING_APPROVAL` $\to$ `REPAIR_EXECUTION` $\to$ `READBACK` $\to$ `VERIFICATION` $\to$ `RELEASE_ASSESSMENT` $\to$ `COMPLETED` / `NEEDS_REVIEW` / `NOT_READY`.
   - Execution Policies: `AUDIT_ONLY`, `GUIDED_REWORK`, `SUPERVISED_REWORK`.
   - Session directory persistence under `projects/<P>/state/rework/<SESSION_ID>/`.

2. **Project Identity Binding (`desk/rework/connection.py`):**
   - Verifies active window, active project UUID, PCB UUID, schematic UUID, and EasyEDA Pro application state.
   - Detects project switching and window focus changes; pauses execution if the active project does not match.

3. **Multi-Domain Engineering Audit Engine (`desk/rework/audit.py`):**
   - Implements the 8 distinct audit domains (Requirements, Schematic/Netlist, Components/Footprints, Mechanical Placement, PCB Connectivity, Power/Thermal, Copper/Ground, DRC/Manufacturing).
   - Generates typed `Issue` records with unique IDs (`RW-0001`), severity, affected objects, and physical evidence.

4. **Dependency-Aware Surgical Repair Planner (`desk/rework/planner.py`):**
   - Categorizes geometry into `PROTECTED`, `ACCEPTED`, `MODIFIABLE`, `INVALID`, `UNKNOWN`.
   - Constructs an acyclic dependency graph of repairs.
   - Generates cryptographically secure, session- and revision-bound approval tokens (`RW-APR-XXXX`).

5. **Controlled Repair Executor with Mandatory Readback (`desk/rework/executor.py`):**
   - Executes mutations under single-writer lock (`desk/ops.py`).
   - Implements mandatory readback of modified tracks, vias, components, and copper.
   - Evaluates verification criteria immediately post-mutation.

6. **Manufacturing Readiness Assessor (`desk/rework/readiness.py`):**
   - Evaluates the 8 fail-closed hard quality gates against the final PCB revision.
   - Emits definitive readiness status (`READY_FOR_MANUFACTURING`, `CONDITIONALLY_READY`, `NOT_READY`, `INCOMPLETE`).

7. **Natural-Language Agent Skill (`.agents/skills/rework-mode/SKILL.md`):**
   - Provides PyAgent and coding assistants with procedural workflows for conversational intake, audit review, and approval handling.

---

## 4. Safety Constraints & Invariants

1. **Zero External Pip Dependencies:** Pure Python standard library (`socket`, `http.server`, `json`, `hashlib`, `urllib`).
2. **Single-Writer Mutex:** Never allow concurrent live writers. All mutations are serialized via `desk/ops.py`.
3. **Fail-Closed Evidence:** Unexecuted or missing checks remain `NOT_RUN` or `UNKNOWN` and can never turn into `PASS`.
4. **Non-Negotiable Readback:** API success is never accepted as proof of physical geometry. Every mutation requires explicit readback.
5. **Customer Project Protection:** Automated live ECAD mutations on active customer projects (`WATCH`, `BEEBOX`) are strictly quarantined. Tests run only against fixtures and disposable projects.
6. **Immutable Baseline & Revision Detection:** Baseline snapshots are immutable. If the user edits the board in EasyEDA Pro outside DESK, revision mismatch is detected and affected plans are invalidated.

---

## 5. Architectural Directory Layout

```text
desk/
├── rework/                         # Rework Mode Engine Package
│   ├── __init__.py                 # Package exports & public API
│   ├── mode.py                     # Mode registration & natural-language intent recognition
│   ├── session.py                  # Durable ReworkSession & state machine lifecycle
│   ├── connection.py               # ECAD connection & project identity binding
│   ├── baseline.py                 # Baseline capture & multi-domain revision fingerprinting
│   ├── audit.py                    # 8-domain engineering audit & issue inventory
│   ├── planner.py                  # Issue dependency graph, surgical repairs & approval tokens
│   ├── executor.py                 # Single-writer mutation execution, readback & verification
│   └── readiness.py                # Fail-closed manufacturing readiness evaluation & report
```

All integration points with existing systems are verified and documented. Implementation proceeds immediately.
