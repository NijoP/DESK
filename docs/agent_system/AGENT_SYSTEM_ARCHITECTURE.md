# DESK Agent System Architecture

One document, five sections, replacing the proposed `MULTI_AGENT_ARCHITECTURE.md`, `PERSISTENT_MEMORY_ARCHITECTURE.md`, `AGENT_RUNTIME_ARCHITECTURE.md`, `AI_RUNTIME_AND_MODEL_ROUTING.md` and `ENGINEERING_CONTRACTS_AND_RELIABILITY.md`. Decisions reference `REFERENCE_ARCHITECTURE_ASSESSMENT.md` (ADOPT/ADAPT table) and the audits in `docs/product_assessment/`. Everything here reuses existing DESK modules; no new external dependency is introduced.

## 1. Multi-agent coordination (firstmate-inspired)

**Contract.** The Founder talks to one liaison, the Product Manager. The Product Manager decomposes requests into SCOUT and SHIP tasks, assigns them to team leads, tracks dependencies, and escalates only real decisions.

**Existing DESK equivalents.** `desk/runtime/task_inbox.py` (in-memory inbox with dedup), `desk/runtime/scheduler.py` (bounded workers, mutation lock), `desk/ops.py` (single-writer lock + journal), `.agents/skills/scout-task-intake` and `ship-task-intake` (intake rules), `AGENTS.md` (Captain / First Mate roles).

**Adaptation plan (SW-04, AI-07).**
- Task record persisted to `projects/<P>/state/tasks.jsonl` (append-only, atomic writes) with: id, kind (SCOUT|SHIP), team, lead, owner agent, model, state, incarnation token, created/updated timestamps, scope, required tests, evidence links, parent request id. Derived event ids make replay idempotent.
- Lifecycle: CREATED → QUEUED → STARTING → WORKING ↔ WAITING_FOR_TOOL / WAITING_FOR_REVIEW / BLOCKED → COMPLETED | FAILED | CANCELLED; any non-terminal state → RECOVERING on restart. UNKNOWN is never promoted to idle or busy.
- Isolation: SHIP tasks that touch code run in a git worktree on a task branch; tasks that touch a live board run under `ops.write_op` only. SCOUT tasks never acquire the lock.
- Escalation: inspection-only. A stuck task is reported with its last evidence; it is never killed or restarted automatically. Destructive or irreversible actions always escalate to the Founder.

## 2. Persistent memory (backpass-inspired)

**Tiers.**
1. Product identity: `AGENTS.md` (always loaded, token-budgeted), `docs/organisation/PRODUCT_CHARTER_AND_TEAMS.md`.
2. Architectural memory: `docs/architecture/*`, `docs/agent_system/*`, `docs/09_STATUS.md`.
3. Project memory: `projects/<P>/LEDGER.jsonl` (decisions with source), `REQUIREMENTS.md`, `blocks/`, `state/` fingerprints.
4. Operational memory: `state/tasks.jsonl` (planned), `state/ops.jsonl`, `.desk_learn/runs.jsonl`, `state/rework/<sid>/`.
5. Ephemeral: agent context packs from `desk/context.py` (never persisted as memory).

**Existing systems and their gaps** (software assessment §4): ledger lacks confidence, author, approval, status; three "verified fact" stores overlap; `learning/` is not indexed; no decay or archival anywhere.

**Rules adopted.**
- One writer for instruction memory: the learning engine's `apply` step with human approval (already implemented in `desk/learn/engine.py`).
- Every knowledge record carries source, timestamp, evidence, confidence, project, status, author, approval status (SW-10 extends `ledger.add`).
- Contradicted knowledge is never rewritten: a `correction` record references the original (already supported by `ledger.refs`).
- Gap ledger entries expire (90 days) and retire when covered; rejections are remembered and re-proposed only with strictly more evidence (learn engine already keeps rejections; expiry to add).
- Context packs: small always-loaded surface, bodies on demand. Benchmark tokens before and after any change to `AGENTS.md` or skills using the existing chars/4 estimator, after consolidating the three estimators into one.

## 3. Agent runtime and supervision (herdr-inspired)

**Decision:** Herdr is an optional execution backend, not a dependency. DESK keeps a native supervisor.

