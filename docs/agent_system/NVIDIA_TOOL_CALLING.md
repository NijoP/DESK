# NVIDIA NIM tool calling in DESK (Nemotron 3 Ultra / 3.5)

**Status:** implemented and verified 2026-11-12. **Incident:** an agent session reported "the API bridge only supports write operations, no read operations", placed 34 components and told the operator to wire them by hand. The bridge executes arbitrary JavaScript and has always supported reads (`tools/verify.py` reads every pin and net). The failure was a model with no read tool in its hands, not an API limit.

## What changed

| Piece | File | Role |
|---|---|---|
| Schematic read-back | `desk/schematic_io.py`, `tools/sch_dump.py` | Parts, uuids, pins (absolute x/y, rotation, number, name, no-connect) and the net of every pin → `state/sch_dump.json`. Read-only. |
| Wiring by pin name | `desk/schematic_io.py`, `tools/wire.py` | `U1.3 C2.1 → NET`: resolves coordinates from the read-back, plans DESK-style stub wires + net labels (same calls as `desk/draw.py`), refuses unknown / no-connect / re-netted pins, `--apply` executes under the single-writer lock and verifies by read-back. |
| Tool manifest | `desk/orchestrator/tools_manifest.py` | OpenAI-format `tools` with deterministic handlers. The model never emits JavaScript or coordinates. |
| Agent loop | `desk/orchestrator/agent_loop.py`, `python tools/desk.py agent` | Bounded tool loop on the `nvidia` provider; trace in `<project>/state/agent_trace.jsonl` with keys redacted. |
| Raw chat call | `OpenAICompatAdapter.chat_completion` | `tools`, `tool_choice`, thinking control, usage. |

## How the request is shaped (and why)

NVIDIA's public material on the Nemotron 3 family (technical report, model cards and NIM docs) describes post-training with supervised fine-tuning followed by reinforcement learning across tool-use, structured-output and instruction-following environments, with a hybrid reasoning switch. Three consequences drive the request shape:

1. **Tools go in the `tools` field, not in prose.** The chat template renders OpenAI-style function schemas; the model answers with `tool_calls` and `finish_reason: tool_calls`. Measured on `integrate.api.nvidia.com` on 2026-11-12: both `nvidia/nemotron-3-ultra-550b-a55b` and `nvidia/nemotron-3.5-lightning-30b-a3b` called `read_schematic` first, in about 1 s, with zero reasoning characters.
2. **Thinking must be switched off for tool turns.** `chat_template_kwargs: {"enable_thinking": false}` plus `reasoning_effort: "none"` (both accepted by NIM; harmless elsewhere). With thinking on, the models spend the token budget reasoning and return truncated or empty content (measured in M1).
3. **Short, explicit contracts beat long prompts.** The system prompt states the facts the model otherwise gets wrong: reads exist, browser automation is not an option, pins are named `REF.PIN`, mutations need operator approval. Tool descriptions carry the rest.

## Usage

```bash
set NVIDIA_API_KEY=...                       # never committed, never logged
python tools/sch_dump.py projects/MYBOARD    # read-only check that the bridge reads
python tools/wire.py projects/MYBOARD +3V3 U1.1 C1.1 C2.1          # plan only
python tools/wire.py projects/MYBOARD +3V3 U1.1 C1.1 C2.1 --apply  # create + verify
python tools/desk.py agent projects/MYBOARD "wire the ESP32 decoupling caps to +3V3 and GND"
python tools/desk.py agent projects/MYBOARD "..." --allow-mutation --model nvidia/nemotron-3.5-lightning-30b-a3b
```

Environment: `DESK_AGENT_MODEL` (default `nvidia/nemotron-3-ultra-550b-a55b`), `DESK_HTTP_BASE_URL`, `DESK_HTTP_MAX_TOKENS`.

## Guarantees enforced in code

- Without `--allow-mutation` the `wire_net` schema is not even sent; a model that asks for it gets an error string.
- Every tool call runs through `tools_manifest.dispatch`; exceptions and `SystemExit` become `{"error": ...}` so the loop reports instead of crashing.
- Bounds: `max_turns` (12), `max_tool_calls_per_turn` (6), `budget_sec` (600), per-request timeout ≤ 180 s.
- `wire_net` plans from a fresh read, writes under `ops.write_op` (dirty-flag, recoverable), then re-reads and lists `verified_pins` / `unverified_pins`.
- No browser automation path exists anywhere in DESK; the only transport is the bridge gateway.

## Tests

`tests/test_agent_tools.py` (18 tests, no network): pin resolution and refusal rules, generated JavaScript uses only verified calls, mutation gating, dispatch error handling, loop termination (final / provider error / max turns), trace redaction, request body shape (`tools`, `tool_choice`, `chat_template_kwargs`, `reasoning_effort`).

## Not done

- Live end-to-end run on a disposable project (requires the Captain's authorisation and an open EasyEDA window). The read-back JavaScript is the same as `tools/verify.py`; the wiring JavaScript is the same as `desk/draw.py`.
- Vision (screenshot interpretation) on `nemotron-3.5-super-vl` is still declared-only.
