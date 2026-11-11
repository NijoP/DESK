# Product Roadmap and Backlog

Single backlog for the DESK programme. Priorities: **P0** critical correctness or data-loss, **P1** essential professional workflow, **P2** important engineering capability, **P3** performance and usability, **P4** future. Every item has an owner team and lead, acceptance criteria, dependencies, a test strategy, complexity (S/M/L), status and evidence. Items marked DONE were implemented and verified in milestone 1 (commit `f6d6e79`).

Team leads: HW = Principal Hardware Architect; SW = Principal Software Architect; AI = Principal AI Systems Engineer; PCB = Principal PCB Routing and Layout Engineer; QA = Principal Verification Engineer; PX = Principal Product Experience Engineer. QA validates every item independently; HW reviews every H-* and PCB-* item before merge.

## P0 — critical correctness and data loss

| ID | Item | Owner | Spec | Acceptance | Deps | Test | Cx | Status |
|---|---|---|---|---|---|---|---|---|
| SW-01 | write.lock reclaim race | SW | treat unreadable lock younger than 2 s as held | two contenders, exactly one holder | — | `test_m1_reliability.TestLockReclaimRace` | S | DONE |
| SW-03 | Mutation timeout journaled dirty | SW | `BridgeMutationTimeout` recognised by `write_op` | journal shows dirty, `recover` lists it | — | `TestMutationTimeoutIsDirty` | S | DONE |
| SW-02 | Atomic writes for all state files | SW | migrate 28 remaining `json.dump` sites to `desk.fsutil` | kill-mid-write leaves original intact | — | patch `json.dumps` to raise | M | OPEN (3 of 31 sites done) |
| H-09 | Readiness report never fabricates evidence | QA | defaults False + `checks_not_performed` | report lists unperformed checks | — | `TestReadinessFailClosed` | S | DONE |
| H-01 | Clearance and creepage model above 50 V | HW | IPC-2221B Table 6-1 B1-B4 by coating/altitude; IEC 60664-1 creepage by pollution degree; explicit net-pair voltages; refuse to route HV nets without them | table values reproduced; LIGHT project nets get ≥ 3 mm | — | unit tests vs table; LIGHT fixture | M | OPEN |
| H-02 | Unknown-current rails fail closed | HW | `allow_unknown_default=False` by default in `RoutingPlanGenerator` and `tools/route.py`; ERROR gate lists undeclared power nets | undeclared VBAT blocks routing with a named fix | — | unit + route dry-run | S | OPEN |
| H-03 | route.py uses the DesignProfile | PCB | net widths, clearances and widening targets from `derive_trace_width_mil`; remove VBAT/VSYS literals | DSN class widths equal profile output | H-02 | e2e DSN assertion | M | OPEN |

## P1 — essential professional workflow

| ID | Item | Owner | Spec | Acceptance | Deps | Test | Cx | Status |
|---|---|---|---|---|---|---|---|---|
| PX-01 | `desk doctor` | SW | prerequisite checks with fixes | 0 failed on a configured machine; FAIL with fix on a clean one | — | `TestDoctor` | S | DONE |
| PX-02 | Bind project without hand-pasting uuids | SW | `ping --write projects/<P>`; gate R/B validators | project.json populated; gate status computed | — | unit on sample project | S | OPEN |
| PX-03 | Single `desk pcb` pipeline with resume and manual-step prompts | PX + PCB | dump → place → check → rules → route → drc, resumable, blocks until readback confirms manual steps | WATCH-like board end to end with one command | PX-04, PERF-01 | live disposable run | L | OPEN |
| PX-04 | Undo for route import | SW + PCB | snapshot lines/vias before delete; `desk undo route` | readback equals pre-state fingerprint | — | live disposable run | M | OPEN |
| PX-07 | Rework executor against the live bridge | SW + QA | execute through `ops.write_op` + bridge; or label `--simulate` | pad-net update read back from EasyEDA | QA-05 | live disposable stage | L | OPEN |
| SW-04 | Durable task inbox and unified lifecycle | SW | persist `tasks.jsonl`; states CREATED…RECOVERING; restart reconciler via `is_process_alive` | RUNNING tasks load as RECOVERING after restart | — | kill-and-reload test | L | OPEN |
| QA-01 | Disposable fixture boards | QA | 2-layer MCU and diff-pair fixtures with dump, DSN, SES, expected metrics | tests run without customer projects | — | — | L | OPEN |
| QA-05 | Execute the nine-stage live checklist | QA | on `projects/DISPOSABLE_TEST` with a human at the window | transcript committed | QA-01 | — | L | OPEN (needs Founder-scheduled session) |
| QA-03 | Investigate B5 1.7 % connectivity | QA + PCB | regenerate Project One SES or fix verifier | B5 ≥ 95 % on a known-routed board or defect documented | — | benchmark | M | DONE 2026-11-12: verifier defects fixed (pad size, double rotation); 2.5.0 SES verifies at 51/60 nets consistent with the engine; Project One dataset itself is stale (6.8 %) |
| PERF-01 | Stream Freerouting passes to Mission Control with abort | PCB + SW | per-pass unrouted count events; operator stop | stalled run stopped at pass 4 | — | event test | M | OPEN |

