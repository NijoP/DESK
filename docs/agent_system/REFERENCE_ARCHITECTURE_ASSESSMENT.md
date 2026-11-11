# Reference Architecture Assessment

**Purpose:** decide which engineering concepts from six reference projects DESK should ADOPT, ADAPT, REUSE, REJECT or DEFER. Facts come only from pages actually read on 2026-11-11 (sources at the end); nothing was cloned and no code was copied. DESK constraints: Python standard library only, single-writer mutation model, hardware engineering remains the differentiator.

## 1. kunchenguid/firstmate

**What it is.** An "agent distro for running a crew of agents": a repo with `AGENTS.md`, bundled skills and bash helpers; a supported harness (Claude Code, Grok, Pi, Codex, OpenCode, Cursor CLI, `agy`) launched inside it becomes the "first mate". License MIT. ~8.8k stars, 1,186 commits.

**Concepts observed.** Single liaison ("you talk only to the first mate"; it dispatches, supervises, "escalates only real decisions"). Ship tasks change projects; scouts leave standalone reports at `data/<id>/report.md` and never push. Each task runs in a disposable git worktree. Zero-token supervision via `bin/fm-watch.sh` with a durable wake queue; "missing or stale state is unknown, never idle." Control-plane actions (`interrupt`, `exit`, `relaunch`) are separate from data-plane sends. Escalation ladder (stale pane → wake → counted escalations → inspection demand → `PERMANENTLY-WEDGED`), deferred for declared pauses, human holds and recent writes, and "never an automatic interrupt, signal, or restart." Durable state on disk: `state/<id>.meta`, incarnation tokens (`.busy-gen`), `turn-ended` markers, inbox/outbox JSON, status logs as cold evidence. Restart reconciliation relies on durable state, derived event IDs make replays converge. Project modes `no-mistakes`, `direct-PR`, `local-only`.

**DESK decision.** ADOPT: single-liaison contract; ship/scout split (maps onto the task inbox); per-task durable meta plus incarnation token; derived idempotent event IDs; "unknown is never idle"; control vs data plane; inspection-only escalation. ADAPT: project modes → per-project mutation posture (gated / direct / local-only); escalation deferral list. REUSE (concept): typed obligations with explicit retirement for the decision ledger. REJECT: worktree-per-task as a hard requirement (hardware artefacts are not always git-managed; keep optional), tmux/herdr backends, Relay/Discord. DEFER: multi-host fleets.

**Licensing.** MIT; scripts are bash, so porting rather than copying is the practical path.

## 2. kunchenguid/backpass

**What it is.** "Gradient descent for your agent memory": mines real agent sessions and proposes evidence-backed edits to `AGENTS.md`/`CLAUDE.md`/skills. Node ≥ 22.5, TypeScript. License MIT. ~1.5k stars.

**Concepts observed.** Pipeline discover → distill → loss → aggregate → synthesis → apply. Deterministic distillation redacts secrets and reduces 96–99 % before any model sees it; recency-weighted sampling with a 14-day half-life. Evidence rule: "every claim needs a verbatim quote" that must appear in the distilled trace; each add/rewrite/remove needs quotes from ≥ 2 distinct observers; removals need harm-class negatives. Gap ledger with 90-day expiry and retire-on-coverage. Synthesis edits a staging copy; backpass computes the diff itself. 5,000-token budget on the always-loaded surface; overflow moves into skill bodies loaded on trigger. "`backpass` never writes. `backpass apply` is the only writer." Remembered rejections suppress re-proposals until strictly more sessions exist.

**DESK decision.** ADOPT: single-writer `apply`; verbatim-quote evidence; two-observer floor; remembered rejections; gap ledger with expiry; token-budgeted always-loaded surface vs on-demand bodies (fits `desk/context.py` packs). ADAPT: distill-before-model for DESK's own `.desk_learn/runs.jsonl`; staging-copy plus self-computed diff; effort-tiered candidate ladders map onto the L0-L4 router. REJECT: Node toolchain, review UI, `acpx`. DEFER: SSH transcript collection. Note: DESK's `desk/learn/engine.py` already implements the corroboration, approval and rejection-memory ideas; the gaps are decay, confidence fields and a single consolidated store (see `SOFTWARE_ARCHITECTURE_ASSESSMENT.md` §4).

**Licensing.** MIT; TypeScript, so DESK re-implements in stdlib Python.

## 3. herdrdev/herdr

**What it is.** "The runtime your coding agents live on": a Rust terminal multiplexer and workspace manager that tracks agent state across panes and machines. License Apache-2.0. ~50k stars, v0.4.0, Windows beta.

