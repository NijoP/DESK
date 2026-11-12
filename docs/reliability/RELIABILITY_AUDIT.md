# DESK reliability audit (M0)

Date: 2026-11-12. Scope: the code on `main` at 3f5a1f4 and the UPS_1000 live-test evidence on branch
`origin/ups-1000-live-test` (commit a2822ee, `live-test/ups-1000/`). The evidence was read from the branch
without checking it out and has not been modified. Baseline test suite on this host (Windows 11, Python 3.12):
**713 tests, OK, 8 skipped, 44.7 s**.

Every statement below is tagged with the evidence it rests on. CONFIRMED means the code or the raw log proves it;
PLAUSIBLE means the builder's or examiner's reading is consistent with the evidence but not proven by it;
DISPROVEN means the evidence contradicts the claim.

## 1. What the current code actually does

### 1.1 Bridge (`desk/bridge.py`)
* `get_or_create_session()` binds a call to a window in this order: explicit `window_id`, `project.json["window_id"]`,
  `EDA_WINDOW_ID`, then a UUID scan of `/eda-windows` (`_find_window_for_project`). **If none resolves, the payload
  carries no `windowId` and the gateway executes the script in whatever window is ACTIVE** (KF-20261112-008,
  UPS F-001). The `guard()` prefix then checks the document uuid and, when it differs, calls `openDocument` in that
  foreign window.
* A session is reused for 30 s without re-verifying the window; the window id stored in `project.json` is never
  re-validated before a mutation. A rotated id is only discovered when the gateway rejects the call
  ("EDA window … is no longer connected", INC-20261112-013), which arrives as an HTTP error and is raised as
  `BridgeScriptError`, not as a rotation.
* `ex()` treats `resp["success"]` as the result. There is no readback of any kind inside the bridge; every caller
  decides for itself whether to read back. `check()` only inspects a returned `{error: …}` dictionary.
* Retry policy: on `OSError`/timeout a non-mutating call rescans windows by uuid and retries once; a mutating call
  raises `BridgeMutationTimeout(possibly_mutated=True)` and invalidates the session. No backoff, no circuit breaker.
* The gateway caps a script at 120 s and the JavaScript keeps running after the cap (INC-20261112-007), so a
  "timeout" is routinely case C (executed, response lost) rather than case A (failed before execution).

### 1.2 Operation journal and lock (`desk/ops.py`)
* Per-project `state/write.lock` with O_EXCL creation, PID liveness, process-start-time check against PID reuse,
  owner-verified release, stale reclaim after 1800 s or a dead PID. Journal `state/ops.jsonl` with
  begin / end / fail(dirty) / resolved / approval phases. `MutationPolicy` (record | require) and approval ids.
* Missing: the begin record carries no window id, document uuid, before-state fingerprint or idempotency key, so
  the journal cannot say *which document* a dirty operation touched; recovery (`desk.py recover`) prints hints and
  cannot reconcile against the live document. The lock is per project, not per document; two projects do not
  block each other (correct), two terminals on one project do (correct).

### 1.3 Routing chain (`desk/routing/pipeline.py`, `desk/routing/orchestrator.py`)
* Flow: dump → plan (`RoutingPlanGenerator`) → dense analysis → DSN export → tuning (`DSNTuningEngine`) → structural
  pre-flight (`preflight.run_preflight`: planes, outline, keep-outs) → engine smoke run → **chunked** engine run →
  SES import (delete all tracks/vias, `importAutoRouteSesFile`, save) → widening → repour → readback →
  `PhysicalConnectivityVerifier.verify_board`.
* `execute_routing_chunked()` keeps the best SES across chunks (`chunk_best.ses`) and continues from it
  (`-de dsn+ses`). A chunk that returns no SES ends the loop; it does not delete the best SES. CONFIRMED by
  `tests/test_routing_chunked.py`.
