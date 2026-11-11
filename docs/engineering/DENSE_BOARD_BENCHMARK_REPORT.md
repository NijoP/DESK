# Dense Board Benchmark Report

Date 2026-11-12. Machine: Windows 11, Python 3.11.9, OpenJDK 23, 2-core tier. Every number here was measured by the commands named; nothing is extrapolated without saying so. Synthetic results are labelled SYNTHETIC and demonstrate algorithm behaviour only; REAL-BOARD rows use the WATCH project's geometry and do not constitute live validation.

## 1. Baseline (before this programme)

| Measure | Value | Source |
|---|---|---|
| Intelligence modules influencing the engine | none (escape, congestion, priority, strategy computed and discarded) | routing pipeline audit |
| Recorded Freerouting 2.1.0 run on WATCH | 49 passes, 996 s, unrouted 64 → best 7 (pass 20) → 25, 11 best-board restores to a 51-unrouted board, killed at timeout, **no SES** | `projects/WATCH/state/route/freerouting.log` |
| Stagnation rule | identical counts for N passes: never fired on the oscillating run | `orchestrator.py` (old) |
| Engine selection | `freerouting.jar` (2.1.0) chosen first regardless of version | `orchestrator.py` (old) |
| Connectivity verifier | pours ignored; plane-net pads reported partially connected | `connectivity.py` (old) |
| Placement feedback | none; gate accepted 355 crossings | `routability.py` |

## 2. Offline intelligence (`tools/dense_benchmarks.py --runs 3`)

| Board | Kind | Parts | Pads | Nets | Crossings | Congestion | Overloaded cells | Hotspot regions | Analysis ms P50 | Refinement | Top cause |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| mcu_2layer_compact | SYNTHETIC | 18 | 83 | 28 | 69 | 0.76 | 24 | 11 | 12.2 | 3 moves / 0.4 s | fine-pitch escape |
| esp32_4layer | SYNTHETIC | 44 | 187 | 57 | 352 | 2.53 | 86 | 10 | 24.9 | 3 moves / 4.5 s | keep-out crossing |
| qfn_fine_pitch | SYNTHETIC | 14 | 105 | 47 | 157 | 1.27 | 48 | 4 | 32.3 | 3 moves / 0.5 s | fine-pitch escape |
| motor_high_current | SYNTHETIC | 21 | 80 | 15 | 116 | 0.55 | 17 | 2 | 24.2 | 2 moves / 0.8 s | fine-pitch escape |
| buck_boost | SYNTHETIC | 12 | 39 | 12 | 15 | 0.47 | 13 | 9 | 17.7 | 1 move / 0.1 s | fine-pitch escape |
| mixed_signal | SYNTHETIC | 20 | 98 | 30 | 107 | 0.70 | 24 | 7 | 29.8 | 3 moves / 3.7 s | fine-pitch escape |
| rf_board | SYNTHETIC | 15 | 60 | 12 | 59 | 1.04 | 31 | 2 | 24.6 | 3 moves / 0.5 s | fine-pitch escape |
| dense_sensor | SYNTHETIC | 28 | 135 | 12 | 172 | 1.47 | 64 | 15 | 41.6 | 3 moves / 4.7 s | fine-pitch escape |
| multi_terminal | SYNTHETIC | 17 | 149 | 14 | 502 | 1.21 | 47 | 14 | 46.8 | 2 moves / 0.4 s | fine-pitch escape |
| multi_rail_limited_layers | SYNTHETIC | 30 | 167 | 44 | 62 | 0.82 | 28 | 9 | 44.3 | 2 moves / 0.8 s | fine-pitch escape |
| WATCH (repo dump) | REAL-BOARD | 87 | 313 | 60 | 212 | 0.62 | 11 | 16 | 83.1 | 3 moves / 12.6 s | power trunk through signal corridor |
| WATCH (live read 18:05Z) | REAL-BOARD | 87 | 313 | 60 | 233 | 0.69 | 11 | 18 | 42.9 | — | power trunk through signal corridor |

Power distribution plan (synthetic multi-rail, declared currents): 3 ms; 3V3 → PLANE, 5V / VIN_12V → WIDE_TRACE, 1V8 / 1V2 → POLYGON (drop > 2 % of a low rail).

## 3. Engine supervision

### 3a. Tracker replay on the recorded WATCH log (`tests/test_routing_pass_tracker.py`)

