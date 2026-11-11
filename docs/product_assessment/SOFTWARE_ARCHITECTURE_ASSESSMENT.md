# Software Architecture Assessment (Team B)

**Scope:** read-only audit of runtime, concurrency, IPC, memory systems, Mission Control, error handling and reliability. Paths relative to the repository root; every claim cites `file:line`.
**Date:** 2026-11-11. **Owner:** Principal Software Architect.
**Status note:** items marked *FIXED (M1)* were implemented in milestone 1 after this audit; see `PRODUCT_MANAGER_REPORT.md`.

## 1. Task lifecycle

- **Three disjoint state vocabularies exist, none wired to real work.**
  - `desk/runtime/task_state.py:17-31` `TaskState` = QUEUED, PREPARING, RUNNING, PAUSED_RESOURCE, PAUSED_EXTERNAL, NEEDS_DECISION, RECOVERING, VALIDATING, COMPLETED, FAILED, UNKNOWN, CANCELLED with a transition table (`:34-57`) and in-memory history.
  - `desk/runtime/scheduler.py:51` `TaskExecutionRecord.state` is a free string; only QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED are ever assigned. It does not use `TaskStateMachine`.
  - `desk/rework/session.py:17-38` `ReworkSessionLifecycle` has its own 20 states and is the only lifecycle actually persisted (`session.py:112-121`, atomic tmp + `os.replace`).
- **No task persistence.** `TaskInbox.__init__` accepts `ledger_path` (`task_inbox.py:66-67`) but never reads or writes it; tasks live only in memory. The sequence counter restarts per process, so the "monotonic sequence" in `docs/architecture/DURABLE_TASK_RUNTIME.md` §4 is per-process only.
- **Nothing in production calls the runtime.** `TaskInbox` is referenced only by tests; `TaskScheduler` only by `tools/benchmarks.py:322-329`; `CheckpointManager` only by `desk/rework/executor.py:101`. `tools/build.py`, `tools/route.py`, `tools/clear_block.py` go straight to `ops.write_op` as separate OS processes.
- **No process-liveness reconciliation of tasks after restart.** `process_guard.py` is a bounded `Popen` wrapper, not a reconciler. `projection.py:633-683` only marks the dashboard projection INTERRUPTED.
- **Gap vs required lifecycle** (CREATED, QUEUED, STARTING, WORKING, WAITING_FOR_TOOL, WAITING_FOR_REVIEW, BLOCKED, COMPLETED, FAILED, CANCELLED, RECOVERING): CREATED, BLOCKED, WAITING_FOR_REVIEW, WAITING_FOR_TOOL missing (nearest: PAUSED_RESOURCE, NEEDS_DECISION, PAUSED_EXTERNAL); RECOVERING unreachable from QUEUED/PREPARING (`task_state.py:35-36`). `submit()` dedup returns the existing task for any non-FAILED state including COMPLETED (`task_inbox.py:101-104`). `scheduler.execute()` timeout cancels only QUEUED records (`scheduler.py:174-194`); a RUNNING `fn()` keeps mutating after the caller received `TimeoutError`.

## 2. Concurrency and the single-writer lock

- Implementation `desk/ops.py:142-184`: `O_CREAT|O_EXCL` lock file `projects/<P>/state/write.lock` with pid, pid_start_time, ts; stale if elapsed ≥ 1800 s, PID dead, or PID start time newer than the lock. Journal `ops.jsonl` begin/end/fail with `dirty`.
- Protects live EasyEDA writes under `write_op`: `tools/build.py:43`, `tools/clear_block.py:32`, `tools/route.py:214`, `desk/rework/executor.py:119`.
- **Gap A, reclaim race.** *FIXED (M1).* The lock was created and written in two steps; a concurrent acquirer reading between them got an unparsable record → `holder_pid=0` → treated as stale → reclaimed → two live writers. Now an unreadable record on a file younger than 2 s is treated as held and re-read.
- **Gap B.** `scheduler._mutation_lock` is a `threading.Lock` (`scheduler.py:85,245-247`) unrelated to `write.lock`; a scheduler EDA_MUTATION task and a `tools/*.py` process are not mutually excluded.
- **Gap C, unlocked writer.** *FIXED (M1) for atomicity.* `desk/bridge.py:258-263` rewrote `project.json` non-atomically from inside `get_or_create_session`, that is from every `ex()` call including read-only tools. It now uses `desk.fsutil.atomic_write_json`. It is still unlocked.
- **Gap D.** `is_process_alive` returns True on ctypes failure (`ops.py:82-83`), which can block all writers for 30 min after a crash where `OpenProcess` fails.
- `pending()` replays the entire `ops.jsonl` on every `write_op` with no compaction.

## 3. Bridge and IPC

