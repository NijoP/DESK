# DESK × Weft: status

Last updated 2026-11-12. Upstream pin: `61fdacd44b69ef12ca16b30dd533123549e45514` (changelog 0.2.292).

| Track | State |
|---|---|
| **DESK development** (contracts, node service, adapter, workflows, tests, Linux package) | **Continuing** on the Windows development machine |
| **Weft runtime installation and end-to-end workflow execution** | **Deferred** to a separate Linux machine, by the Captain's decision of 2026-11-12. The Windows machine is not restarted or reconfigured for it |

**The integration is not complete. No workflow has been executed by a Weft runtime.** What depends on a running
Weft is listed below as deferred. The procedure that will execute it is ready:
[05_LINUX_VALIDATION.md](05_LINUX_VALIDATION.md).

Labels used below:

| Label | Meaning |
|---|---|
| PASSED | executed in this repository's test suite on the development machine |
| VERIFIED FROM SOURCE | checked against the pinned upstream source, or computed by upstream's own code through the compiler harness; nothing was run on a Weft runtime |
| MOCK TEST PASSED — LIVE VALIDATION PENDING | tested against a fake `weft` or a fake dispatcher |
| NOT RUN — ENVIRONMENT DEFERRED | needs the Linux machine |
| BLOCKED — EXTERNAL RUNTIME REQUIRED | needs a live outside service (model provider, EasyEDA) |

## Executed or verified

| What | State | How |
|---|---|---|
| Both workflows compile with 0 errors, 0 warnings | PASSED | Upstream's compiler at the pin, through the harness, built with upstream's Rust 1.99.1 (`desk.py weft validate`) |
| The compiler passes upstream's examples and rejects broken DESK graphs (mistyped wire, missing input, unknown port) | PASSED | harness; `tests/test_weft_service_runtime.py` |
| **Weft admits the runs DESK starts**: the flags `desk.py weft run` passes are judged by upstream's admission check (`run_spec::judge`, behind `weft run --check` and the dispatcher). `GetRunId` and `TagRun` are inside the run's cut. An unknown start node or a non-JSON value is refused | VERIFIED FROM SOURCE (upstream code, executed through the harness) | `desk.py weft check-run`; `test_weft_admits_the_runs_desk_starts` |
| Run inputs: `--from <node>={"value": ...}` hands the `value` **input port** of a `Text` node | VERIFIED FROM SOURCE | `catalog/basic/text/metadata.json`; `crates/weft-cli/src/main.rs` (`--from`); test reads upstream's metadata |
| Upstream's admission check does **not** refuse an unknown port name | VERIFIED FROM SOURCE (found by probing) | so the port is checked against the catalog metadata instead |
| `weft --json run` prints NDJSON `{tsUnix, verb, phase, detail}`, run id in `detail.runId` | VERIFIED FROM SOURCE | `crates/weft-cli/src/progress.rs`, `commands/run.rs` |
| Every DESK `HttpRequest` site, spelled for `weft connect` (7 in `requirement_to_profile`, 32 in `hardware_design`) | VERIFIED FROM SOURCE (upstream `address_of`, executed through the harness) | `desk.py weft addresses`; `test_every_desk_node_call_is_listed_for_the_connection_pick` |
| An unpicked DESK call carries no key and gets 401, so the run fails closed | VERIFIED FROM SOURCE (connection optional on `HttpRequest`) + PASSED (service refuses without token) | `catalog/http/request/metadata.json`; service tests |
| Headless approval: signal token, `GET /signal-token/signals`, `POST /signal/<link>` `{"decision": "approve"/"reject"}`, `/skip` | VERIFIED FROM SOURCE; MOCK TEST PASSED (fake dispatcher) | dispatcher routes, upstream e2e client, `signal/form/fields.rs`; `SignalTests` |
| 10 DESK nodes against the real deterministic engines | PASSED | `tests/test_weft_nodes.py` |
| Contract enforcement: typed inputs/outputs, timeout, retry, idempotent replay, error codes | PASSED | `tests/test_weft_nodes.py`, `tests/test_weft_contracts.py` |
| Quality gate fails closed on missing/stale/failing evidence; release needs a recorded manufacturing approval for the same profile | PASSED | `tests/test_weft_nodes.py` |
| Model node: scoped context, provider failure, retry, malformed output, advisory only | MOCK TEST PASSED — LIVE VALIDATION PENDING (fake provider) | `tests/test_weft_nodes.py` |
| Node service: token, loopback, body cap, end-to-end call sequence over HTTP | PASSED | `tests/test_weft_service_runtime.py` |
| Runtime adapter: detection, pin match, run and check arguments, wait-state mapping, no fallback | MOCK TEST PASSED — LIVE VALIDATION PENDING (fake `weft`) | `tests/test_weft_service_runtime.py` |
| The Linux validation fixture passes the six DESK stages the run expects; the trace checker's verdicts; every node a script names exists; secrets only reach environment variables | PASSED | `tests/test_weft_linux_package.py` |
| Linux scripts parse | PASSED (`bash -n`; no script was run) | `integrations/weft/linux/*.sh` |

## Deferred

