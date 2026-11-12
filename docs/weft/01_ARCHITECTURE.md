# DESK × Weft: architecture

**Weft orchestrates. DESK engineers.**

[Weft](https://github.com/WeaveMindAI/weft) (WeaveMind, Inc., O'Saasy licence) is the workflow runtime for DESK's
orchestrated workflows: typed graphs, compilation, durable waits, human approval, run journal. DESK keeps every
engineering decision: classification, profiles, calculations, validation, quality gates, release.

This document describes what is built. For what has actually been executed and what has not, read
[04_STATUS.md](04_STATUS.md) first.

## Integration method

| Option considered | Decision |
|---|---|
| Weft as an external runtime, driven through its CLI | **Chosen.** `desk/weft/runtime.py` runs `weft` natively or through WSL with `--json`. Weft's management HTTP API is unversioned, so DESK does not script it. |
| DESK nodes as native Weft nodes (Rust) | **Deferred.** They cannot be compiled or tested without a Linux Weft runtime, and shipping unverified Rust is worse than not shipping it. |
| DESK nodes as typed Weft groups over the stock `HttpRequest` node | **Chosen.** Each node is a genuine Weft file with typed ports, checked by the Weft compiler, calling a local DESK service. No fork, no custom Rust. |
| Vendoring the Weft source | **Rejected.** Nothing from upstream is copied into this repository. |
| Version pin | The upstream **commit** in `integrations/weft/WEFT_PIN.json`. Upstream has no semantic-versioning policy and says breaking changes are still possible. |

Nothing in DESK imports `desk.weft`; the deterministic engines, tools and tests work without Weft. When Weft is
missing, `python desk.py weft run` exits 3 and says the orchestrated workflow cannot proceed. There is no fallback
orchestrator.

## Layout

```
integrations/weft/
  WEFT_PIN.json                  pinned upstream commit, toolchain, licence
  nodes/desk/*.weft              one typed Group per DESK node  (GENERATED from desk/weft/contracts.py)
  nodes/desk_stages/*.weft       stage groups: understand, bom, components, schematic, layout, verification, release, approve
  workflows/<name>/              a Weft project: weft.toml + src/main.weft
  validator/                     compiler harness source (links upstream's compiler; see 02_INSTALL.md)
desk/weft/
  contracts.py   node contracts: id, version, typed inputs/outputs, errors, timeout, retry, idempotency
  nodes.py       handlers (thin adapters over DESK engines) + the executor that enforces the contract
  store.py       DESK-side records under <project>/state/weft/
  service.py     loopback HTTP node service
  weftgen.py     contracts -> .weft node files
  staging.py     workflow + node library -> a runnable Weft project in .desk_weft/stage/
  runtime.py     detect and drive `weft`; compiler harness
  cli.py         python desk.py weft ...
```

## How a node works

```
Weft program                       DESK node service (127.0.0.1)             DESK engine
classify = @include(".../domain_classifier.weft")
  JsonObject -> HttpRequest  ──POST /v1/nodes/DeskDomainClassifier──▶  executor ──▶ desk.domain_intelligence.api.classify
  Cast -> (value: DeskDomainClassifierEnvelope)  ◀── envelope ──────  validate, time out, retry, replay, trace
```

The envelope of a successful call:

```json
{"node": "DeskDomainClassifier", "version": "1.0.0", "ok": true, "passed": true,
 "outputs": {"primaryArchetype": "buck_converter", "classificationStatus": "CLASSIFIED", "confidence": 0.95, "overlays": [], "missingInformation": []},
 "blockingIssues": [], "evidence": ["..."],
 "provenance": {"engine": "desk.domain_intelligence.api.classify", "inputHash": "...", "idempotencyKey": "...", "replayed": false, "attempts": 1, "durationMs": 3.1}}
```

- `ok` says the call worked. `passed` is the **engineering verdict**. Every downstream stage is gated on the
  `passed` of the stage before it (`_should_flow`), so a blocked stage closes everything after it.
- A failed call answers with an HTTP error status and `{"ok": false, "error": {"code", "message", "retryable"}}`,
  with **no `outputs`**. The node's `Cast` then fails and the run fails. A failure cannot flow on as a result.
- A node declared but not backed by an engine answers `NODE_UNAVAILABLE` (501). It does not pretend.

### What the contract adds that Weft does not have

Weft has no per-node timeout, no retry and no node version field (upstream `TODO.md`, `nodes/metadata.md`). DESK
enforces them on its side of the adapter:

| Policy | Where |
|---|---|
| Typed inputs, required/optional, unknown-key refusal | `NodeContract.validate_inputs`, before any engine runs |
| Typed outputs | `NodeContract.validate_outputs`; an adapter that breaks its contract is an `ENGINE_ERROR` |
| Timeout | per contract (30 s default, 120 s for the model node) |
| Retry | only for `PROVIDER_UNAVAILABLE` and `TIMEOUT`, only where `max_attempts > 1`; deterministic engines are never retried |
| Idempotency | key = sha256(node, version, inputs without the run id). A repeated call returns the stored envelope with `replayed: true` and the engine does not run |
| Version | in the contract, the envelope and the first line of the node file |
| Error contract | twelve codes in `contracts.ERROR_CODES`, each mapped to an HTTP status |

## Data ownership

| Lives in Weft | Lives in DESK |
|---|---|
| Graph state, which node ran, paused runs, human questions, the run journal | Requirement text, compiled profiles, verification evidence, approvals, idempotent results, the per-run trace |
| Project id, hashes, record names, verdicts, short lists | Everything a hash or a record name points to |

Records are files under `<projects_root>/<project_id>/state/weft/` (`requirements/`, `profiles/`, `notes/`,
`evidence/`, `approvals/`, `results/`, `runs/<run id>.jsonl`). `state/` is ignored by git, like DESK's other state.

Nodes exchange **project id, requirements hash, profile hash, evidence record name, approval reference and run
id**. A workflow value is never the engineering record. Traceability runs both ways: the Weft run is tagged with
the project id (`TagRun`), and DESK writes one trace line per node call under the run id, with the evidence
references it produced.

Privacy: Weft journals every value on a wire in plain text. The one document that crosses is the requirement text
given to `DeskRequirementIntake` at the start of a run; after that only its hash travels. No credential, supplier
quote or full engineering document is put on a wire, and `DeskRequirementExtractor` writes model notes to a DESK
record and returns only its name.

## Durable execution and recovery

What Weft provides (read from upstream source at the pin; not yet executed here):

- A run started with `--durable` journals each node start. After a worker crash another worker continues;
  completed nodes are **not** re-executed, their recorded outputs are replayed.
- A `HumanQuery` pauses the run, releases the worker and resumes when the answer arrives. There is no time limit.
- There is **no `resume <run-id>` command**. Resumption is automatic. A failed run cannot be restarted in place;
  `weft run --seed=<run>` starts a new run that reuses the completed nodes.
- Default (non-durable) runs live in worker memory and are cancelled if the worker dies. `desk.py weft run` always
  passes `--durable`.

What DESK adds:

- Idempotent replay, so a seeded re-run or a node re-executed after a crash does not repeat engine work, model
  calls or (later) component searches and routing jobs.
- `python desk.py weft resume <run-id>` reports where the run stands and what resumes it; `--reseed <workflow>`
  starts the seeded run explicitly.
- **Resuming a workflow is not rolling back a board.** A live PCB change is governed by DESK's own lock, mutation
  journal, baseline and readback (`desk/ops.py`, `desk/rework/`). No node in this release mutates a live design:
  mutating nodes are declared, unavailable, and refused by the node service outright.

## Human approval

`nodes/desk_stages/approve.weft` is the one approval group: a `HumanQuery` with an approve/reject field, then
`DeskApprovalRecorder`, which writes a DESK approval record bound to a **subject hash** (the profile hash). The
workflow uses it for the profile, the BOM, the schematic and manufacturing.

Approval is enforced by DESK, not by the shape of the graph: `DeskReleaseGate` refuses (`APPROVAL_REQUIRED`) unless
the referenced record exists, is a manufacturing approval, says approved, and was given for this profile hash; it
then re-evaluates the quality gates. A graph that compiles authorizes nothing.

## Models

DESK's provider adapters are unchanged. A model task is a DESK node (`DeskRequirementExtractor` today) that:

- sends the provider a fixed instruction and the one record it needs, and nothing else;
- validates the answer's shape deterministically and stores it as an **advisory** record;
- never feeds an electrical value into an engine. Classification, profiles and trace widths are computed by DESK
  from the requirements, whatever the model said.

The node service uses DESK's `OpenAICompatAdapter` (NVIDIA NIM by default) when a key is configured, and answers
`PROVIDER_UNAVAILABLE` otherwise. Weft also ships its own provider nodes (`CustomProvider` takes any
OpenAI-compatible base URL; `Pi` and `GoogleAntigravity` exist as agent nodes). They are not used yet: routing
model work through DESK nodes keeps credentials in DESK's vault and validation on DESK's side.

## Tangle and DESK's agent instructions

Tangle is Weft's assistant kit: files copied into a Weft project (`CLAUDE.md`/`AGENTS.md`, skills, a hook that runs
`weft validate` after an edit). Its installer **deletes and rewrites** `AGENTS.md`, `CLAUDE.md` and the skill
folders at the project root, without merging.

- Tangle is therefore never installed at the DESK repository root. If it is wanted, install it inside a staged
  project folder (`.desk_weft/stage/<workflow>/`), which is build output.
- DESK's own instruction system is unchanged; the skill `.agents/skills/weft-orchestration/SKILL.md` carries the
  compatible ideas: validate after every edit to a `.weft` file, build one stage at a time against real output,
  and treat the node contracts as the source of truth.

## Security

- A Weft worker runs as the local user and is not a sandbox (upstream `SECURITY.md`). The workflows use no
  `ExecPython` and no `RunCommand`; a test enforces that.
- The node service binds to loopback, requires a bearer token on every `/v1` call, exposes only the node contracts
  (no shell, no paths, no code), resolves a project id to a folder name under the projects root, and caps bodies.
- The token lives in `DESK_WEFT_TOKEN` or `.desk_weft/service.token` and reaches Weft as a stored connection. It is
  never written in a `.weft` file.
- Weft's install key and credential encryption key are Weft's; set `CREDENTIAL_ENCRYPTION_KEY`, because upstream
  falls back to a public development key when it is unset.
