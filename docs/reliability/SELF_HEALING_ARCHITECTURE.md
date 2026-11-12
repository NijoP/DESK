# DESK self-healing architecture (M1)

Status: implemented and unit-tested offline on 2026-11-12 (see `tests/test_reliability_*.py`,
`tests/test_weft_reliability_nodes.py`). Live validation against EasyEDA Pro and a Freerouting run on a real board
has **not** been performed in this pass and is listed under "Not yet verified" at the end. Read
`docs/reliability/RELIABILITY_AUDIT.md` first: every design decision below answers a failure in its traceability matrix.

## 1. Principle

DESK observes what happened, establishes facts, classifies the failure, identifies the cause with a stated confidence,
selects a recovery whose risk class the policy allows, executes it, reads the live state back, verifies the
postcondition independently, records the outcome and learns from it. A recovery is successful only when the
independent verification passes. HTTP 200, a JavaScript `true`, exit code 0 or a model's confidence never establish
success on their own.

```
OBSERVE -> COLLECT EVIDENCE -> CLASSIFY -> IDENTIFY ROOT CAUSE -> ASSESS CONFIDENCE AND RISK -> SELECT RECOVERY PLAN
-> CHECK PERMISSIONS AND SAFETY -> EXECUTE RECOVERY -> READ BACK -> INDEPENDENTLY VERIFY -> RECORD -> LEARN
```

The lifecycle is `desk.reliability.supervisor.Supervisor.handle()`. Its record, `FailureRecord`, answers the seven
questions (`Supervisor.explain()`): what failed, where, why, which evidence proves it, the safest recovery, what
changed, and whether verification passed. A record with `healed == False` is never reported as healed.

## 2. Package layout (`desk/reliability/`)

| Module | Responsibility | Used by |
|---|---|---|
| `models.py` | 30 `FailureCategory` values, `ExecutionState` (API cases A-H), `Confidence`, `RiskClass`, `FailureRecord` with identity, fingerprints, evidence, hypotheses, plan, outcomes, verification; `redact()` keeps secrets out | everything |
| `project_isolation.py` | `ProjectSession`, `SessionResolver` (discover windows, bind by project/document uuid, refuse ambiguity, verify the active document, rebind after rotation) | `desk.bridge`, `tools/rebind.py`, supervisor |
| `api_registry.py` | observed API capabilities (VERIFIED / EXPERIMENTAL / DIALOG / UNSUPPORTED / UNKNOWN) with evidence, and the per-method verification contracts | `mutation.py`, planner |
| `mutation.py` | `MutationContract`: precondition, journal BEGIN with identity and fingerprint, target check, execute, readback until settled, postcondition, fingerprint comparison, `reconcile()` for unknown outcomes | live mutations |
| `retry_policy.py`, `circuit_breaker.py` | bounded retries gated on execution state; breakers per service | `desk.bridge`, executor |
| `failure_classifier.py`, `registry.py` | exceptions / engine results / text → category + state; known-failure signatures with evidence | supervisor, pipeline |
| `evidence.py` | layer 1: windows, session, journal, route files, engine versions, resources, known matches → facts with evidence ids | supervisor, Weft nodes |
| `root_cause.py` | layer 2 deterministic rules → hypotheses with confidence; layer 3 diagnostic packet, model answer validation, builder/evaluator comparison | supervisor |
| `recovery_policy.py`, `recovery_planner.py`, `recovery_executor.py` | AUTO / APPROVAL / REFUSE classes, attempt limits, no repetition on unchanged evidence; category → plan; handler execution with independent verification | supervisor |
| `health_monitor.py`, `resource_monitor.py` | per-project component health; deadlines, RSS, child-process registry | dashboard, long runs |
| `learning.py` | incidents in `learning/incidents/` (template layout), `RECOVERY_OUTCOMES.jsonl`, promotion to a CONFIRMED known failure after two independent sessions with a deterministic cause | supervisor |

Routing-side modules: `desk/routing/engine_profiles.py` (per-version measured behaviour), `desk/routing/adaptive.py`
(chunk planner from measured pass durations, chunk outcome names), `desk/routing/checkpoint.py` (best valid SES,
never discarded), `desk/routing/feasibility.py` (per-pad rule check before the engine runs), `desk/spacing.py`
(clearance, creepage, fabricator minimum and pin-field gap kept apart; engineering decisions).

## 3. Failure model

Every failure carries a `FailureCategory` (the thirty classes in the directive), an `ExecutionState` that says what is
known about whether the request ran, a before and after state fingerprint, the project / document / window / session
/ operation / run identity, the command, engine and API versions, log tails, request and response metadata, evidence
references, hypotheses with confidence, the plan, the outcomes and the verification. `FailureRecord.to_dict()` masks
credential-like keys and API-key-like values; records are appended to `projects/<P>/state/reliability/failures.jsonl`.