**Concepts observed.** Persistent sessions survive detach or SSH drop. Agent statuses `idle`, `working`, `blocked`, `done`, `unknown` (`done` = idle and not yet seen). `blocked` is strict: only on positive match of approval/question UI; "idle status is not authorization to approve an action." Socket API: newline-delimited JSON `{id, method, params}` → `{id, result | error{code, message}}`; `agent.list/get/read/prompt/wait`, `events.subscribe`; overflowing subscribers get `events_lost` and must snapshot and reconcile; `herdr api schema --json` self-describes. Recovery: `session.json`, 48 snapshots, 3 backups of unreadable files, opt-in history replay (off by default because output may contain secrets).

**DESK decision.** ADOPT: the five-state lifecycle with `unknown` and `done` distinct from `idle`; "blocked only on positive match, idle is not authorization"; `{id, method, params}` JSONL request/response with `events_lost` + snapshot-reconcile (stdlib `socket`/`json`); snapshot ring plus backup-of-unreadable for DESK state files. ADAPT: `agent.wait --until <state>` as a scheduler primitive. REUSE: none (Rust). REJECT: terminal multiplexing, PTY management, plugin marketplace. DEFER: multi-machine aggregation. Herdr is therefore an optional execution backend, not a dependency.

## 4. earendil-works/pi (and pi.dev docs)

**What it is.** "AI agent toolkit: unified LLM API, agent loop, TUI, coding agent CLI." TypeScript monorepo; Node ≥ 22.19. License MIT. ~121k stars. Packages: `pi-ai`, `pi-agent-core`, `pi-coding-agent`, `pi-tui`, `pi-durable`, `pi-telemetry`, `chord`.

**Concepts observed.** Provider interface: a provider owns its catalogue, auth and streaming; wire protocols `anthropic-messages`, `openai-responses`, `openai-completions`, `google-generative-ai`; every assistant message carries `usage` and `cost`. `models.json`: providers keyed by id with `baseUrl`, `apiKey` (`$ENV` or `!command`), `api`, `models[]` with `id`, `cost`, `contextWindow`, `maxTokens`, `reasoning`, `thinkingLevelMap`. Agent loop: turn = one LLM call + tool executions; `beforeToolCall` gate, `afterToolCall` transform; `steer()` and `followUp()`; `agent_end` ≠ idle, use `agent_settled`. Tools are JSON Schema with `strict` modes. Extensions: notify / gate / transform hooks. Skills: `SKILL.md` with name and description in the system prompt and the body on demand. Sessions: JSONL with id/parentId tree, typed entries, compaction policy (reserve 16,384 tokens, keep 20,000 recent, never cut at a tool result, structured summary). `--mode json` / `--mode rpc`: LF-framed JSONL on stdin/stdout, `id` correlation, stdout protocol-only, stdin close = orderly shutdown. "Pi does not include a built-in permission system."

**DESK decision (DESK calls `pi` as a subprocess).** ADOPT: drive `pi` with `-p --mode json`, `-ne` (no extensions) and `--no-session` for deterministic non-interactive calls; `agent_settled` as the completion signal; `message_end` as authoritative output; per-message `usage`/`cost` for router accounting. ADAPT: models.json schema as the DESK model-capability registry format; compaction policy for the context engine; JSONL id/parentId tree for DESK session logs; notify/gate/transform hook taxonomy. REUSE: `SKILL.md` format verbatim (already used in `.agents/skills/`). REJECT: in-process TS SDK, jiti extensions, TUI. DEFER: telemetry contracts, `pi-durable`.

**Verified today.** The three intended NVIDIA models are reachable through `pi` after adding an `nvidia` provider to `~/.pi/agent/models.json`. Pi failed to start with extensions enabled because of an unrelated local extension config error, which is why the DESK adapter now passes `-ne`.

## 5. WeaveMindAI/wefth → actually `weft`

The given URL returns 404; the intended repo is `WeaveMindAI/weft`: "a programming language and framework for AI orchestration" compiling typed node graphs to Rust binaries. License "O'Saasy License" (not SPDX, not OSI-approved per the pages read; hosted-use partnerships require contacting the company). ~2k stars; README says "early, breaking changes still possible".

**Concepts.** Typed ports with `_should_flow` gating; `Switch`/`FirstInOrder` routing nodes; durable human waits that release the worker and resume on answer; every run journaled; "Sequential Diffusion Programming" (freeze accepted steps, replay).

**DESK decision.** ADAPT (concept only): durable human-wait that releases the worker (fits the human-gated learning engine and approval tokens); journaled runs; typed inter-step ports for tool-chain validation; freeze/replay of accepted steps. REJECT: DSL, compiler, Rust/Restate runtime. **Do not copy code** under this licence.

## 6. rust-lang/rust (process only)

License MIT OR Apache-2.0.

