# AI Orchestration Assessment (Team C)

**Scope:** DESK's agent architecture, model routing, provider adapters and the intended NVIDIA configuration. Every number below was measured in this repository on 2026-11-11; nothing is quoted from vendor marketing.
**Owner:** Principal AI Systems Engineer.

## 1. How DESK uses models today

- **Two separate AI paths.** (a) The interactive harness (Claude Code, Codex, Pi, OpenCode, Cursor) reads `AGENTS.md` and `.agents/skills/*` and drives the CLI tools. (b) `desk/orchestrator/` implements an L0-L4 capability router that shells out to the `agy` (Gemini) and `pi` CLIs. Path (b) is not called by any pipeline stage (`docs/09_STATUS.md` row 1d). In practice all AI work runs through path (a).
- **Deterministic core.** Routing, DRC parsing, placement, copper geometry and the quality gates are pure Python with no model call. This is the right split and must be preserved.

## 2. Defects found in the router and adapters (all fixed in M1)

| Defect | Evidence | Fix |
|---|---|---|
| Provider fallback never worked: the Gemini model name was written onto the shared request and passed to Pi | `router.py` L1/L2 loops mutated `task.preferred_model` | per-provider task copies (`_task_for`) |
| Pi path had no structured-output contract; JSON parsed by hunting for a fence | `pi_adapter.py` | schema injected into the system prompt; no-JSON is a failure |
| One 60 s timeout for every tier | `protocol.py` | per-tier defaults 30/90/180/300 s, env-overridable |
| L4 hard-coded `claude-sonnet-4-6` through the Gemini CLI, which cannot serve it | `router.py` | `DESK_FRONTIER_PROVIDER/MODEL`, else the provider's own catalogue |
| L3 dual review ran sequentially | `router.py` | `ThreadPoolExecutor` |
| `shell=True` with prompt text in argv (command injection on Windows) | `pi_adapter.py` ×2 | argument lists only |
| Hard-coded `C:\Users\HP\...` executable paths | both adapters | `DESK_PI_PATH` / `DESK_AGY_PATH` / PATH |
| CLI output decoded as cp1252 on Windows → `UnicodeDecodeError` on UTF-8 JSON | observed live during the first router dispatch | `encoding="utf-8", errors="replace"` |
| Pi aborted at startup because of an unrelated local extension config error | observed live | `-ne --no-session` for worker calls |

## 3. Verification of the intended NVIDIA configuration

Intended: `DESK_L1_MODEL_PI=nvidia/nemotron-3.5-lightning-30b-a3b`, `DESK_L2_MODEL_PI=nvidia/nemotron-3.5-super-vl-120b-a12b`, `DESK_FRONTIER_PROVIDER=pi`, `DESK_FRONTIER_MODEL=nvidia/nemotron-3-ultra-550b-a55b`.

**Availability and auth.** `GET https://integrate.api.nvidia.com/v1/models` with the configured key lists 84 models including all three intended ids. Pi's `~/.pi/agent/models.json` had no `nvidia` provider, so the intended variables would have failed inside Pi; an `nvidia` provider was added (key referenced as `$NVIDIA_API_KEY`, never stored) and `pi --list-models` now shows the NVIDIA catalogue.

**Behaviour under probe** (one-line IPC width question, JSON object requested):

| Model | Thinking default | Result with thinking on | Result with thinking off |
|---|---|---|---|
| nemotron-3.5-lightning-30b-a3b | on | 40-50 s, `finish_reason=length`, empty content (all 1,500 tokens spent on reasoning) | 0.8-1.1 s, valid JSON |
| nemotron-3.5-super-vl-120b-a12b | on | 41.5 s, empty content | 51.6 s valid JSON; intermittent HTTP 503 "content safety screening is temporarily unavailable" |
| nemotron-3-ultra-550b-a55b | on | 14.8 s valid JSON (JSON mode); plain mode empty | 0.7 s valid JSON |

Both `chat_template_kwargs: {"enable_thinking": false}` and `reasoning_effort: "none"` switch thinking off on this endpoint. The router now sets thinking off for L1 and L2 and medium/high for L3/L4.

**Structured output.** `response_format: {"type": "json_object"}` is honoured by all three models when thinking is off.

**Vision.** Only the Super-VL model accepts images; the registry (`desk/orchestrator/capabilities.py`) records this and the router substitutes a vision-capable model when a task sets `requires_vision`.

**Rate limits.** The free tier is documented by third parties at about 40 requests per minute with a small starting credit pool. The 503 content-safety outage was reproducible across several minutes; L2 therefore needs a fallback provider.

**Context limits.** The catalogue returns no `max_model_len`; the registry assumes 131,072 tokens from vendor documentation (UNVERIFIED).

**Numerical reliability.** For the identical question "trace width for 1 A on 1 oz outer copper, 10 °C rise", the models answered 25, 110, 10.4 and 12 mil. DESK's deterministic calculator gives 11.9 mil (IPC-2221). This is the strongest evidence in the audit that LLMs must never perform the engineering arithmetic.

## 4. Token and latency overhead of calling models through a coding-agent CLI

Measured with one L1 classification task ("is this request SCOUT or SHIP?"):

| Path | Input tokens | Wall time | Notes |
|---|---|---|---|
| `agy` (Gemini CLI, inside the repo) | 23,683 | 30.6 s | loads AGENTS.md and project context; answered "Aye, Captain" |
| `pi -ne` (Pi CLI, NVIDIA Lightning) | 4,423 | 4.2 s | still loads the coding-agent system prompt |
| Direct HTTP (`desk/orchestrator/http_adapter.py`, NVIDIA Lightning) | ~150 | 1.1 s | only the task's system prompt and prompt |
| Direct HTTP, L2 Super-VL | ~150 | 31.8 s | model-bound, not overhead |

Conclusion: for L1/L2 the harness is the cost, not the model. The direct adapter (provider name `nvidia`) is now the recommended first provider: `DESK_PROVIDER_ORDER=nvidia,pi,agy`.

## 5. Context engine and skills

- `desk/context.py` builds task packs under a token budget with a chars/4 estimate; `desk/mental/compiler.py` emits policies under 400 tokens; `desk/skills.py` loads one skill by trigger. These are sound and match the Backpass/Pi "small always-loaded surface, bodies on demand" principle.
- `AGENTS.md` is 8.5 KB and is inlined into every session via `CLAUDE.md`. The learning directory `learning/` is not indexed by the context engine, so verified EasyEDA gotchas are invisible to agents.
- Three token estimators and three "verified fact" stores exist (see the software assessment §4).

## 6. Recommendations (ranked)

1. **Wire the router into real stages** (scout/ship intake classification, DRC-diagnosis explanation, rework-plan narration) behind the deterministic validators. Owner: AI. M. Without this the router remains documented capability with zero product effect.
2. **Keep L1/L2 on the direct HTTP adapter** with thinking off; keep CLIs for L3/L4 where tool use matters. Done M1; needs the pipeline wiring to pay off.
3. **Trace IDs and per-call accounting.** Record provider, model, tokens, latency and outcome per `task_id` in `.desk_learn/runs.jsonl` style, redacted. S.
4. **Index `learning/` in the context engine** and surface lessons at failure time. S.
5. **Applicability levels** (Rust-style `MachineApplicable` / `MaybeIncorrect`) on every model-generated suggestion before anything auto-applies. M.
6. **Never let a model touch numbers.** Every numeric field in a model's structured output that DESK can compute must be overwritten by the deterministic engine before use; add a validator helper. S.
