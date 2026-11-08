# 09 — Capability status (evidence-based)

**GREEN** = acceptance criteria met **and** test evidence exists. **AMBER** = implemented, offline-tested, live path not
yet exercised. **RED** = not implemented. Live = against EasyEDA Pro 3.2.149 on this machine.

| # | Capability | Status | Acceptance criteria | Evidence |
|---|---|---|---|---|
| 1 | Knowledge + ledger | GREEN | source-required decisions, append-only, corrections supersede, verification STALE on spec **or library device** change, incremental index, in-memory cache | tests/test_context.py (16), tests/test_perf_engineering.py, tests/test_decision_memory.py |
| 1b | Context engine & policy retrieval | GREEN | packs within budget, live lint, next gate from real state; compiled policy retrieval (`ctx.py policy`) < 300 tokens | tests/test_context.py; tests/test_mental_compiler.py (5); bench −69 % on real sessions |
| 1c | Engineering design profile | GREEN | versioned contract for physical stackup, per-net currents, voltage tree, RF lines, diff pairs, thermal rise | desk/profile.py + tests/test_profile_and_mental_models.py (5) |
| 1d | Multi-model orchestration | GREEN | unified task/result protocol, AGY adapter (agy.exe), Pi adapter (pi.cmd), L0–L4 capability router | desk/orchestrator/ + tests/test_orchestrator.py (6) |
| 2 | Schematic generation | **AMBER** | build→verify VERIFIED on a live sheet; clear→rebuild identical | drawing routine identical to the one that produced proven sheets; **DESK build/verify/clear never run live** (see blocker) |
| 3a | Offline electrical checks | GREEN | computed QA (expr/min/max, safe eval), ground/supply pin rules, cap ratings, numeric values | tests/test_core.py |
| 3b | Netlist validation | GREEN (logic) / AMBER (live) | pin-by-pin compare, collisions, stray parts | tests/test_core.py; live read path untested in DESK |
| 3c | EasyEDA ERC | AMBER | `sch_Drc.check(...,true)` parsed, 0 errors gate | method exists live (api_map); not executed |
| 4 | PCB placement & intelligence | GREEN (offline) / AMBER (live) | rules of docs/04 enforced: edge, pad-to-pad/body by package class, connector edge + mating keep-out + ESD distance, sensor vs heat, heat spreading, RF at edge, keep-outs, height zones, decap distance/side, rotation, utilisation/hotspots/free space, mechanical access | desk/placement.py + desk/placement_intel.py + tests/test_placement.py (12) + tests/test_evolution.py (12) + tests/test_phase6_placement_policy.py (2); live pcb_dump readback not yet exercised |
| 4b | Routability & placement freeze | GREEN | fast O(V²) Prim MST, sweep-line ratsnest crossing filter, escape congestion score, placement freeze SHA-1 snapshot and ledger entry | desk/routability.py + tests/test_perf_engineering.py + tests/test_placement.py |
| 5a | Net classes / diff pairs | AMBER | create + read back | methods exist live; not executed |
| 5b | Autorouting & DSN tuning | GREEN (offline) / AMBER (live) | 6-stage priority scheduling, profile-driven widths, DSN tuning, duplicate pad coordinate deduplication, Freerouting execution, SES import | desk/router.py + tools/route.py + tests/test_evolution.py + tests/test_perf_engineering.py + tests/test_copper_and_routing_intelligence.py (5) |
| 5c | DRC convergence & recovery | GREEN (offline) / AMBER (live) | `pcb_Drc.check` parser, failure diagnoser, recovery planner with selective rip-up, progress-aware convergence loop | desk/drc_engine.py + tools/drc.py + tests/test_evolution.py + tests/test_perf_engineering.py |
| 5d | Copper & ground intelligence | GREEN (offline) / AMBER (live) | plane layer allocation from actual stackup, stitching via array synthesis, return-path continuity evaluation, slot crossing detection | desk/copper.py + tests/test_copper_and_routing_intelligence.py |
| 6 | API coverage | GREEN (discovery) | live probe of all modules/methods; per-call verified/failed register | library/api_map.json: 93 modules, 702 methods; api_verified.json: 7 calls observed (incl. `openProject` → false) |
| 7 | Agent execution & safety | GREEN (offline) | single-writer lock, op journal, dirty-failure recovery, tool catalog, deterministic L0 bypass | desk/ops.py, desk/orchestrator/router.py, tests/test_core.py, tests/test_orchestrator.py |
| 8 | Test suite & benchmarks | GREEN | 102 automated unit & integration tests passing in < 5.5s; 10-scenario benchmark suite executing in < 8.5ms | tests/ (102 tests passing across 10 test modules); tools/benchmarks.py; tools/profile_perf.py |
| 9 | Manufacturing release & quality gates | GREEN (offline) / AMBER (live) | 8 hard acceptance gates separated from 6-component weighted quality score; BOM/PnP/Gerber cross-checks, sha256 manifest | desk/quality.py + desk/release.py + tests/test_quality_and_mfg_verification.py (4) + tests/test_core.py |
| 10 | Learning engine | GREEN | real corpus, ≥2-session corroboration, human gate, protected surfaces, regression revert, benchmark | tests/test_learn.py (16); real run: 33 sessions, 36 proposals, 1.9 s |
| 11 | Performance engineering | GREEN | sub-millisecond socket discovery, indexed PCB snapshot cache, sweep-line geometric pre-filters, telemetry collector | desk/snapshot.py + desk/profiler.py + desk/telemetry.py + tests/test_perf_engineering.py (9 tests) |

## Blocker for every AMBER live item
`dmt_Project.createProject` works live (disposable project **DESK_LIVETEST_11031644**, uuid
`fc66155d5a2f4d2d9b1dd3bcd8093391`, was created), but `dmt_Project.openProject` returned **false** while your project
was open, so DESK could not switch to it without risking your unsaved work. To unblock: open that project in EasyEDA
yourself (or tell DESK it may switch), then run the live sequence: resolve → pins → lint → build → verify → clear → build
→ verify → erc → (PCB) importChanges → pcb_dump → pcb_rules → drc → release. Delete the project afterwards.
