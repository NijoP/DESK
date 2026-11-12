# DESK × Weft: status

Last updated 2026-11-12. Upstream pin: `61fdacd44b69ef12ca16b30dd533123549e45514` (changelog 0.2.292).

**The integration is not complete.** The DESK side is built and tested, and the workflows compile under the real
Weft compiler. **No workflow has been executed by a Weft runtime yet**: the development machine is Windows, Weft
needs WSL2 and Docker, and WSL2 was enabled but not finished (it needs a restart and a Linux distribution).
Everything that depends on a running Weft is listed below as not executed.

## Executed and passing

| What | How |
|---|---|
| Both workflows compile with 0 errors and 0 warnings | Upstream's compiler at the pin, through the harness, against upstream's 262 catalog node types (`python desk.py weft validate`) |
| The same compiler passes upstream's two example programs and rejects broken DESK graphs (mistyped wire, missing required input, unknown port) | harness; `tests/test_weft_service_runtime.py` |
| 10 DESK nodes run against the real deterministic engines | `tests/test_weft_nodes.py`, temporary project, no bridge, no network |
| Contract enforcement: typed inputs and outputs, timeout, retry, idempotent replay, error codes | `tests/test_weft_nodes.py`, `tests/test_weft_contracts.py` |
| Quality gate fails closed on missing, stale or failing evidence; release needs a recorded manufacturing approval for the same profile | `tests/test_weft_nodes.py` |
| Model node: scoped context, provider failure, retry, malformed output, advisory-only | `tests/test_weft_nodes.py`, fake provider |
| Node service: token, loopback, body cap, end-to-end call sequence over HTTP | `tests/test_weft_service_runtime.py` |
| Runtime adapter: detection, pin match, run arguments, wait-state mapping, no fallback | `tests/test_weft_service_runtime.py`, **fake `weft`** |

76 tests; 2 are skipped on a machine with no Weft compiler.

## Not executed

| What | Why | Risk |
|---|---|---|
| A Weft run of either workflow | no Weft runtime | The graphs compile; their run-time behaviour is unproven |
| Durable wait, human approval pause, worker crash recovery, seeded re-run | no Weft runtime | Described from upstream's source and docs only |
| `weft run --from <node>={"value": ...}` as the way to supply run inputs | no Weft runtime | The flag exists; that it substitutes a `Text` node's output this way is an inference |
| `weft connect` giving the service token to each node's `HttpRequest` | no Weft runtime | From upstream docs; the per-node pick may be tedious for 32 nodes |
| Driving `weft` through WSL, and copying the staged project into the Linux home | no WSL distribution | Written against upstream's stated constraints; untested |
| `weft validate` from a real install | no Weft runtime | The harness runs the same compiler entry point (`compile_strict`, runtime mode) |
| `build-validator --apply-windows-shim` on an unpatched checkout | the scratch checkout was already patched by hand with the identical edit | Low |
| A live model provider | fake provider only | DESK's adapter is unchanged and tested elsewhere |

## Nodes

`python desk.py weft nodes` is the live list. 10 are backed by an engine:

`DeskRequirementIntake`, `DeskRequirementValidator`, `DeskDomainClassifier`, `DeskDesignProfileCompiler`,
`DeskComponentFamilyResolver`, `DeskPowerDistributionAnalyzer`, `DeskQualityGate`, `DeskReleaseGate`,
`DeskApprovalRecorder`, `DeskRequirementExtractor`.

22 are declared and fail closed with `NODE_UNAVAILABLE`, each with its reason. Three kinds:

- **Engine exists, adapter not written yet** (pin map lint, offline ERC, placement, routing plan, copper,
  connectivity, manufacturing checks, component search/identity/verification/BOM).
- **Needs the live EasyEDA bridge or mutates a board** (schematic compile, routing execution, netlist read, DRC,
  release export). These need DESK's write lock, an approval record and explicit authorization before they are
  wired; none is wired.
- **No DESK engine** (datasheet parsing, thermal simulation, block planning, archetype matching).

Consequence: `requirement_to_profile` can run to completion once Weft is up. `hardware_design` expresses the whole
pipeline and stops at the BOM stage today.

## Acceptance criteria

| # | Criterion | State |
|---|---|---|
| 1 | Weft pinned to an explicit version | Done (commit pin) |
| 2 | DESK detects and validates the runtime | Built; tested against a fake `weft` only |
| 3 | Workflows are genuine Weft programs | Done |
| 4 | The Weft compiler validates the workflow | Done, through the harness |
| 5 | Engines callable through reusable nodes | 10 of 32 |
| 6 | Node contracts typed and tested | Done |
| 7 | Model tasks receive scoped context | Done for the one model node, with a fake provider |
| 8 | Durable execution and resume work | **Not demonstrated** |
| 9 | Human approval enforced at defined stages | DESK-side enforcement done; the Weft pause is **not demonstrated** |
| 10 | Workflow records link to DESK evidence | Done (run trace, evidence references) |
| 11 | Errors propagate without bypassing gates | Done on the DESK side and at compile time; **not demonstrated in a run** |
| 12 | Existing deterministic functionality remains | Done (full suite passes) |
| 13 | Clean installation and reproducible integration test | **Not done** |
| 14 | Documentation | Done |
| 15 | Licensing documented | Done ([03_LICENCE.md](03_LICENCE.md)) |

## Next steps

1. Restart Windows, install a WSL2 distribution and Docker, install the pinned Weft ([02_INSTALL.md](02_INSTALL.md)).
2. Run `requirement_to_profile` and correct whatever the "not executed" table gets wrong.
3. Demonstrate pause, approval, crash recovery and seeded re-run; record measured timings.
4. Write adapters for the engines that exist, offline ones first.
5. Design the authorization path for live nodes before wiring any of them.

## Superseded decision

`docs/agent_system/REFERENCE_ARCHITECTURE_ASSESSMENT.md` §5 recommended adopting Weft's concepts only and rejecting
its language, compiler and runtime. The Captain's directive of 2026-11-12 reverses that. The concerns it raised
stand and are handled here: the licence is documented, the upstream instability is met with a commit pin, and no
upstream code is copied.