| What | State | Risk if the source reading is wrong |
|---|---|---|
| Installing the pinned Weft from source as the default install | NOT RUN — ENVIRONMENT DEFERRED | Build failure on the pinned toolchain; `WEFT_INSTALL=default` behaviour on a detached checkout |
| A Weft run of `requirement_to_profile` | NOT RUN — ENVIRONMENT DEFERRED | The graph is admitted; run-time behaviour unproven |
| Durable wait, approval pause, resume after answer | NOT RUN — ENVIRONMENT DEFERRED | — |
| A parked run surviving a runtime restart | NOT RUN — ENVIRONMENT DEFERRED | Durability is opt-in (`--durable`), which DESK sets |
| `weft connect --door own --set-env` and `--grant` over 7 + 32 sites | NOT RUN — ENVIRONMENT DEFERRED | Field names `header`/`value` read from the catalog; unexecuted |
| The listed signal's `nodeId` spelling matching `approve.review` | NOT RUN — ENVIRONMENT DEFERRED | `desk.py weft answer` refuses rather than guesses; the operator reads `desk.py weft signals` |
| `hardware_design` failing closed at the first unwired stage (Cast of an error envelope fails the run) | NOT RUN — ENVIRONMENT DEFERRED | If the run completes or parks instead, that is a fail-open defect to fix before anything else |
| Seeded re-run (`--seed=<run>`) reusing completed nodes | NOT RUN — ENVIRONMENT DEFERRED | — |
| `weft validate` from a real install (the harness runs the same compiler entry point) | NOT RUN — ENVIRONMENT DEFERRED | Low |
| Full suite on Linux with Weft present | NOT RUN — ENVIRONMENT DEFERRED | — |
| Driving Weft through WSL from Windows | NOT RUN — ENVIRONMENT DEFERRED (no WSL distribution; not pursued) | Untested path in `runtime.py` |
| A live model provider through the model node | BLOCKED — EXTERNAL RUNTIME REQUIRED | DESK's adapter is unchanged and tested elsewhere |
| `build-validator --apply-windows-shim` on an unpatched checkout | NOT RUN (the scratch checkout was already patched with the identical edit) | Low |

## Nodes

`python desk.py weft nodes` is the live list. 10 are backed by an engine:

`DeskRequirementIntake`, `DeskRequirementValidator`, `DeskDomainClassifier`, `DeskDesignProfileCompiler`,
`DeskComponentFamilyResolver`, `DeskPowerDistributionAnalyzer`, `DeskQualityGate`, `DeskReleaseGate`,
`DeskApprovalRecorder`, `DeskRequirementExtractor`.

22 are declared and fail closed with `NODE_UNAVAILABLE`, each with its reason. There are three kinds:

- **The engine exists, the adapter is not written yet.** Pin map lint, offline ERC, placement, routing plan,
  copper, connectivity, manufacturing checks, and component search, identity, verification and BOM.
- **The node needs the live EasyEDA bridge or changes a board.** Schematic compile, routing execution, netlist
  read, DRC and release export. Before any of these is wired it needs DESK's write lock, an approval record and
  explicit authorization. None is wired.
- **There is no DESK engine.** Datasheet parsing, thermal simulation, block planning and archetype matching.

As a result, `requirement_to_profile` can run to completion once Weft is up. `hardware_design` expresses the
whole pipeline but stops at the BOM stage today.

## Acceptance criteria

| # | Criterion | State |
|---|---|---|
| 1 | Weft pinned to an explicit version | Done (commit pin) |
| 2 | DESK detects and validates the runtime | Built; mock-tested only |
| 3 | Workflows are genuine Weft programs | Done |
| 4 | The Weft compiler validates the workflow | Done, through the harness; runs admitted by upstream's admission check |
| 5 | Engines callable through reusable nodes | 10 of 32 |
| 6 | Node contracts typed and tested | Done |
| 7 | Model tasks receive scoped context | Done for the one model node, with a fake provider |
| 8 | Durable execution and resume work | **Not demonstrated** (deferred; scripted in `40_...sh`) |
| 9 | Human approval enforced at defined stages | DESK side done; headless answering verified from source and mock-tested; the Weft pause is **not demonstrated** |
| 10 | Workflow records link to DESK evidence | Done (run trace, evidence references) |
| 11 | Errors propagate without bypassing gates | Done on the DESK side and at compile time; **not demonstrated in a run** (scripted in `50_...sh`) |
| 12 | Existing deterministic functionality remains | Done (full suite passes) |
| 13 | Clean installation and reproducible integration test | **Procedure ready, not executed** ([05_LINUX_VALIDATION.md](05_LINUX_VALIDATION.md)) |
| 14 | Documentation | Done |
| 15 | Licensing documented | Done ([03_LICENCE.md](03_LICENCE.md)) |

## Next steps

1. On the Linux machine: run [05_LINUX_VALIDATION.md](05_LINUX_VALIDATION.md) and return `results.tsv` and the
   bundle.
2. Correct whatever the deferred rows get wrong; fix any fail-open result first.
3. Write adapters for the engines that exist, offline ones first, so `hardware_design` gets past the BOM stage.
4. Design the authorization path for live nodes before wiring any of them.

## Superseded decision

`docs/agent_system/REFERENCE_ARCHITECTURE_ASSESSMENT.md` §5 recommended adopting Weft's concepts only and rejecting
its language, compiler and runtime. The Captain's directive of 2026-11-12 reversed that. The concerns it raised
still stand and are handled here:

- the licence is documented;
- upstream instability is handled with a commit pin;
- no upstream code is copied.
