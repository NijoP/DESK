# Congestion Optimisation and Routing-Time Reduction

Evidence base: the recorded Freerouting 2.1.0 run on WATCH (`projects/WATCH/state/route/freerouting.log`, 2026-11-11 22:59-23:17), the routing pipeline audit, and the read-only live observation (`docs/product_assessment/LIVE_EASYEDA_OBSERVATION_01.md`).

## Why the original execution took so long

1. **Every run was a full-board reroute.** `tools/route.py` deleted all lines and vias before each SES import and never fed the previous SES back; the converge loop could launch three blind 5-minute runs.
2. **The engine never stopped on its own.** Freerouting 2.1.0 ignores `-mp` and the per-run `freerouting.json`; the global file had a 12-hour timeout. DESK's stagnation rule required N *identical* unrouted counts, which never happens on an oscillating run (64, 51, 51, 27, 18, 11, 12, 11, 27 …). The run ran to DESK's kill at timeout + 120 s and wrote no SES.
3. **The engine discarded its best boards.** v2.1.0 scores by trace length and via count; it restored a 51-unrouted board over an 8-unrouted one eleven times. v2.5.0 (completion-dominant score, best-board restore) sits in `library/tools` but needs Java 25; the machine has Java 23, and the discovery code preferred `freerouting.jar` (= 2.1.0) regardless.
4. **No intelligence reached the engine.** Priority, corridor, strategy and escape results were computed and dropped; all 60 net classes had identical clearance; planes were declared but inner layers stayed `signal`.
5. **Power trunks in signal corridors.** The density engine shows seven of the ten worst regions are VBUS / VBUS_BOOST / VSYS / VBAT trunks on a board with only two routable layers.

## What changed

| Change | Where | Effect |
|---|---|---|
| Improvement-based stagnation (`PassTracker`) with best-pass tracking | `desk/routing/orchestrator.py` | on the recorded log, patience 6 stops at pass 12 (28 % of the engine time) instead of running to the 17-minute kill; patience 14 reaches the true best (7 at pass 20) and stops at pass 35 |
| Highest compatible JAR selected by probing all candidates | orchestrator `discover_engine` | 2.5.0 is used automatically once Java 25 is installed; `desk doctor` reports the incompatibility |
| Engine config written where the engine reads it, restored after the run | `install_global_config` / `restore_global_config` | 2.1.0 now honours max passes, timeout, plane nets |
| `priority_net_classes`, `plane_nets`, `via_costs`, `stagnation_pass_limit` from DESK intelligence | `build_config`, `execute_routing(...)`, `tools/route.py` | the dense-board priority order drives the engine's order (v2.2+); planes handled as planes |
| Previous SES fed back (`-de dsn+ses`) with `--continue` | `execute_routing(input_ses=…)`, `tools/route.py` | a run continues a partial result instead of starting from zero |
| Per-net clearances from the routing plan reach the DSN | `tools/route.py` → `tune_dsn(net_clearances=…)` | voltage/RF/fine-pitch clearances no longer collapsed to 4.05 mil |
| Pre-flight congestion veto and dense-board report before Java starts | `tools/route.py` | impossible boards fail in milliseconds with a named cause |
| BALANCED stagnation patience 6 → 4 | `desk/routing/modes.py` | shorter stalls (the operator's PRECISION edit kept) |

## Bounded retries and recovery

- Retries are bounded by `recovery_max_attempts` per mode and by the tracker; no loop reruns on identical input.
- `IntelligentRecoveryEngine` still compares pad ids to net names (audit §3) and the converge loop still reroutes blindly; selective rip-up on real copper requires the pours-as-conductors verifier (QA-03 / SW-11). Status: OPEN.

## Runtime accounting (measured, this machine)

| Item | Time |
|---|---:|
| Dense-board analysis, WATCH | 43-83 ms |
| Placement refinement, WATCH, 3 moves | 12.6 s |
| Power distribution plan, 5 rails | 3 ms |
| Freerouting 2.1.0 per pass, WATCH | 6-42 s (median 17 s) |
| Recorded full run (49 passes) | 996 s, no SES |
| Tracker stop on the same log, patience 6 | pass 12, 279 s engine time (−72 %) |
| Tracker stop, patience 14 | pass 35, ~675 s (−32 %), best 7 |

A live A/B run through the new orchestrator on a scratch copy of the WATCH DSN is recorded in `DENSE_BOARD_BENCHMARK_REPORT.md` when available.

## Remaining limiting factors

- ~~Freerouting 2.1.0's score function; only an engine upgrade (Java 25) fixes best-board selection.~~ Resolved 2026-11-12: Temurin JDK 25 bundled in `library/tools/jdk25/`, Freerouting 2.5.0 selected automatically; a 6-pass run on the scratch WATCH DSN stopped itself and returned a SES (42 → 11 unrouted) that the verifier confirms at 51/60 nets.
- No fanout stub generation for RESTRICTED pads (78 on WATCH); the engine still does all escapes.
- ~~Pours ignored by the connectivity verifier.~~ Resolved: declared planes are conductors; pad sizes and board-frame pad offsets fixed (QA-03).
- Candidate evaluation in the refiner rebuilds the spatial index per candidate.