Execution states map the API failure cases: A `NOT_EXECUTED`, B `GATEWAY_NOT_EXECUTED`, C `EXECUTED_RESPONSE_LOST`,
D `PARTIAL`, E `EXECUTED_STALE_READBACK`, F `FALSE_SUCCESS`, G `UNSUPPORTED`, H `WRONG_DOCUMENT`, plus
`EXECUTED_VERIFIED` and `UNKNOWN`.

## 4. Project and window identity

* Identity is the project uuid from `project.json` and the bound document uuids. A window id is a transport address
  that rotates on every gateway reconnect; it is stored only as a cache and re-validated by identity.
* `SessionResolver.resolve()` binds only when exactly one connected window hosts the project; zero or several raise
  `IdentityUnverified`. A name is never a match.
* `desk.bridge.ex()` refuses a mutating script (flagged or detected by `looks_mutating`) without a verified binding
  unless the operator explicitly accepts the active window (`allow_unbound`, `DESK_ALLOW_UNBOUND_WINDOW=1`). A read
  without binding still runs and the session records `bound_by="unbound"`.
* "window … is no longer connected" means the gateway refused before executing: the bridge rebinds by uuid (one match
  only), bumps `window_generation`, persists the new id and resends once. A mutation timeout is never resent.
* The invariant before and after every contract mutation: `EXPECTED DOCUMENT UUID == ACTIVE DOCUMENT UUID` in the bound
  window (`SessionResolver.verify_target`). `MutationContract.run()` raises before BEGIN when it fails and marks
  `WRONG_DOCUMENT` when the document changed after execution.
* Locks stay per project (`desk/ops.py`): independent projects proceed concurrently, one project has one writer. The
  journal BEGIN record now carries `window_id`, `document_uuid`, `before_fingerprint`, `idempotency_key`, `methods`;
  END / fail carry `execution_state`, `after_fingerprint`, `verified`.
* `tools/rebind.py projects/<P>` binds or rebinds from the CLI; `--list` shows every window with its project.

## 5. API failure intelligence

* `api_registry.CAPABILITIES` records what each method was observed to do, on which document type, with which
  parameters, its return shape, the verification contract that proves it, its limitations and the evidence (incident or
  live-test ids). `importChanges` and `clearRouting` are DIALOG; `modifyPcbName`, the rule-configuration writers and
  `sch_Netlist.getNetlist` are UNSUPPORTED; `pcb_PrimitiveLine.delete` is EXPERIMENTAL (survivors after `true`). Unknown
  methods are UNKNOWN, never inferred.
* Verification contracts are operation-specific: `count_increased`, `ids_absent`, `ids_present`, `document_uuid`,
  `coordinates`, `copper_counts`, `pin_net_map`, `pour_present`, `value_equals`. An unknown contract fails closed.
* `MutationContract` declares `FALSE_SUCCESS` when the call returned a value, the readback fingerprint is unchanged
  after the settle re-reads and the postcondition is unmet; `PARTIAL` when the state changed but the postcondition is
  unmet; `EXECUTED_VERIFIED` only when the contract passes.
* Unknown outcomes are reconciled (`reconcile()`): read the document, compare against the postcondition, report
  complete / absent / partial. The retry policy never repeats a non-idempotent mutation whose state is UNKNOWN,
  PARTIAL or EXECUTED_RESPONSE_LOST; transient reads retry with exponential backoff and jitter; the gateway port has a
  circuit breaker.

## 6. Routing recoverability

* **Spacing model** (`desk/spacing.py`): functional clearance (IPC-2221B), creepage (IEC 60664-1, only across a
  declared `insulation_barriers` entry), fabricator minimum and the measured pin-field gap are separate quantities.
  `DesignProfile.spacing_policy` defaults to `CREEPAGE_AS_CLEARANCE`, which reproduces the historical rule exactly
  (`tests/test_reliability_spacing.py::LegacyEquivalence`); `FUNCTIONAL` is a Captain decision recorded in the ledger.
  Nothing lowers a rule automatically.
* **Feasibility gate** (`desk/routing/feasibility.py`, pipeline phase 9e): every pad is checked against its net's
  actual rule with axis-aware pad rectangles; classes `LEGAL_AND_ROUTABLE`, `ROUTABLE_WITH_*`, `BLOCKED_BY_*`,
  `UNKNOWN`. A rule above the pin-field gap of its own package produces an `EngineeringDecision` (BLOCKING, with
  options) and the run stops with `EngineeringDecisionRequired` before the engine starts; `--acknowledge-blocked`
  records the operator's choice as an approval and continues.
* **Engine profiles** (`desk/routing/engine_profiles.py`): per-version measured facts (2.1.x ignores limits and writes
  the SES only at 100 %, probe blocks online; 2.5 honours `max_passes`, rejects the stagnation flag, needs Java 25;
  2.2 / 2.4 not measured). An unboundable engine is refused before the first chunk (`ENGINE_UNBOUNDABLE`).
