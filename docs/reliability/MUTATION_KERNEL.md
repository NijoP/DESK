# Mutation kernel (roadmap I-1)

Status: software-tested with fixtures and a fake bridge; **not validated on a live design**.

## What a live PCB tool does now

`tools/copper_fill.py`, `tools/pcb_rules.py`, `tools/stitch_orphans.py` and `tools/pcb_place.py`:

1. `cli_approve()` (`desk/reliability/mutation.py`) records the hand-run invocation as the approval
   (`ops.cli_approval`) and checks `DESK_MUTATION_POLICY` **before any bridge call**. `--dry` runs record nothing.
2. `run_live()` runs the mutation through `MutationContract`: writer lock and journal (`ops.write_op`), an
   active-document identity check, the mutation, an independent readback, and a postcondition from
   `desk/reliability/api_registry.py`.
3. `report()` prints `MUTATION <op> <target>: <state>`. The tool exits 0 only when the readback proves the change.
   The journal's end record carries `execution_state` and `verified`.

| Tool | Readback | Verifier |
|---|---|---|
| pcb_place | `pcb_PrimitiveComponent.get(id)`: x, y, rotation, layer | `placements` |
| pcb_rules | names of net classes, differential pairs, equal-length groups | `names_present` (names only, not membership) |
| copper_fill | `pcb_PrimitiveFill.getAll()` primitive ids | `ids_replaced` (old ids gone, new ids present, count) / `ids_absent` for `--remove` |
| stitch_orphans | via and line primitive ids | `ids_present` with the planned count |

The four readback scripts are not in the API registry as VERIFIED (status UNKNOWN). If a getter behaves differently
on a live board, the tool fails closed (NOT VERIFIED) rather than reporting success.

`tools/live_disposable_test.py` now runs its live milestones under `write_op` with a CLI approval.
`tests/test_mutation_kernel.py` statically checks that every file with a literal EasyEDA mutator call is guarded.

## Rework executor

`desk/rework/executor.py` edits the in-memory snapshot only. Results are `SIMULATED` or `FAILED`, never `VERIFIED`, and
`verification_passed` is always False. Unknown action types and widening a track that does not exist fail. The run is
journalled as `rework_simulate` / `VALIDATION`.

## Not done yet

- `build`, `wire` and the SES import still use plain `write_op` without a readback contract.
- An unverified PARTIAL/UNKNOWN outcome is journalled as `end` with `verified: false`, not left pending for `recover`.
- `Supervisor` has no production caller. Rework still fabricates `project_uuid` and has no live execution path.
- stitch_orphans' readback test needs shapely and is skipped in CI (its policy refusal test runs everywhere).
