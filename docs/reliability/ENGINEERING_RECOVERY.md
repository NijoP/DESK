# DESK engineering recovery engine (B1-B5)

DESK owns the engineering rules and the state. Models may propose, deterministic engines calculate, validators verify,
and the engineer approves APPROVAL-class changes. Everything here is pure standard-library Python on append-only files,
with no Backpass dependency.

**Status: software-tested with fixtures; not validated on a live design.** No live EasyEDA session, real placement,
routing or DRC run was used.

## What exists (implemented and unit-tested)

| Increment | Module / command | Store | Tests |
|---|---|---|---|
| B1 persisted recovery budget | `RecoveryPolicy.rebuild` / `adopt`, rebuilt in `Supervisor.__init__` | `state/reliability/recoveries.jsonl` (now also records `failure_signature` and `evidence_signature`) | `tests/test_recovery_budget.py` |
| B2 engineering task record | `desk/tasks.py`; `desk.py task show <P> <id>`, `desk.py task list <P>` | `state/tasks/<task_id>.jsonl` (event stream; the record is its fold) | `tests/test_task_record.py` |
| B3 decision graph | `ledger.py add decision --req-ids --alternatives --reasoning --supersedes`; `ledger.py <P> history <id>`; `desk/decision_graph.py` | `LEDGER.jsonl` (`supersedes`, `refs`, `req_ids`) | `tests/test_decision_history.py` |
| B4 ten-item recovery case | `desk/recovery_case.py`; `desk.py recover <P> --case <id\|list>` | `state/recovery/<case_id>.json` | `tests/test_recovery_case.py` |
| B5 seven-response selector | `desk/reliability/response_selector.py` (`select`, `select_for_task`) | `recovery` events on the task record | `tests/test_response_selector.py` |

### B1: the attempt bound holds across processes

Each executed recovery action is folded back into the budget. A failure observed again in a new process, under a new
failure id but with the same failure signature, inherits the attempts made since that signature's last verified
recovery. A verified recovery resets the signature's budget, so a healed failure that recurs gets a fresh budget.
Tried (action, evidence signature) pairs are rebuilt per failure id. Across failure ids, `RecoveryOutcomes` already
refuses a kind that failed before for the signature.

### B2: task record

The fold carries `inputs`, `expected_outputs`, `constraints`, `execution_status`
(PENDING/RUNNING/SUCCEEDED/FAILED/BLOCKED/SUPERSEDED), `verification_status` (NOT_RUN/PASS/FAIL/STALE), `failure`
(`FailureCategory` + OPERATIONAL/ENGINEERING layer), `evidence`, `provenance` (actor, desk commit, ts) and `attempts`
(count, max = 2, signatures).

- `validate()` is fail-closed, and `create()` validates before writing, so a malformed task never lands.
- A new execution after a verification turns it STALE. `freshness()` applies the ledger's `spec_hash` rule.
- `ops.write_op` mirrors begin/end/fail into the task of `(stage, target)`. This is an additive hook, and an error in the
  task record never fails the live operation.
- Measured: folding 1,000 events took 2.24 ms (best of 5, on the development laptop under load).

### B3: decision history

- `ledger.py add decision` writes `add_decision_record`.
- A `correction` without `--refs` is refused, and so are `refs`/`supersedes` that name unknown ids.
- `history` prints requirement -> decision -> correction -> new decision.
- All 222 existing ledger entries in `projects/*/LEDGER.jsonl` still load and walk (read-only check).
- `SpacingRequirement` gains optional `decision_ref` / `calc_ref`, omitted from `to_dict` when unset.

### B4: recovery case

The case holds the ten items:

1. requirements
2. assumptions
3. calculations
4. components
5. decision chain
6. failure
7. root cause
8. correction
9. verification
10. approval

Rules:

- A root-cause claim is kept only if every cited ref resolves (a ledger id, a reliability evidence id, or a file inside
  the project) and every excerpt is found in its artifact. Otherwise the claim is discarded with the reasons.
- `close()` refuses when:
  - an item is missing and not marked `not_applicable` with a reason;
  - the verification failed or came from the proposer or a `model:` source;
  - the approval id is not a recorded `ops` approval or a `RW-APR-` token;
  - `not_required` is given without the policy rule.
- On close it appends a ledger `correction` (refs -> the corrected decision) and the revised decision with
  `supersedes`.
- A closed case is never edited.

### B5: response selector

The seven responses are retry, change strategy, recalculate, alternative parts, return upstream, request
clarification and request approval.

- They come from a deterministic table over `FailureCategory` x `ExecutionState` x layer x established root-cause
  kind x approval class.
- A model ranking may only reorder the allowed candidates.
- The ladder is monotone. The same (response, signature) never runs twice, and the same signature twice escalates.
- There are at most 2 non-terminal responses per task and at most 2 back-edge hops. A property test over 9,000 random
  failure sequences shows termination at clarification or approval within max + 1 selections.
- REQUEST_CLARIFICATION blocks the task.

## Planned, not implemented

- `tools/verify.py` calling `desk.tasks.record_verify(...)`: this one-line wiring is a follow-up (the file is owned by
  parallel work). Until then a verify run does not update the task record; only `write_op` does.
- `decision_ref` / `calc_ref` on net-class profiles (`desk/profile.py` `NetClassProfile`). Adding fields there changes
  every `profile_hash`, so this needs its own migration.
- No production caller of `select_for_task` or of the recovery case yet. The first back-edge (routing -> placement /
  stackup from `desk/routing/pipeline.py`) is B6.
- B6-B10 from the study report: the routing, DRC and manufacturing back-edges, the structured agent failure return
  (`report_failure` in `desk.py agent`), and known-failure learning on case close.
- There is no CLI to fill or close a recovery case; that is done through the Python API.