- Transport: blocking `urllib` POST to `http://127.0.0.1:<port>/execute`, default timeout 280 s, retries 1 (`bridge.py:280`). Port discovery: `EDA_PORT` → in-memory cache (60 s) → `~/.desk/bridge_endpoint.json` (60 s) → probe 49620 → concurrent probe 49621-49629. Fallback silently returns 49620 and caches it.
- `get_or_create_session` opens and parses `project.json` on every `ex()` before the session-reuse check (`:235-242` precede `:249`). `_find_window_for_project` does one GET plus one POST per window on first session and on every OSError retry.
- Retry classification: HTTP error → `SystemExit` (no retry); mutation + timeout → invalidate + exit (*now raises `BridgeMutationTimeout`, which `write_op` journals as dirty, FIXED M1*); other OSError → window re-resolve, sleep 1 s, retry once. `is_mutation` is a caller flag, not derived from the operation registry.
- Second bridge client: `desk/rework/connection.py:63-86` reimplements `/eda-windows` and `/execute` with different timeouts and `RuntimeError`.
- Mission Control runs a 10-port probe on every `/api/status`, `/api/sync`, `/api/project/select` (`server.py:227-275`); the UI polls every 2 s (`index.html:869`).
- `bridge.py:18-19` replaces `sys.stdout` at import time.

## 4. Memory systems inventory

| System | Storage | Schema present | Missing | Dedup / decay / supersede |
|---|---|---|---|---|
| Decision ledger `desk/ledger.py` | `projects/<P>/LEDGER.jsonl` append-only | id, ts (local, no tz), type, text, block, source (required for decision/fact/assumption), spec_hash, refs; `add_decision_record` adds model_id, req_ids, alternatives, reasoning, board_rev, verification_result, profile_hash | confidence, author/actor, approval, status | No dedup. Supersede via `correction.refs`; staleness by spec/profile hash. IDs from line count → concurrent writers produce duplicate IDs. No fsync. |
| Context engine `desk/context.py` | `projects/<P>/state/ctx_index.json`, `ctx_served.json` (non-atomic) | chunk id/kind/title/src/text/refs/hash | derived cache | Content-hash reuse; FORMAT bump invalidation. |
| Mental models `desk/mental/*` | in-process cache only | model_id, version, domain, constraints; policy has profile_hash, token_estimate | persistence, provenance, approval | cache key = profile hash + model version |
| Learning engine `desk/learn/engine.py` | `.desk_learn/{corpus.jsonl, known.json, gaps.json, decisions.jsonl, proposals.json, metrics.json}` (atomic) | gaps: kind, target, sessions{model, quotes, count, tokens}, first/last_seen, n_sessions; decisions: id, sig, decision, reason, reviewer, ts | confidence, project | signature dedup; idempotent per (session, event); rejection memory; no decay |
| `.desk_learn/runs.jsonl` | every tool exit (`tools/_common.py:26-37`) | ts, tool, args, rc, dur_s, out_chars, err_tail | — | unbounded growth |
| `learning/` | Markdown incidents (8), lessons (4), sessions (1), indexes | free-form template | machine schema, timestamps, evidence links, status | manual; no code reads it; not indexed by `desk/context.py` (`DOC_FILES`, `context.py:25-26`) |

Overlap: three independent "verified fact / gotcha" stores (LEDGER `fact/verified`, `learning/lessons/*.md`, learn-engine "Learned gotchas" in `docs/06_EASYEDA_API.md`). Three token estimators (`context.py:27,41-42`, `learn/engine.py:30,390-391`, `mental/compiler.py:121`). The projection timeline is a fourth, in-memory event memory with colliding ids after `pop(0)` (`projection.py:840,848-849,855,864-865`).

## 5. Mission Control

- Endpoints (`server.py:157-198`): status, bridge, sync, project/select, executions, events, timeline, logs, SSE streams, rework/{session, issues, plan, history}, health, projects, metrics, per-execution events/logs/artifacts. POST accepted on `/api/events|telemetry` although docs claim read-only.
- Derived vs real: stage status comes from file-existence heuristics (`projection.py:373-437`) plus an OS process scan and a ledger regex. Nothing outside `desk/runtime` emits `stage.*` events. Routing progress is a time formula `25 + elapsed/25` capped at 92 (`projection.py:543`). Hardware metrics are real. `/api/v1/health` is static.
- Cost per status call: full `pcb_dump.json` parse, full `LEDGER.jsonl` parse, Toolhelp32 snapshot with PEB reads, rework session dir scan, 10-port probe; triggered every 2 s by the UI and every 1 s by the monitor loop. `persist_state()` writes synchronously inside every event callback under the projection lock.
- SSE: per-connection bounded queue, drops newest when full, 10 s heartbeat, O(n) replay.

## 6. Error handling

