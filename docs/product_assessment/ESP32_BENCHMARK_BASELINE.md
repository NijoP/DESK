# ESP32 Benchmark Baseline (Phase 1)

**Date:** 2026-11-11/12. **Machine:** Windows 11, Python 3.11.9, OpenJDK 23, DESK resource tier LOW (2 cores detected). **Status:** no end-to-end timed C2/C3 run exists yet; this baseline records what has actually been measured and what is estimated, per stage.

Legend: **M** measured in this repository; **E** estimated from measured parts; **U** unmeasured.

## Stage 1 — Schematic and electrical validation (target 45 min)

| Item | Value | Basis |
|---|---|---|
| Block lint, spec compile, offline ERC | sub-second per block | M (`test_core.py`, benchmarks T04) |
| Component resolution (`resolve.py`) | one EasyEDA library search per MPN; ambiguous results need `--pick` | M workflow audit; latency per call U |
| Pin map retrieval (`pins.py`) | places and deletes a symbol per part | M workflow audit; latency U |
| Schematic build (`build.py`) per block | bridge call ≤ 280 s timeout; chunked JS | U (no recorded live transcript in repo) |
| Live ERC (`erc.py`) | one bridge call | U |
| Human steps | hand-written block JSON, pin edits, RESULT.md, EasyEDA save/revision | U |
| **Stage estimate for C2 (8-10 blocks)** | **90-180 min today** | E: the hand-written specs dominate (workflow audit §3) |

Bottleneck: human transcription of block specs and pin maps, not computation. Lever: generators from requirements + LCSC data (PX-02/PX-03, Continuation 03 work).

## Stage 2 — Placement (target 45 min)

| Item | Value | Basis |
|---|---|---|
| Placement rule check | 0.015 ms | M (T05) |
| Routability graph + MST + crossings | 1.2-3.9 ms | M |
| Dense-board analysis (WATCH, 87 parts) | 43-83 ms | M |
| Placement refinement (WATCH, 3 moves) | 12.6 s | M |
| `pcb_place.py` live apply | one bridge call per chunk | U |
| Human steps | hand-written `placement.json` with reasons; manual outline in EasyEDA | U |
| **Stage estimate for C2** | **30-60 min today**, 10-20 min once refinement proposes positions | E |

## Stage 3 — Routing (target 90 min)

| Item | Value | Basis |
|---|---|---|
| DSN export + tuning | export U; tuning 0.1 ms | M/U |
| Freerouting 2.1.0 pass on WATCH | 6-42 s, median 17 s | M (log, 49 passes) |
| Recorded full run | 996 s, no SES (killed at timeout) | M |
| Scratch A/B run through the new orchestrator (240 s budget) | engine ignored the merged config, ran to DESK's 360 s kill, best 8 unrouted at pass 16, no SES | M (2026-11-12; config writer corrected to legacy keys afterwards; re-verification pending) |
| Tracker stop on the recorded log (patience 6 / 14) | pass 12 (279 s) / pass 35 (~675 s) | M (simulation on real log) |
| SES import + widening + repour + readback | 4 bridge calls + 6.5 s fixed sleeps | M (audit) |
| DRC pass (EasyEDA) | ≤ 600 s each, up to 3 converge passes | M (timeouts); actual U |
| **Stage estimate for C3-like WATCH** | **> 90 min today** (two 15-minute engine runs that produced nothing, plus DRC) | E |

Bottleneck ranking (evidence in `docs/engineering/CONGESTION_OPTIMISATION.md`): repeated full-board reroutes; engine never stopping; score-based best-board loss in v2.1.0; no intelligence reaching the engine; power trunks in signal corridors.

## Stage 4 — Copper (target 30 min)

| Item | Value | Basis |
|---|---|---|
| Power distribution plan | 3 ms | M |
| Zone geometry checks | < 10 ms | M |
| Pour create / rebuild / readback | live, never executed | U |
| **Stage estimate** | **unknown**; planning is negligible, the budget is EasyEDA time | U |

## Stage 5 — Manufacturing preflight (target 15 min)

| Item | Value | Basis |
|---|---|---|
| Offline gates (8 quality gates, readiness report) | < 1 ms | M |
| Live ERC/DRC + 6 exports (`release.py`) | U |
| BOM/CPL generation | offline tested; live U |
| **Stage estimate** | **10-20 min** once live calls are timed | E |

## Totals

| Profile | Today (estimate) | Measured end-to-end | Target |
|---|---|---|---|
| C2 | 3.5-6 h | none | 225 min |
| C3 | > 6 h (routing alone exceeded 90 min on WATCH without a result) | none | 225 min |

## Next measurements (Phase 2/5)

1. Create disposable `BENCH_C2` and `BENCH_C3` projects in EasyEDA from the frozen specification (human step).
2. Run each stage with the stage timer and `runs.jsonl` accounting; repeat 3 ×; report P50/P90 in `ESP32_ENGINEERING_TIME_REPORT.md`.
3. Re-run the scratch Freerouting A/B after the legacy config fix and after a Java 25 install to compare 2.1.0 vs 2.5.0.