- State detection: an agent is WORKING only while its process is alive (`ops.is_process_alive`) and its incarnation token matches; BLOCKED only on a positive match of a review/approval request; "idle is not authorisation".
- Control plane vs data plane: task control (cancel, resume, review) is a separate JSONL request `{id, method, params}` on the Mission Control server; task output is the data plane. `events_lost` on overflow forces a snapshot reconcile (the SSE queue already drops on overflow; the client must re-sync).
- Recovery: on start, reconcile filesystem (`tasks.jsonl`, `ops.jsonl`), git (worktrees, branches) and process state; never auto-resume a mutation; mark RECOVERING and require re-authorisation.
- Snapshots: keep a ring of state snapshots and a backup of any unreadable state file instead of overwriting (adopts herdr's session-backup rule; `desk/fsutil.py` is the write path).

## 4. AI runtime and model routing (pi-inspired)

**Providers (implemented M1):** `nvidia` (direct OpenAI-compatible HTTP, `desk/orchestrator/http_adapter.py`), `pi` (CLI, `-p --mode json -ne --no-session`), `agy` (Gemini CLI). Order via `DESK_PROVIDER_ORDER`; recommended `nvidia,pi,agy`.

**Tool-calling agent (implemented 2026-11-12):** `desk/orchestrator/agent_loop.py` runs an OpenAI-style tool loop on the `nvidia` provider (default `nvidia/nemotron-3-ultra-550b-a55b`, thinking off). The model sees only DESK's deterministic tools (`desk/orchestrator/tools_manifest.py`: read_schematic, list_schematic_nets, plan_wires, wire_net, read_pcb, dense_board_analysis, doctor, run_desk_tool); DESK executes every call, mutations exist only with `--allow-mutation`, and the trace lands in `<project>/state/agent_trace.jsonl`. See `docs/agent_system/NVIDIA_TOOL_CALLING.md`.

**Tiers (implemented M1):**

| Tier | Use | Default model (nvidia) | Thinking | Timeout |
|---|---|---|---|---|
| L0 | deterministic engineering | none | — | — |
| L1 | classification, intake, short interpretation | nemotron-3.5-lightning-30b-a3b | off | 30 s |
| L2 | engineering reasoning, screenshot interpretation (vision) | nemotron-3.5-super-vl-120b-a12b | off | 90 s |
| L3 | dual independent review | nemotron-3-ultra-550b-a55b + second provider | medium | 180 s |
| L4 | frontier escalation | nemotron-3-ultra-550b-a55b or `DESK_FRONTIER_MODEL` | high | 300 s |

**Capability registry (implemented M1):** `desk/orchestrator/capabilities.py` records context window, vision, structured output, tool calling, thinking default/controllability, free tier, verification date and probe latency per model. The router substitutes a vision-capable model when `requires_vision` is set. Entries are VERIFIED only after a live probe.

**Every request has:** a task id, a bounded timeout, a bounded provider list (no infinite retries), a structured-output contract when a schema is given, and a deterministic validator when the output drives any action. Numeric fields the engine can compute are overwritten by the engine (AI-06).

**Accounting (AI-03):** provider, model, tokens, latency and outcome per task id, redacted, appended to `.desk_learn/runs.jsonl`.

## 5. Engineering contracts and reliability (rust-inspired)

- **Units are explicit.** Coordinates in mil in the EasyEDA frame; widths in mil; currents in A; voltages in V; dielectric thickness in mil. Any new dataclass field carries the unit in its name (`width_mil`, `current_a`) and the profile records provenance (`VERIFIED | ESTIMATED | UNKNOWN`). UNKNOWN never becomes a default value (H-02).
- **Structured verdicts** replace booleans: `PASS | CONDITIONAL | FAIL | NOT_RUN | STALE | UNKNOWN` for routing, DRC comparison, quality gates, rework verification and router results (SW-07). A report lists `checks_not_performed` (done for readiness in M1).
- **Typed errors** at library boundaries; `SystemExit` only at the CLI boundary (SW-06). `BridgeMutationTimeout` is the first typed error (M1).
- **Diagnostics** follow Rust wording rules: one general message that stands alone, the smallest span (net, pad, layer, coordinates), `help` = what the engineer can change, `note` = facts; suggestions carry an applicability level and only `MachineApplicable` ones may be auto-applied (AI-05).
- **Tests:** property and invariant tests for geometry (incremental == rebuild already exists), numeric reference tests against published tables (QA-04), golden snapshot tests for text reports with an explicit bless-and-review step (QA-07), two-process lock contention (QA-02).
- **Stability:** new behaviours ship behind an explicit flag or env var with a documented default; a flag does not become default by age, only by evidence.
- **Dependency governance:** standard library only; optional external runtimes (Herdr, Pi, Freerouting, EasyEDA CLI) are detected by `desk doctor` and never imported.

## 6. Runtime backend compatibility matrix

| Backend | Role | Coupling | Status |
|---|---|---|---|
| Direct Claude Code / OpenCode / Codex session | drives CLI tools via `AGENTS.md` | none (files only) | in use |
| Pi CLI | model provider for the router; optional interactive harness | subprocess | verified M1 |
| NVIDIA NIM HTTP | model provider | stdlib HTTP | verified M1 |
| Gemini CLI (`agy`) | model provider | subprocess | present, unprobed |
| Herdr | optional pane/session supervisor | none planned | DEFER |
| Local tmux | optional | none | DEFER |
| Firstmate-style supervisor | concepts adopted natively | none | SW-04 / AI-07 |

The Product Manager depends on none of these specifically; replacing a backend does not touch `desk/` engineering modules.