| Rule | Stop | Engine time | Best known at stop |
|---|---|---:|---|
| Old identical-count rule (patience 6) | never | 996 s (killed) | — |
| Improvement rule, patience 6 | pass 12 | 279 s (−72 %) | 11 (pass 6); the later 7 at pass 20 is forfeited |
| Improvement rule, patience 14 | pass 35 | ~675 s (−32 %) | 7 (pass 20) |

Trade-off: with Freerouting 2.1.0 the SES written at the stop is the engine's *score*-best board, not the connectivity-best one, so a shorter patience saves time but does not by itself deliver the best board. Only the engine upgrade (v2.5.0, needs Java 25) fixes that; the tracker's value today is bounded time and a recorded best pass.

### 3b. Scratch A/B run through the new orchestrator (scratch copy of the WATCH DSN, 2026-11-12 00:49 local)

Command: `-de watch.dsn -do watch_new.ses -mp 30 -mt 1`, 240 s budget, priority classes and plane nets in the config.

| Result | Value |
|---|---|
| Engine | v2.1.0 (2.2.4 / 2.4.1 / 2.5.0 present but `UnsupportedClassVersionError` on Java 23) |
| Passes in 360 s | 21; unrouted 68 → best **8 at pass 16** → 20; 4 best-board restores |
| Stop | DESK kill at budget + 120 s (`TIMEOUT`), no SES |
| Finding | the engine did not honour the 4-minute job timeout: the global config merge included nested keys 2.1.0 does not know (`autorouter.*`, `plane_nets`), and the engine fell back to its defaults. The writer now merges only `job_timeout`, `max_passes`, `optimizer.max_passes`, `scoring.via_costs` for engines < 2.2 (`legacy_router_keys`). |
| Re-verification | short run (6 passes, 2-minute timeout) launched after the fix; result recorded in §3c when complete |

### 3c. Short re-verification run and smoke proof (2026-11-12)

| Run | Result |
|---|---|
| Legacy-keys global config, `max_passes 6`, `job_timeout 00:02:00`, scratch WATCH DSN | 12 passes in 240 s, best 12 unrouted; engine ignored both limits; killed; no SES |
| Smoke fixture (`desk/routing/dsn_fixture.py`, 4 nets, `-mp 2`) | 12/12 connections in 3.2 s, SES written (2,232 bytes) |

Conclusion: on this host Freerouting 2.1.0 honours no stop setting at all (CLI, per-run file, global file); the SES write path itself works. A partial board can only be obtained from Freerouting ≥ 2.2 on Java 25 (human install step, `INC-20261112-009`). `tools/route.py` now runs the smoke fixture before any long job and refuses to start when the engine cannot write a SES.

## 4. What is routed more efficiently now

- Boards whose bottleneck is a power trunk in a signal corridor (WATCH's dominant cause): the density engine names the nets and regions, the power planner proposes polygon/plane strategies, and the engine receives `plane_nets` so plane nets are not routed as traces.
- Fine-pitch boards (synthetic QFN/sensor fixtures): the priority order puts escape-constrained nets first (`priority_net_classes`, honoured by Freerouting ≥ 2.2).
- Any board: the run stops on a plateau instead of running to the kill, and `--continue` resumes from the previous SES instead of rerouting from zero.

## 5. Runtime change (measured where possible)

| Item | Before | After |
|---|---|---|
| Pre-route analysis | none | 43-83 ms (WATCH) |
| Engine time on the recorded run | 996 s, no result | 279-675 s by tracker replay (same engine); live re-run pending |
| Verification of plane nets | always "partial" | correct with declared pours (`tests/test_connectivity_zones.py`) |
| Placement refinement | not available | 12.6 s for 3 authorised proposals (WATCH) |

The 30 % reduction target is met on the replayed log (−32 % at patience 14, −72 % at patience 6) but has **not** been demonstrated on a live run with an SES result; that requires either the engine upgrade or a verified legacy-config run (§3c).

## 6. Remaining limitations and unverified live capabilities

- Freerouting 2.1.0 best-board selection (engine-internal); Java 25 needed for 2.5.0.
- No fanout stub generation for the 78 RESTRICTED pads on WATCH.
- Placement refiner rebuilds the spatial index per candidate (PERF-08).
- Pour creation, repour and poured-copper readback never executed live; declared polygons are used for verification until then.
- Priority classes are only known to be honoured by Freerouting ≥ 2.2; on 2.1.0 their effect is UNKNOWN.
- Copper-zone connectivity on real poured geometry, DRC convergence time and SES import time are unmeasured.