* **Defect (CONFIRMED, UPS F-012 and attempt 6):** the pipeline computes `chunk_passes = max(4, min(8, passes//4))`
  and `chunk_timeout_sec = min(300, mode.timeout_sec)`. Every chunk must therefore complete at least four passes
  within 300 s (+120 s grace in `supervise()`), or it is terminated. Freerouting 2.1.0 ignores `-mp` and
  `job_timeout` (KF-20261111-006), so a chunk never ends by itself; on Windows `_graceful_stop()` is `terminate()`,
  which kills the JVM before it writes the SES. Result: a board whose passes take longer than about 75 s can never
  complete a chunk and every attempt imports nothing. UPS attempt 5: pass 1 took 3 min 4 s, chunk 1 TIMEOUT at
  420.24 s with 5 passes and `ses: false`; attempt 6 (PRECISION, 900 s budget): same 300 s cap, 3 passes, no SES.
  The chunk size is static; measured pass durations (`PassTracker.history[*]["seconds"]`) are collected but not
  used to size the next chunk.
* Progress accounting defect (CONFIRMED, `progress_chunks.json`): `best_unrouted` stays `null` after a timed-out
  chunk although the tracker saw 70, so the operator report says "best None unrouted at pass None".
* `classify_outcome()` returns SUCCESS when the engine exits 0 with a non-empty SES; the number of unrouted
  connections is not part of the verdict. Full connectivity is only established later by `verify_board`, and the
  pipeline's exit code does not depend on it (the run prints the summary and returns 0).
* Engine versions are not profiled. One code path serves 2.0.1, 2.1.0, 2.2.4, 2.4.1 and 2.5.0 with two
  `_version_tuple < (2, 2)` branches (global config, command flags). Known per-version behaviour (2.1.0 ignores
  limits and writes SES only at completion; 2.5.0 honours `max_passes`, rejects `stagnation_pass_limit`, needs
  Java 25) lives in incident prose and comments only.
* The compatibility probe (`_probe_jar_compatibility`) has a 25 s timeout; 2.1.0 blocks on its online version
  check after printing its banner (UPS F-007). The fix exists only on the UPS branch (12 lines, with
  `tests/test_freerouting_probe_timeout.py`), not on `main`.

### 1.4 Spacing rules (`desk/profile.py`, `desk/ipc.py`, `desk/router.py`)
* `RoutingPlanGenerator.generate_plan()` sets each net's `clearance_mil = profile.derive_clearance_mil(net, "GND")`,
  which is `ipc.required_spacing_mil(v_diff) = max(IPC-2221B clearance, IEC 60664-1 creepage, fab minimum)`.
  `DSNTuningEngine.tune_dsn()` writes that number into the net's DSN `(class … (rule (clearance X)))`, where
  Freerouting applies it between that net's copper and **every** other object, including the neighbouring pads of
  the same IC. CONFIRMED by reading `desk/router.py:491` and `:378`.
* UPS numbers (ROUTING_BLOCKERS.md, DSN): 49.21–51.18 mil (1.25–1.30 mm) on VBUS, VIN_RAW, SW, PHASE, SW12, RIP12,
  VOUT_EXT, GH, BST, BST12; IPC-2221B B2 alone would give 0.6 mm for 51–100 V. The creepage table is flagged
  `verified_against_standard = False`.
* Engineering assessment: creepage is a surface-path requirement between parts of a circuit that must be insulated
  from each other; applying it as a copper-to-copper routing clearance on every net at a given potential makes
  nets terminating on a 1.27 mm-pitch package unroutable (the pad gap, about 0.6–0.7 mm, is below the rule before
  any trace exists). The right model separates functional clearance, creepage across a declared insulation
  barrier, fabricator minimum and local pin-field geometry. The UPS requirements call rev A a SELV ≤ 60 V
  functional board with no safety insulation (REQUIREMENTS.md as quoted by the builder); whether creepage applies
  at all is therefore a requirements decision that needs the Captain's sign-off. No spacing value is changed by
  this audit.
