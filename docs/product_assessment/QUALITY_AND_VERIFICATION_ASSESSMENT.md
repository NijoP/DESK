# Quality and Verification Assessment (Team E)

**Scope:** what DESK's tests and benchmarks actually prove, executed in this repository on 2026-11-11 on Windows 11, Python 3.11.9. The QA team is independent of the implementation teams; nothing here is taken from README claims.
**Owner:** Principal Verification Engineer.

## 1. Executed results

| Run | Result |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` (before M1 changes) | 338 tests, OK, 3 skipped, ~14 s |
| Same, after M1 changes plus `tests/test_m1_reliability.py` | 352 tests, OK, 3 skipped |
| `tools/benchmarks.py` (offline T01-T13 pipeline) | 112.8 ms telemetry total; 206.2 ms combined; T01 discovery 99 ms is 88 % of it |
| `tools/routing_benchmarks.py` (Project One dataset, 89 parts, 349 pads) | B1 ingestion 2.13 ms; B2 pad escape 11.75 ms (86 constrained pads); B3 priority 13.71 ms; B5 connectivity 8.14 ms; B6 widening 0.10 ms |
| `tests/bench_server_overhead.py` | 0.40 ms/op baseline, 1.20 ms/op with Mission Control + SSE, 50 MB RSS |
| `python desk.py doctor --project projects/WATCH` | 0 failed, 2 warnings, 12 ok |
| Live L1 router dispatch, direct NVIDIA adapter | 1.1 s, valid JSON |
| Live L2 router dispatch, direct NVIDIA adapter | 31.8 s, valid JSON |

Discrepancy: README says 332 tests, AGENTS.md says "195+", the tree had 338 before M1.

## 2. What the suite does and does not prove

- **Proves:** deterministic geometry, parsing, profile compilation, lock semantics in-process, SSE plumbing, rework session state machine, orchestrator routing with mock adapters, the M1 fixes.
- **Does not prove:** anything against a live EasyEDA Pro document. Every capability in `docs/09_STATUS.md` is "tested offline" or "not live verified". The nine-stage live checklist (`docs/LIVE_INTEGRATION_CHECKLIST.md`) has never been executed.
- **No numeric reference tests.** No test asserts an IPC-2221 width, an impedance, a diff-pair skew or a clearance against a published value (hardware assessment §1).
- **Benchmark B5 result is suspicious.** The connectivity verifier reports 1 of 59 nets fully connected (1.7 %) on the Project One SES. Either the dataset's SES does not match its PCB dump or the verifier is wrong. Status: NEEDS_INVESTIGATION (roadmap QA-03).
- **Readiness report had fabricated evidence.** `evaluate_readiness` returned `footprint/mechanical/thermal verified=True` without performing those checks. Fixed in M1: now False with a `checks_not_performed` list, covered by `test_m1_reliability.TestReadinessFailClosed`.
- **No cross-process lock contention test** existed; M1 adds thread contention and the write-window race test. A true two-process test is still open (QA-02).
- **No failure-injection tests** for bridge timeouts mid-mutation beyond the new dirty-journal test.
- **No CI.** There is no workflow directory; tests run only when someone runs them.

## 3. Evidence standard adopted

- A capability is VERIFIED only with a reproducible test or a recorded live run.
- Passing unit tests with mocks do not count as production readiness.
- A readiness or quality report may never assert a check it did not perform.
- Benchmarks are recorded with the command, dataset and machine; estimates are labelled as estimates.

## 4. Test portfolio required for a 9/10 (Phase 7)

Ten representative boards: 2-layer MCU; 4-layer ESP32; high-current motor controller; buck/boost converter; RF transmitter; differential-pair board; mixed-signal; dense fine-pitch; multi-terminal routing; defective PCB for rework. For each: design correctness, connectivity, DRC, ERC, clearance, track width, layer usage, ground-plane continuity, routing completion, thermal constraints, manufacturing readiness, runtime, recovery. Today only one dataset (Project One / WATCH) exists and it is a customer project under mutation protection; a disposable fixture set must be created (QA-01).

## 5. Top QA tasks

1. QA-01 Disposable fixture boards (at least the 2-layer MCU and the diff-pair board) checked into `tests/fixtures/`, with PCB dump, DSN, SES and expected metrics. L.
2. QA-02 Two-process `write.lock` contention test using `subprocess`. S.
3. QA-03 Investigate B5 1.7 % connectivity: regenerate the Project One SES from its dump or fix the verifier. M.
4. QA-04 Numeric reference tests: IPC-2221 widths, clearance tiers, stackup dielectric totals. S.
5. QA-05 Execute the nine-stage live checklist on a disposable project and record the transcript. L (needs human at the EasyEDA window).
6. QA-06 CI workflow running the suite on Windows and Linux. S.
7. QA-07 Golden snapshot tests for ERC/DRC/audit text output with a bless-and-review step. M.