**Concepts.** Review: auto-assigned reviewer, `S-waiting-on-author` / `S-waiting-on-review` labels, "PRs are never merged by hand", explicit LLM-contribution policy. RFC / MCP / FCP tiers: substantial changes need an RFC; FCP with disposition merge/close/postpone, 10-day window, "merged = active, not a rubber stamp"; MCP as a lightweight path. Stability: feature gates, `#[unstable]`/`#[stable(since)]`, "features do not gain tenure by being unstable and unchanged." Diagnostics: level + code + message + spans with labels; `help` = changes the user can make, `note` = facts; suggestions carry `Applicability` (`MachineApplicable`, `HasPlaceholders`, `MaybeIncorrect`, `Unspecified`), "be conservative". Tests: compiletest UI suites with `.stderr` snapshots, `//~ ERROR` annotations, normalisation, `--bless` then manual review.

**DESK decision.** ADOPT: applicability levels on every AI-generated suggestion (DESK must mark `MachineApplicable` vs `MaybeIncorrect` before any auto-apply); diagnostic wording and span rules for DRC/ERC/audit findings; golden snapshot tests with normalisation and an explicit bless-and-review step (stdlib `unittest` + `difflib`); exhaustive expected-finding annotations for hardware rule checks; feature-gate semantics for DESK's own unstable features. ADAPT: RFC/MCP/FCP tiers as the decision-ledger proposal lifecycle; `S-waiting-on-*` labels for the task inbox. REJECT: bors/CI infra. DEFER: crater-style smoke tests.

## Cross-reference table

| Concept | Source | Decision |
|---|---|---|
| Single liaison; escalate only real decisions | firstmate | ADOPT |
| Ship vs scout task kinds | firstmate | ADOPT |
| Per-task worktree isolation | firstmate | ADAPT (optional) |
| Zero-token watcher + durable wake queue | firstmate | ADOPT |
| "Unknown never idle" | firstmate, herdr | ADOPT |
| Incarnation tokens, derived event IDs | firstmate | ADOPT |
| Escalation ladder, inspection-only, deferral list | firstmate | ADOPT/ADAPT |
| Project modes | firstmate | ADAPT |
| Typed obligations with retirement | firstmate | REUSE (concept) |
| Single-writer `apply` | backpass | ADOPT (already in learn engine) |
| Verbatim-quote evidence; two-observer floor | backpass | ADOPT (already in learn engine) |
| Gap ledger expiry, retire-on-coverage | backpass | ADOPT |
| Remembered rejections | backpass | ADOPT (already) |
| Token-budgeted surface vs on-demand bodies | backpass, pi | ADOPT |
| Deterministic distill + redaction | backpass | ADAPT |
| Five-state agent lifecycle incl. done/unknown | herdr | ADOPT |
| Strict blocked; idle is not authorisation | herdr | ADOPT |
| JSONL socket API, events_lost + snapshot | herdr | ADOPT (stdlib) |
| Snapshot ring + backup of unreadable state | herdr | ADOPT |
| Drive `pi` via json mode, `agent_settled` | pi | ADOPT (done M1) |
| models.json schema as capability registry | pi | ADAPT (done M1) |
| Per-message usage/cost accounting | pi | ADOPT |
| Compaction policy | pi | ADAPT |
| Hook taxonomy notify/gate/transform | pi | ADAPT |
| SKILL.md format | pi / Agent Skills spec | REUSE (already) |
| Durable human-wait, journaled runs | weft | ADAPT (concept only) |
| DSL/compiler/Restate | weft | REJECT; no code reuse |
| Applicability levels on suggestions | rust | ADOPT |
| Diagnostic wording rules | rust | ADOPT |
| Snapshot tests, bless + review | rust | ADOPT |
| RFC/MCP/FCP tiers | rust | ADAPT (ledger) |
| bors/CI/crater | rust | REJECT / DEFER |

## Sources

- https://github.com/kunchenguid/firstmate and `docs/architecture.md`
- https://github.com/kunchenguid/backpass (README)
- https://github.com/herdrdev/herdr ; https://herdr.dev/docs ; socket-api, agents, session-state pages
- https://github.com/earendil-works/pi ; `packages/coding-agent/docs/` (how-pi-works, rpc, json, session-format, extensions, skills, compaction, models-configuration, sdk); `packages/ai/README.md`; `packages/agent/README.md`; `packages/telemetry/README.md`
- https://github.com/WeaveMindAI/wefth (404) ; https://github.com/WeaveMindAI/weft (README)
- https://github.com/rust-lang/rust ; CONTRIBUTING.md ; rustc-dev-guide: contributing, pr-lifecycle, implementing-new-features, stability, diagnostics, tests/compiletest, tests/ui ; rust-lang/rfcs README