* **Claim check.** ROUTING_BLOCKERS.md says the rule "leaves 64 pads with no legal escape". DISPROVEN as a causal
  link: `DensePCBIntelligence` evaluates escapes with `default_clearance_mil = 4.02` (fabricator minimum), not the
  net rule (`desk/routing/density.py:166,294`), and the count (64 NO_LEGAL_ESCAPE, 58 RESTRICTED) is identical in
  runs 1, 2, 3, 5 and 6. Those 64 pads are fine-pitch pads whose neighbour gap is below 2 × 4.02 + 4 mil at the
  fabricator minimum. The rule's effect on pass duration (pass 1 = 4 min 25 s in attempt 6) is PLAUSIBLE but
  not separately measured. Two gaps follow: the pre-flight never evaluates escape against the *actual* net rule,
  and the escape engine reports a QFP edge pad as blocked in all eight directions although the outward direction
  is free (`escape.py:142`), which inflates NO_LEGAL_ESCAPE counts.

### 1.5 Pre-flight (`desk/routing/preflight.py`, pipeline phase 9c/9d)
* Checks: declared planes present in the DSN, exactly one closed outline, no pad inside a routing keep-out, and a
  pin-escape congestion veto (> 1.0). No check of pad-to-pad gap against each net's clearance rule, of routable
  signal layers versus demand, of DSN integrity beyond the boundary, or of engine/Java compatibility beyond the
  smoke run. UPS preflight.json: `passed: true` for a board that was unroutable under its own rules.

### 1.6 Schematic → PCB sync
* `pcb_Document.importChanges()` returns `true` and only opens the Import Changes dialog; `pcb_Net.setNetlist`
  returns `true` and instantiates nothing (UPS F-004, INC-20261111-006). The benchmark script
  (`benchmark-scripts/sync_pcb.py`) already does the right thing locally: count before, call, count after. DESK
  has no general mechanism for this; each tool decides on its own whether to read back.
* Component count went 0 → 123 between polls with no builder call (autockpt.log T+40): a human clicked Apply.
  Counted honestly as one intervention.

### 1.7 Other false-success evidence on `main`'s incident record
* `pcb_PrimitiveLine.delete(ids)` returned `true` while 33 primitives survived (INC-20261112-012).
* `dmt_Pcb.modifyPcbName` returned `true` and renamed a different PCB (INC-20261111-005).
* `overwriteCurrentRuleConfiguration` / `saveRuleConfiguration` return `undefined`/`false` with no effect
  (INC-20261111-006).
* `clearRouting("all")` and `pcb_Drc.check` behave as dialog operations and stall past the 120 s cap
  (INC-20261112-012/013).
None of these has a regression test on `main`; none is in `KNOWN_FAILURES.md` as a failure class.

### 1.8 Learning system
* `learning/incidents/*.md` (free-form since 2026), `learning/index/KNOWN_FAILURES.md` (fifteen KF entries; the
  2026 entries reuse 2025 suffixes, the search table lists only 2025), `learning/index/INCIDENT_INDEX.md`
  (INC-007, -012, -013 missing). There is no programmatic API to create an incident from a failure record;
  `desk/learn/engine.py` mines telemetry for proposals and is unrelated to incidents.

### 1.9 Weft
* `desk/weft/nodes.py` exposes ten deterministic nodes behind typed contracts (`contracts.py`), idempotent by input
  hash, no mutation nodes (`MUTATION_NOT_AUTHORIZED`). Reliability workflows (`api_failure_recovery`,
  `routing_recovery`, `incident_analysis`) do not exist yet. Linux runtime validation is deferred by directive.

### 1.10 Overlapping implementations found
* Stagnation detection exists three times: `PassTracker.stagnated()` (orchestrator), `IntelligentRecoveryEngine.
  record_iteration()` (recovery.py, unused by the pipeline), and chunk plateau logic in `execute_routing_chunked`.
* Failure categories exist as free strings in `recovery.py` (`FAILURE_CATEGORIES`), as status strings in
  `EngineExecutionResult.status`, and as typed exceptions in `desk/errors.py`. None is shared with the bridge.
* Window discovery by uuid exists in `bridge._find_window_for_project` (document uuid) and in the benchmark
  `rebind.py` (project uuid via `dmt_Project.getCurrentProjectInfo`). Only the latter refuses on ambiguity.

## 2. UPS_1000 traceability matrix

