# Model-agnostic provider layer

**Status:** software-tested with fixtures and a fake in-process provider (`tests/test_model_providers.py`); not validated against live provider endpoints and not validated on a live design.

DESK is the orchestrator; a model is a replaceable component. DESK owns the engineering rules and the system state. Models interpret requirements and propose. Deterministic engines calculate, validators verify independently, and the engineer approves important design mutations. No model is ever the sole authority for electrical correctness. The provider layer (`desk/orchestrator/providers/`) lets any supported model fill the "propose" role without DESK depending on one vendor.

## Pieces

| File | Role |
|---|---|
| `base.py` | The one contract every provider speaks (`ModelProvider.chat` / `stream` / `list_models` / `configured`), the canonical OpenAI-style message format, `ProviderError` (with `retryable` and `kind`), a stdlib `urllib` transport with explicit timeouts, and the SSE parser. |
| `openai_compat.py` | `/chat/completions` + `/models`: OpenAI, xAI Grok, NVIDIA NIM, Ollama, llama.cpp `llama-server`, vLLM. |
| `anthropic.py` | Anthropic Messages API (`tool_use` / `tool_result` blocks, system prompt at top level). |
| `gemini.py` | Gemini `generateContent` (`functionCall` / `functionResponse`, `thoughtSignature` round trip, key in the `x-goog-api-key` header, never in the URL). |
| `prompt_tools.py` | Tool calling through the prompt for models without native tools. DESK still executes every tool itself. |
| `catalog.py` | Provider presets and `ModelDescriptor` capability records: native tools, JSON mode, streaming, vision, context window, thinking control, price. |
| `registry.py` | Registration, lazy credentials, base-URL overrides, discovery. |
| `resilience.py` | Capability gates, timeouts, bounded retry with backoff (honours `Retry-After`), ordered fallback chain. |
| `accounting.py` | One ledger row per attempt: tokens (estimated ones flagged) and cost (known prices only). |
| `allocation.py` | The task class → model tier policy, as data, with an independent verifier role. |
| `bridge.py` | Adapters to `agent_loop.run_agent` (`chat_completion`) and to the L0–L4 `CapabilityRouter` (`execute(TaskRequest)`). |

Everything is standard library. No SDKs.

## Capabilities differ, so DESK adapts per model

For each route, `ResilientClient` reads the model's descriptor and then:

- **Skips** the route when vision is required and the model has none, when the prompt plus the output budget exceeds the context window, or when credentials are missing. The reason is recorded, not hidden.
- **Wraps** the provider in `PromptToolProvider` when tools are requested but the model has no native tool calling.
- **Asks for JSON** natively only when the model supports a JSON mode; otherwise it adds a JSON instruction to the system prompt.
- **Sends thinking control** only to models that support it (for NIM, `chat_template_kwargs.enable_thinking`, the setting verified on 2026-11-11).

Descriptor sources: `verified` (probed by DESK; currently the three NIM models in `capabilities.py`), `operator` (from the catalog file) and `assumed` (provider-kind default). An `assumed` descriptor is never reported as verified. Local servers assume no native tools, so a local model uses the prompt protocol until the operator records otherwise.

## Credentials

Credentials come from the environment or the user config file (`~/.desk/config.json`), then from the DESK vault (`desk.py auth configure <provider>`). Keys: `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`. Local servers need none. Keys are resolved on each request and are never written by this layer, never put in a URL, and redacted from every error message. `desk.config.json` (the repository file) refuses secrets.

## Configuration

- `DESK_<PROVIDER>_BASE_URL` overrides a preset endpoint, e.g. `DESK_OLLAMA_BASE_URL=http://gpu-box:11434/v1`.
- `DESK_MODEL_CATALOG_FILE` adds endpoints and model descriptors:

```json
{"providers": [{"name": "lab-vllm", "kind": "openai_compat", "base_url": "http://127.0.0.1:8000/v1", "key_setting": null}],
 "models": [{"provider": "ollama", "model": "example-model:8b", "context_window": 8192, "native_tools": false,
             "input_per_mtok": 0.0, "output_per_mtok": 0.0}]}
```

- `DESK_MODEL_POLICY_FILE` overrides top-level keys of the allocation policy (`tiers`, `task_classes`, `escalate_domains`, `thinking`, `timeouts_s`). The authority statement can't be overridden.

## Intelligence allocation (`allocation.py`)

| Task class | Tier | Model use |
|---|---|---|
| calculation, validation, drc_erc, repetitive | 0 | none: deterministic DESK code |
| classification, extraction, simple_planning | 1 | small model (JSON for classification and extraction) |
| planning, schematic_review | 2 | capable model; schematic review is verified |
| power_electronics, rf, mains_safety, system_architecture, engineering_tradeoff | 3 | strong reasoning model, plus an independent verifier |
| contradiction_resolution | 4 | frontier model, plus a verifier |
| verification | verifier | the challenger role |

Any task tagged with a domain in `escalate_domains` (mains, power electronics, RF, high voltage, high current, battery, motor drive, isolation) is raised to at least tier 3 with a verifier. Verifier routes put a different provider first, then a different model on the same provider, and never the proposer itself. When no independent verifier is configured, the allocation carries an `open_issue` saying the decision goes to the engineer unverified. An unknown task class is refused.

The default tier routes are the NIM models already used by the router (a test keeps them in step with `router._DEFAULT_MODELS`), so an operator who configures nothing sees no change. The allocation reports a choice; it doesn't run anything by itself.

## Operator-fixed project scope (audit S-5)

`tools_manifest.dispatch` refuses a model-supplied `project` that names anything other than the project the operator started the session with. `wire_net` also refuses to mutate when the session has no operator-fixed project. Before this change, prompt injection could redirect `wire_net` to another project while the approval still read `granted_by="operator"`.

## CLI

```bash
python tools/desk.py models list                     # providers, configuration state, catalog (no network)
python tools/desk.py models discover [openai ...] [--local]   # ask configured providers which models they serve
python tools/desk.py models policy                   # the effective allocation policy
python tools/desk.py models allocate power_electronics [--domain mains]
python tools/desk.py agent projects/<P> "<task>" --model anthropic:<model-id> --fallback gemini:<model-id>,ollama:<model-id>
```

A bare `--model <id>` (no `provider:` prefix) keeps the previous NIM path unchanged. A `provider:model` route, or any `--fallback`, uses the provider layer and writes the usage ledger to `<project>/state/model_usage.jsonl`.

## Not done yet

- No live endpoint has been exercised by this layer. Wire formats follow the providers' public API documentation, and the tests replay synthetic fixtures in those formats.
- Anthropic extended thinking and Gemini thinking budgets aren't wired; those APIs use their defaults.
- Images reach OpenAI-compatible endpoints as `image_url` parts. The Anthropic and Gemini adapters drop image parts (text only).
- No model prices are built in (they'd be invented); cost is reported only for prices the operator records.
- The allocation policy isn't yet called by the role agents or the recovery engine (out of scope here). `CapabilityRouter.dispatch` still has no production callers (audit 5.5).
- Pi CLI shell access (audit S-7) is unchanged.
