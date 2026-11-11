# Performance Baseline and Optimisation Plan

All numbers measured 2026-11-11 on the development machine (Windows 11, Python 3.11.9, 2-core resource tier LOW as detected by DESK). Commands and datasets are named so results can be reproduced.

## 1. Task lifecycle, where the time goes

| Stage | Measured | Source | Verdict |
|---|---|---|---|
| Context retrieval (task pack) | sub-ms, hash-cached | `desk/context.py`, `test_context.py` | fine |
| Model inference, L1 via `agy` CLI | 30.6 s wall, 23,683 input tokens | live router dispatch | harness overhead, not model |
| Model inference, L1 via `pi -ne` | 4.2 s, 4,423 tokens | live | harness overhead |
| Model inference, L1 direct HTTP (Nemotron Lightning, thinking off) | 1.1 s, ~150 tokens | live | **adopted default** |
| Model inference, L1 Nemotron with thinking on | 40-50 s, empty answer | live probe | never use |
| Model inference, L2 direct HTTP (Super-VL) | 31.8 s | live | model-bound; needs fallback |
| Engineering calculation (full offline T01-T13) | 112.8 ms, of which T01 bridge discovery 99 ms | `tools/benchmarks.py` | discovery dominates |
| Board intelligence ingestion (89 parts, 349 pads) | 2.13 ms | `tools/routing_benchmarks.py` B1 | fine |
| Pad escape, priority scheduling | 11.75 ms, 13.71 ms | B2, B3 | fine |
| Connectivity verification | 8.14 ms | B5 | fine (result correctness open, QA-03) |
| ECAD communication, one bridge call | up to 280 s timeout, blocking; project.json parsed on every call | `desk/bridge.py` | overhead per call |
| Board mutation (route import) | deletes all tracks then imports SES; no measurement recorded | `tools/route.py` | needs timing + undo |
| External routing (Freerouting) | FAST 120 s, BALANCED 300 s, PRECISION 900 s (local edit) timeouts; up to 4-6 recovery attempts; WATCH rev B stall at 108/320 | `desk/routing/modes.py`, INC-007 | **dominant wall-clock cost** |
| Verification (DRC via EasyEDA) | 600 s timeout per pass, up to 3 converge passes | `tools/drc.py` | second largest |
| Mission Control status call | full `pcb_dump.json` + ledger parse + process scan + 10-port probe, every 1-2 s | `projection.py`, `server.py` | wasteful but off the critical path; 0.8 ms/op SSE overhead |

## 2. Findings

- **Unnecessary model invocations:** none in the pipeline today because the router is unused; the risk is the opposite (AI-01 must add calls only where validators exist).
- **Repeated context reads:** `project.json` is re-read on every bridge call (`bridge.py:235-242`); Mission Control re-parses the whole dump and ledger every 1-2 s.
- **Repeated calculations:** three trace-width implementations compute the same thing differently (H-10).
- **Excessive serial operations:** L3 was sequential (fixed M1); bridge calls are blocking by design (single writer, acceptable).
- **Inefficient parsers:** `ops.pending()` replays the entire `ops.jsonl` on every `write_op`; the ledger derives ids from a full line count.
- **Unbounded retries:** none found in the router (bounded by provider list); Freerouting recovery bounded by `recovery_max_attempts`.
- **Blocking subprocesses:** all adapters and Freerouting; acceptable for a single engineer, but each needs a cancel path (SW-05).
- **Excessive polling:** UI polls status/timeline/logs every 2-3 s while also holding an SSE stream.
- **Expensive spatial queries:** none measured above 14 ms.
- **Duplicate validation:** DRC parsed three ways (SW-07).

## 3. Optimisations adopted in M1 (correctness preserved)

1. Direct HTTP adapter for L1/L2 with thinking off: 30.6 s → 1.1 s and 23.7k → ~150 tokens per L1 call.
2. Per-tier timeouts so a slow tier cannot hold a fast one.
3. L3 providers in parallel.
4. Pre-flight pin-escape congestion veto before launching Java (fails in milliseconds instead of minutes).
5. BALANCED stagnation patience 6 → 4 passes (about 2 minutes saved per stalled run; no gate weakened: the run was already failing).

## 4. Plan (ordered by wall-clock impact per unit of risk)

| ID | Change | Expected effect | Risk | Owner |
|---|---|---|---|---|
| PERF-01 | Stream Freerouting per-pass unrouted counts to Mission Control and allow operator abort | engineer stops a stalled 5-minute run at pass 4 | low | PCB + Software |
| PERF-02 | Cache the bridge session's project identity; read `project.json` once per session, not per call | removes a file parse per bridge call | low | Software |
| PERF-03 | Mission Control: mtime-keyed cache for dump/ledger, 5 s port-probe cache, debounced persist thread | status call from tens of ms to sub-ms; no 1 s file churn | low | Software |
| PERF-04 | Compact `ops.jsonl` on clean exit; ledger ids from a counter file | constant-time `write_op` start | low | Software |
| PERF-05 | DRC converge: run DESK's offline connectivity and clearance pre-check before each EasyEDA DRC pass to skip passes that cannot pass | fewer 600 s DRC waits | medium (must not replace EasyEDA DRC) | PCB + QA |
| PERF-06 | Incremental snapshot updates already exist (`desk/snapshot.py`); wire them into rework readback instead of full dumps | faster readback on large boards | medium | Software |
| PERF-07 | Freerouting FAST mode as the default for the first attempt, escalate to BALANCED only on stall | first result in ≤ 2 min | low | PCB |

## 5. Rules that do not change

- No concurrent writers against a live EasyEDA document.
- Physical verification is never skipped to save time.
- Benchmarks are reported only when run; the commands above are the record.