| Failure | Observed evidence | Root cause | Affected module | Required permanent fix | Regression test |
|---|---|---|---|---|---|
| F-001 three windows, unbound calls go to the active window (project "light") | failure_register F-001; `tools/ping.py` has no window binding; bridge sends no `windowId` when unresolved | CONFIRMED: `get_or_create_session` falls through to "no windowId"; gateway default is the active window | `desk/bridge.py` | Project identity object (`ProjectSession`) with verified project uuid; refuse to execute a mutation without a verified binding; read-only calls without binding must say so | `tests/test_reliability_sessions.py` (unbound mutation refused; three windows, two similar names) |
| F-002 gateway reconnect rotated all window ids (671ec3d9 → a03bf2c1); `resolve` failed closed | failure_register F-002; INC-20261112-013 (three ids in minutes) | CONFIRMED: ids are per connection; stale id is stored in project.json and only rejected by the gateway | `desk/bridge.py`, `project.json` | Rotation detection, invalidate, rediscover by project+document uuid, rebind only if exactly one window matches, verify document uuid again, resume only read-safe work | `tests/test_reliability_sessions.py` (rotation rebinds when unambiguous; ambiguous refuses; restart mid-mutation marks UNKNOWN) |
| F-003 `domains validate` swallowed `--project` value (silent wrong result) | failure_register F-003; fix + test on UPS branch | CONFIRMED (builder) | `tools/desk.py` | Already fixed on the UPS branch; bring to `main` | `tests/test_domains_cli_args.py` (UPS branch) |
| F-004 / B-001 `importChanges()` → `true`, PCB component count stays 0; `setNetlist` → `true`, 0 components | failure_register F-004; INC-20261111-006; autockpt T+40 | CONFIRMED: dialog operation; return value is not completion | `desk/bridge.py` callers, no sync tool on `main` | API capability registry marking these as DIALOG / FALSE_SUCCESS-prone with a mandatory readback contract (component count, pad/net map); classify as API_FALSE_SUCCESS when readback is unchanged | `tests/test_reliability_api.py` (importChanges true without components is API_FALSE_SUCCESS) |
| F-005 passives stacked on one spot, 277 gate errors | failure_register F-005; fix on UPS branch, no test | CONFIRMED (builder) | `tools/pcb_place.py` | On the UPS branch (collision-aware legalisation); needs a unit test before merge | none yet (UPS branch) |
| F-006 POSIX jar path on Windows; no planes declared | failure_register F-006 | Builder error + pre-flight warning | `desk/routing/orchestrator.py` | Engine discovery should reject a non-existent path with a classified EXTERNAL_TOOL_UNSUPPORTED record naming the path | `tests/test_reliability_routing.py` (unresolvable engine path is classified) |
| F-007 probe of 2.1.0 blocks on online version check > 25 s | failure_register F-007; fix + 3 tests on UPS branch | CONFIRMED | `desk/routing/orchestrator.py::_probe_jar_compatibility` | On the UPS branch; bring to `main` and fold into the engine capability profile | `tests/test_freerouting_probe_timeout.py` (UPS branch) |
| F-008 placement gate passes with decaps 3.7–14.7 mm from pins | failure_register F-008; examiner | CONFIRMED gate gap (rule not evaluated) | `tools/pcb_check.py` | Out of this directive's scope (placement rule evaluation); recorded as an open DESK gap | none |
| F-009 profile compiler ignores board size / stackup | failure_register F-009 | CONFIRMED limitation | `desk/domain_intelligence` compiler | Out of scope here; recorded | none |
| F-010 attempt 3: 0 passes in 420 s, pre-poured inner fills in the DSN | route_run3.txt (TIMEOUT, 0 passes); builder attributes to a DSN load exception; the attempt-3 freerouting.log is not in the records | PLAUSIBLE (fills) / CONFIRMED (chunk timeout with 0 passes, no SES) | `desk/routing/pipeline.py`, `desk/routing/preflight.py` | Pre-flight must detect pours exported as pins and a chunk with 0 passes after the first expected pass time must be classified ROUTER_ENGINE_CRASH / DSN load failure, not a generic TIMEOUT | `tests/test_reliability_routing.py` (zero passes in a chunk is not a plain timeout) |
| F-011 hand-edited profile keys → loader TypeError → currents undeclared → STOP | route_run4.txt | CONFIRMED (fail-closed behaviour correct) | `desk/profile.py` | Classify as DESIGN_PROFILE_INVALID with the offending key, instead of a warning followed by an unrelated STOP | `tests/test_reliability_routing.py` (invalid profile is classified, not ignored) |
| F-012 / attempt 6: 106→70 (5 passes, ~84 s/pass) then chunk TIMEOUT at 420 s, no SES; attempt 6 103→90 (3 passes) same | route_run5/6.txt, freerouting.log, progress_chunks.json | CONFIRMED DESK defect: static chunk (≥ 4 passes, ≤ 300 s), engine ignores limits, Windows terminate loses the SES | `desk/routing/pipeline.py`, `orchestrator.execute_routing_chunked` | Adaptive chunking from measured pass time (first chunk 1 pass, then passes = floor(safe_window / p95 pass time), never below 1); respect the engine profile's real timeout semantics; keep a routing checkpoint with the best valid SES; classify CHUNK_TIMEOUT vs ENGINE_TIMEOUT vs SES_NOT_GENERATED | `tests/test_reliability_routing.py` (adaptive chunk sizes from measured passes; timed-out chunk never discards the best SES; best unrouted reported after a timeout) |
| Root blocker: creepage applied as router clearance on 1.27 mm-pitch IC nets | ROUTING_BLOCKERS.md; `desk/router.py:491`, `desk/ipc.py::required_spacing_mil` | CONFIRMED model defect (clearance and creepage merged with `max`) | `desk/ipc.py`, `desk/profile.py`, `desk/router.py` | Separate functional clearance, creepage across a declared barrier, fabricator minimum and pin-field geometry; emit a BLOCKING engineering decision (approval required) when a net rule cannot be met at its own pads; never lower a safety value automatically | `tests/test_reliability_spacing.py` (creepage not used as pin-field clearance; unmeetable rule is a blocking decision) |
| "64 pads NO_LEGAL_ESCAPE caused by the rule" | dense_analysis counts identical across runs; `density.py` uses 4.02 mil | DISPROVEN as stated; the 64 are a fine-pitch geometry/escape-engine result | `desk/routing/escape.py` | Pre-flight feasibility must evaluate each pad against its net's actual rule and report pad, component, net, rule and gap; escape engine must allow outward escape for edge pads | `tests/test_reliability_spacing.py` (feasibility names pad, net, rule and gap) |
| DRC count 349 vs "1 violations" at the release gate | drc_s4_unrouted.json vs release_attempt_revA_2.txt | Unreconciled; two counting methods | `tools/release.py`, `tools/drc.py` | Out of this directive's scope; recorded | none |
| Decap distance, M4 holes, stackup TBD, RK-01..05, V-01..10, M-01..13 | FINAL_BENCHMARK_REPORT.md | Design and tooling gaps, not reliability failures | various | Out of scope; recorded as external limitations | none |