## P2 — important engineering capability

| ID | Item | Owner | Spec | Acceptance | Deps | Test | Cx | Status |
|---|---|---|---|---|---|---|---|---|
| H-04 | Differential-pair verification | HW | post-route length/skew from SES or readback, gap sampling, uncoupled %; W/S solver | synthetic fixture skew detected ±5 % | H-05 | fixtures | M | OPEN |
| H-05 | Impedance calculator | HW | Hammerstad-Jensen microstrip, stripline, CPWG; consume stackup fields; fix 2-layer dielectric double count | ±5 % vs published points | — | unit | M | OPEN |
| H-06 | Via ampacity and thermal via farms | HW | IPC-2221 via cross-section, parallel count, θ budget | tests vs published data | — | unit | M | OPEN |
| H-07 | Return path on real copper | HW + PCB | plane geometry from poured-region readback minus antipads/other zones; ≤ 0.5 mm sampling; emit `plane_split` | split-plane fixture flagged | QA-01 | fixture | L | OPEN |
| H-08 | Real outline and slots to the router | PCB | pass outline polygon/arcs and keep-out polygons into DSN | L-shaped board round-trips | — | DSN test | M | OPEN |
| H-10 | Single ampacity module | HW | `desk/ipc.py` used by width.py, router.py, audit.py; fix `profile.power_nets`; relabel 2221 | parity across call sites | — | parity tests | S | OPEN |
| H-11 | ERC breadth | HW | driver conflicts, floating inputs, pull-ups, polarity, I/O voltage | fixtures per rule | — | unit | M | OPEN |
| PCB-01 | Planes from PCB dump instead of hand-declared JSON | PCB | read poured regions and zones from readback | GND routed via plane on WATCH without `"planes"` | — | fixture | M | OPEN |
| AI-01 | Wire the router into real stages | AI | scout/ship intake classification, DRC-diagnosis explanation, rework-plan narration, all behind validators | three stages dispatch with validation; failures fall back deterministically | — | live dispatch tests | M | OPEN |
| AI-06 | Numeric override guard | AI | any model-produced number DESK can compute is overwritten by the engine | helper + validator test | — | unit | S | OPEN |
| PX-09 | Engineering report generator | PX + HW | MD/PDF from requirements, power tree, QA table, BOM cost, DRC/ERC evidence, manifest; reviewer identity | WATCH report matches ledger | — | golden test | M | OPEN |
| SW-07 | Structured verdicts instead of booleans | SW | `PASS/CONDITIONAL/FAIL/NOT_RUN/STALE/UNKNOWN` across routing, quality, rework, orchestrator | NOT_RUN gate yields NOT_RUN, not FAIL | — | unit | M | OPEN |
| QA-04 | Numeric reference tests | QA | IPC-2221 widths, clearance tiers, stackup totals | values asserted | — | unit | S | OPEN |

## P3 — performance and usability

| ID | Item | Owner | Cx | Status |
|---|---|---|---|---|
| PX-05 | Data-driven Mission Control; remove WATCH default; render rework routes | SW | M | PARTIAL 2026-11-12: routing-stage panel and `/api/v1/route/progress` added (file-backed); WATCH default and rework panels still open |
| PX-06 | Project-agnostic defaults (board size, net names) in `design_profile.json` with template and validator | PCB + SW | M | OPEN |
| PX-08 | Unified error layer and argparse across tools | SW | M | OPEN |
| PX-11 | Surface lessons at failure time; fix stale learning indexes | AI + QA | S | OPEN |
| SW-05 | Scheduler cancel-on-timeout stops mutations | SW | M | OPEN |
| SW-06 | Typed exceptions in library modules | SW | M | OPEN |
| SW-08 | Mission Control reconciliation cache and debounced persist | SW | M | OPEN |
| SW-09 | Unify project loaders and bridge clients | SW | M | OPEN |
| SW-10 | Index `learning/` in the context engine; add author/status/confidence to the ledger | SW | S | OPEN |
| AI-03 | Per-call trace ids and token accounting | AI | S | OPEN |
| AI-05 | Applicability levels on model suggestions | AI | M | OPEN |
| PERF-02..07 | see performance plan | SW/PCB | S-M | OPEN |
| QA-02 | Two-process lock contention test | QA | S | OPEN |
| QA-06 | CI on Windows and Linux | QA | S | OPEN |
| QA-07 | Golden snapshot tests with bless-and-review | QA | M | OPEN |
| DOC-01 | Reconcile test counts and skill references to real code | PX | S | OPEN |

