# ESP32 Engineering Time Report

**Status: no benchmark run has been executed yet.** This file holds the reporting format and the measured component times; it is filled in Phase 5 after the C2/C3 projects are frozen and run three times each.

## Format (per profile, per run)

| Stage | Target | Wall clock | DESK active | Model inference | External API | Engineering calc | Human | External wait | Rework/recovery | Gate passed | Measured/Estimated |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 Schematic | 45 min | | | | | | | | | | |
| 2 Placement | 45 min | | | | | | | | | | |
| 3 Routing | 90 min | | | | | | | | | | |
| 4 Copper | 30 min | | | | | | | | | | |
| 5 Preflight | 15 min | | | | | | | | | | |
| Total | 225 min | | | | | | | | | | |

P50 and P90 are computed across runs per stage. Timers run from stage start to gate pass, including retries.

## Component times measured so far (feed into the estimates in `ESP32_BENCHMARK_BASELINE.md`)

| Component | Measured | Date |
|---|---:|---|
| Dense-board analysis (WATCH) | 43-83 ms | 2026-11-11/12 |
| Placement refinement (WATCH, 3 moves) | 12.6 s | 2026-11-12 |
| Power distribution plan (5 rails) | 3 ms | 2026-11-12 |
| Freerouting 2.1.0 pass (WATCH) | 6-42 s, median 17 s | 2026-11-11 |
| Recorded Freerouting run (49 passes, no SES) | 996 s | 2026-11-11 |
| L1 model call, direct HTTP | 1.1 s | 2026-11-11 |
| L2 model call, direct HTTP | 31.8 s | 2026-11-11 |
| Read-only live board readback (87 parts) | 0.48 s | 2026-11-11 |
| Offline pipeline T01-T13 | 113 ms | 2026-11-11 |

## Not yet measured

Schematic build per block, live ERC/DRC, DSN export, SES import, pour rebuild, release exports, LCSC lookups, any human step.