## 3. Evidence of what a "test pass" did not cover
The baseline suite (713 OK) ran while the UPS board was unroutable and while the bridge could still mutate a foreign
window. Nothing in the suite simulates window rotation, a false-success API return, a chunk that times out before
its first SES, or a clearance rule that cannot be met at a pad. Section 2's last column lists the tests that will
close each gap.

## 4. Decisions carried into M1
1. One typed failure model (`desk/reliability/models.py`) used by the bridge, the journal, the routing chain and the
   agent; existing status strings map into it rather than being replaced.
2. Project identity is a verified `(project_uuid, document_uuid)` pair, never a window id alone.
3. Every live mutation goes through one `MutationContract` (precondition, target identity, journal, execute,
   readback, postcondition, fingerprint) with an operation-specific verifier; `write_op` gains the identity fields.
4. Routing becomes checkpoint-driven: `RoutingCheckpoint` owns the best valid SES; chunks are sized from measured
   pass durations; engine behaviour comes from a per-version `EngineProfile`.
5. Spacing is modelled as separate quantities with a declared barrier; an unmeetable rule is a blocking decision
   record, never an automatic reduction.
6. Recovery is policy-gated (`AUTO`, `APPROVAL`, `REFUSE`) and journalled; verification is a separate step that
   reads the live state.