## P4 — future

| ID | Item | Owner |
|---|---|---|
| PX-10 | KiCad import adapter | SW |
| PCB-02 | Panelisation | PCB |
| HW-12 | Thermal model (θJA, copper area per watt) | HW |
| HW-13 | PDN and decoupling impedance | HW |
| AI-07 | Worktree-isolated ship tasks and liaison supervision (firstmate-style) | AI + SW |

## Milestone plan

- **M1 (done, 2026-11-11):** audits, router hardening, P0 reliability fixes, doctor, direct NVIDIA adapter, capability registry.
- **M2:** H-01, H-02, H-03, H-10, QA-04, SW-02, PX-02, PERF-01. Target: hardware defaults are safe and the router honours the profile.
- **M3:** QA-01, QA-03, PX-04, PX-03, SW-04, AI-01, AI-06. Target: one disposable board through the full pipeline with undo and live events.
- **M4:** QA-05 live checklist, PX-07, H-04, H-05, H-06, H-08, PX-09. Target: first live-verified release on a representative board.
- **M5:** H-07, H-11, PCB-01, SW-07, Mission Control, CI, snapshot tests. Target: 9/10 scorecard with evidence.

## Milestone 2 additions (2026-11-12)

| ID | Item | Owner | Cx | Status |
|---|---|---|---|---|
| PCB-03 | Dense PCB Intelligence engine wired into `tools/route.py` (priority classes, plane nets, via costs, clearances to DSN) | PCB + SW | M | DONE |
| PCB-04 | Placement refiner (proposals; authorised apply to placement.json) | PCB | M | DONE |
| H-13 | Power distribution planner with IPC sizing, drop budget, via arrays, zone checks | HW | M | DONE |
| SW-13 | PassTracker improvement-based stagnation; highest-compatible JAR; legacy global config merge/restore; `--continue` | SW | M | DONE (engine honouring of the legacy config under verification) |
| H-10 | Single ampacity module, IPC-2221 relabel | HW | S | DONE |
| H-01 | Clearance/creepage tables | HW | M | DONE (table values await Hardware Architect confirmation) |
| H-02 | Unknown current fail-closed | HW | S | DONE |
| H-03 | route.py widths from profile | PCB | M | DONE |
| QA-04 | Numeric reference tests | QA | S | DONE |
| SW-10 | learning/ indexed by context engine | SW | S | DONE |
| SW-11 | Pours as conductors in `PhysicalConnectivityVerifier`; poured-region readback | SW + PCB | M | OPEN, P1 (blocks 100 % connectivity claims for plane nets) |
| PERF-08 | Reuse spatial index across refiner candidates (12 s → target < 2 s on WATCH) | SW | S | OPEN |
| H-12 | Switching-loop area check for buck/boost | HW | M | OPEN |
| ENG-01 | Install Java 25 and validate Freerouting 2.5.0 (completion-dominant score, best-board restore) | Founder + PCB | S | DONE 2026-11-12: bundled JDK in library/tools/jdk25, stopped job returned a SES (INC-20261112-009) |
| ESP-01 | Freeze C2/C3 benchmark designs (`ESP32_C2_C3_PERFORMANCE_SPECIFICATION.md`) as disposable projects | HW | M | OPEN, human step |
| ESP-02 | Stage timers and accounting report (`ESP32_ENGINEERING_TIME_REPORT.md`) | SW + QA | M | OPEN |
| ESP-03 | Block-spec and placement generators from requirements + LCSC data (Stage 1/2 time) | PX + AI | L | OPEN |
| CP-01..04 | Cross-platform CI, POSIX config path, entry-laptop measurement, explicit `-Xmx` | QA + SW | S-M | OPEN |
| ECO-01 | LCSC/JLCPCB/EasyEDA ecosystem architecture set (Continuation 03) | LCSC/JLCPCB + PM | L | OPEN (inventory in progress) |