* **Adaptive chunks** (`desk/routing/adaptive.py`): the first chunk measures (two passes); later chunks fit
  `safety × window` of measured p95 pass time (never below one pass, with a longer window when one pass is slower
  than the window), bounded by the remaining budget. Chunk outcomes: `ENGINE_TIMEOUT`, `ENGINE_CRASH`,
  `CHUNK_TIMEOUT`, `ZERO_PASSES_TIMEOUT`, `SES_NOT_GENERATED`, `SES_CORRUPTED`, `SES_NOT_IMPROVED`,
  `PARTIAL_ROUTING_SUCCESS`, `FULL_ROUTING_SUCCESS`, `ENGINE_IGNORES_LIMITS`.
* **Checkpoint** (`desk/routing/checkpoint.py`): `chunk_best.ses` is adopted only after validation (parses, balanced,
  carries routes) and only when better; atomic replace; a DSN change archives it; `observed_best_unrouted` is tracked
  even when no SES exists. A timed-out, crashed or corrupt chunk leaves it untouched.
* **Verdict**: the pipeline prints `ROUTING VERDICT: FULL|PARTIAL` from the physical connectivity readback and
  returns 3 on PARTIAL; an engine SUCCESS is not a routing verdict. Engine failures write
  `state/route/route_failure.json` as a `FailureRecord`.

## 7. Diagnosis

* Layer 1 (`evidence.py`) establishes facts with ids. Layer 2 (`root_cause.diagnose`) applies rules; only rules assign
  `CONFIRMED`. Layer 3 receives `diagnostic_packet()` (facts, evidence ids, deterministic hypotheses, allowed
  recovery kinds, answer schema, rules) and its answer passes `validate_model_diagnosis()`: each fact must cite an
  evidence id from the packet, an uncited fact invalidates the diagnosis (UNVERIFIED), CONFIRMED from a model is
  demoted, categories and recovery kinds must exist. An independent evaluator answer is compared by `evaluate()`:
  agreement yields the weaker confidence; disagreement preserves both and requires more evidence or a human.

## 8. Recovery policy

* `AUTO`: rebind / verify identity, bind by uuid, retry a not-executed read, reconnect the gateway, restart a helper,
  recreate a temporary workspace, resume from the checkpoint, re-plan a chunk, select a compatible engine or the bundled
  JDK, reconcile by readback, wait for or reclaim a dead lock, re-export the DSN without pours, adjust routing priority
  or via cost.
* `APPROVAL`: any clearance / creepage / voltage / current change, moving critical parts, modifying the switching loop,
  deleting tracks or copper, rip-up, stackup changes, DRC / ERC overrides, requirement changes, repeating an uncertain
  non-idempotent mutation, power polygons, placement refinement, corridor reservation, width changes, engineering
  decisions, human Apply in a dialog, budget extension, escalation.
* `REFUSE`: bypassing a quality gate, weakening a safety rule, mutating another project, forcing a release, marking a
  gate passed, any unknown action.
* Attempts per failure are bounded (default 3); the same action is not repeated for a failure while the evidence
  signature is unchanged; a recovery that failed for a signature is not proposed again without new evidence
  (`RECOVERY_OUTCOMES.jsonl`). `DESK_RELIABILITY_AUTORECOVER=0` turns AUTO into proposals.

## 9. Learning

`IncidentWriter` renders a failure as an incident in the template layout (what happened, expected, actual, root cause,
evidence, confidence, recovery, whether it worked, regression test, prevention, related incidents) and appends to the
incident index. `promote_known_failure()` needs at least two independent sessions with a deterministic CONFIRMED or
STRONGLY_SUPPORTED cause; model explanations are never promoted.

## 10. Weft

Four read-only nodes expose the layer to Weft workflows (`desk/weft/contracts.py`, generated files under
`integrations/weft/nodes/desk/`): `DeskFailureRecorder`, `DeskFailureDiagnoser`, `DeskRecoveryPlanner`,
`DeskRoutingCheckpointStatus`. `DeskRecoveryExecutor` is declared unavailable and mutating: live recovery runs inside
the DESK process where the bridge can read back. Linux runtime execution of these workflows is deferred and not
claimed.

## 11. Not yet verified (honest list)

* No live EasyEDA session was used: window rotation, false-success readback and the rebind path are proven against a
  fake gateway only.
* No Freerouting run was executed: adaptive chunking, checkpoints and engine profiles are proven against mocked engine
  results and the UPS_1000 logs. The 2.2.4 / 2.4.1 profiles are marked unmeasured.
* The spacing policy `FUNCTIONAL` is implemented but no project uses it; the IEC table remains
  `verified_against_standard = False`.
* Existing tools (`tools/build.py`, `tools/wire.py`, `tools/pcb_place.py`) still use the bridge directly rather than
  `MutationContract`; the bridge-level identity refusal protects them, the per-operation postcondition does not yet.
* The UPS_1000 `pcb_place.py` collision fix and `copper_fill.py --remove` remain on the `ups-1000-live-test` branch.
