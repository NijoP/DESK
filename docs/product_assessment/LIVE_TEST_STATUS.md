# Live Test Status

Updated 2026-11-12. Categories are kept separate so that passing offline tests are never mistaken for live compatibility.

| Category | Count / state | Evidence |
|---|---|---|
| Offline unit tests | 433 passed, 3 skipped across 75 files (2026-11-12 01:55 local) | `python -m unittest discover -s tests` |
| Integration tests (offline, multi-module) | routing e2e on Project One SES, rework e2e, orchestrator with mock adapters, dense-board fixtures | `tests/test_routing_e2e_project_one.py`, `test_rework_e2e.py`, `test_orchestrator.py`, `test_dense_intelligence.py` |
| EasyEDA API tests (read-only, live) | **1 pass executed** on the WATCH project through the gateway: 13 getter calls, 484 ms, no mutation | `docs/product_assessment/LIVE_EASYEDA_OBSERVATION_01.md` |
| Live EasyEDA mutation tests | **0 executed**; nine-stage checklist defined, never run | `docs/LIVE_INTEGRATION_CHECKLIST.md`, `tools/live_disposable_test.py` |
| Complete PCB workflow tests | 0 timed runs; one real routing attempt observed (WATCH, 2026-11-11: 49 passes, no SES) | `projects/WATCH/state/route/freerouting.log` |
| Freerouting engine tests (offline, scratch copy) | 5 runs: two 2.1.0 WATCH-DSN runs (no SES, engine ignores stop settings), 2.1.0 smoke (SES 3.2 s), **2.5.0 smoke (SES 4.4 s) and 2.5.0 WATCH-DSN run stopped at 6 passes with a 100 KB SES, 11 unrouted** | `docs/engineering/DENSE_BOARD_BENCHMARK_REPORT.md`, `learning/incidents/INC-20261112-009.md` |
| Senior engineer acceptance | none | `ESP32_HARDWARE_ACCEPTANCE_CRITERIA.md` |
| Manufacturing verification (fabricator DFM) | none | — |

## Rules in force

- Live mutation only on disposable projects (`DISPOSABLE` / `TEST` in the path); customer projects WATCH and BEEBOX are mutation-protected in code.
- While another terminal routes a project, DESK observation is read-only getters with explicit window id, no retries, no locks.
- No live compatibility claim is made on the strength of offline tests.

## Next live steps (need a human at the EasyEDA window)

1. Create `projects/DISPOSABLE_TEST` from a copy and run `tools/live_disposable_test.py --execute-live` stages 1-3 (read, placement verify).
2. Stage 4-7: pour create / rebuild / poured readback; capture the polygon getter that works (unknown today).
3. One `tools/route.py` run on the disposable board through the new orchestrator with `--continue`, timed with the stage timer.
4. Install Java 25 and repeat the routing run with Freerouting 2.5.0.