- 66 `raise SystemExit(...)` sites across `desk/` and `tools/`; library modules use it as control flow (`bridge.py`, `ops.py`, `ledger.py`, `context.py`, `spec.py`), so in-process callers must catch `BaseException`. `ops.write_op` treats `SystemExit` as a clean failure, so a bridge mutation timeout was journaled `dirty=False` (*FIXED M1 via `BridgeMutationTimeout`*).
- `tools/_common.py:20-24` monkey-patches `sys.exit` and infers the return code from stderr content.
- Boolean collapse: `EngineExecutionResult.success` is True for STAGNATED-with-partial-SES (`routing/orchestrator.py:320-338`); `DRCComparisonResult.passed=True` for CONDITIONALLY_PASSED (`routing/quality.py:88-90`); `QualityReport.hard_gates_passed: bool` folds NOT_RUN/STALE/UNKNOWN into False (`quality.py:154,486`); `RepairExecutionResult.verification_passed: bool`; `OperationRegistry.execute` always returns `"status": "SUCCESS"` (`operation_registry.py:99-105`).
- Broad exception swallowing at `projection.py:462-463,507-510,682-683,710-711,915-916`, `events.py:185-193`, `server.py:630-631`, `bridge.py:54-55,65-66,100-101,222-225`.

## 7. Duplicate logic

Token estimators ×3; project loaders ×4 (`bridge.load_project`, `bridge.get_or_create_session`, `context.Engine.__init__`, `rework/connection.py:135-140`); bridge HTTP clients ×2; DRC parsing ×3 (`drc_engine.DRCParser`, `rework/audit.audit_drc_manufacturing`, `projection.py:483` regex); process liveness ×2; atomic-write helpers ×5 alongside 30+ non-atomic `json.dump` sites (*one shared `desk/fsutil.py` added in M1; call sites migrate incrementally*); grid-snap/anchor logic duplicated between `desk/placement_intel.py` and `tools/pcb_place.py:50-60`; port probing ×3.

## 8. Reliability risks

- Non-atomic JSON writes that can truncate on crash: `bridge.py:64` and `:261` (*FIXED M1*), `tools/pcb_dump.py:22` (*FIXED M1*), `context.py:38`, `ops.py:148`, `profile.py:346`, `release.py:93`, `rework/audit.py:457`, `rework/planner.py:244,274`, `rework/readiness.py:122`, `routing/orchestrator.py:175`, `tools/route.py:325`, `tools/drc.py:52,128,137,143`, `tools/pcb_place.py:46,86`, `tools/build.py:53`, `tools/clear_block.py:37`, `tools/pins.py:22`, `tools/desk.py:308`. `ledger.add` appends without fsync and derives ids from line count.
- Missing timeouts: `tools/drc.py:76`, `auth/storage.py:171,187,201`, `learn/engine.py:69,224,412`, `tools/desk.py:428`, `tools/release.py:84`, `tools/learn.py:28-30`.
- Unbounded growth: `scheduler._records`, `TelemetryCollector.records`, `ops.jsonl`, `runs.jsonl`, `LEDGER.jsonl` with full re-read per use.
- Thread safety: `TelemetryCollector` counters unsynchronised yet incremented from the router thread pool; `SessionRegistry._sessions` and `_LEDGER_CACHE` unsynchronised.
- `persist_state` under the projection lock inside `EventBus.emit` listeners stalls every emitter on a slow disk.

## 9. Credentials

Secrets are never written to task or projection records. Vault backends: Windows Credential Manager, macOS `security` CLI (secret passed as argv, visible in process listings, `storage.py:184`), POSIX file with XOR-by-path obfuscation and 0600 (explicitly non-cryptographic). `CredentialBroker.scrub` is applied only in `auth/cli.py`; projection logs use their own regex (`projection.py:86-99`); the server masks dict keys only.

## 10. Top 10 software improvements (ranked by correctness and data-loss evidence)

1. Fix `write.lock` reclaim race (`ops.py`). **Done M1.**
2. Atomic, lock-aware writes for `project.json` and `pcb_dump.json` via one `desk/fsutil.atomic_write_json`. **Helper and the two critical sites done M1**; remaining 28 sites tracked as SW-02.
3. Mark bridge mutation timeouts dirty. **Done M1.**
4. Persist the task inbox and unify the state vocabularies; add CREATED/BLOCKED/WAITING_FOR_TOOL/WAITING_FOR_REVIEW and a QUEUED→RECOVERING edge; startup reconciler using `ops.is_process_alive`. L.
5. Scheduler cancel-on-timeout must not leave mutations running; pass a cancel `Event` into `fn`. M.
6. Replace `SystemExit` in library modules with typed exceptions, converted at the CLI boundary. M.
7. Structured verdicts (`PASS | CONDITIONAL | FAIL | NOT_RUN | STALE | UNKNOWN`) instead of booleans across routing, quality, rework and orchestrator results. M.
8. Stop per-request full reconciliation in Mission Control: mtime-keyed cache, 5 s port-probe cache, debounced persist thread, monotonic timeline ids. M.
9. Unify project loading and bridge clients; remove the `project.json` write from the `ex()` read path. M.
10. Index `learning/` in the context engine and consolidate the three gotcha stores; add author, status, confidence to `ledger.add`. S.
