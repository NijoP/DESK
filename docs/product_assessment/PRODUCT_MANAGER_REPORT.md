# Product Manager Report — Milestone 1

**To:** Founder. **From:** AI Product Manager, DESK. **Date:** 2026-11-11. **Commit:** `f6d6e79` on `main` (plus this document set).
**Honesty note:** all six team roles were performed by the Product Manager using read-only scout agents for the audits; no separate specialist agents were available. Every number below was measured in this repository today.

## PRODUCT STATUS

**Current evidence-based score: 4.1 / 10.** Potential after the roadmap: about 8.5 / 10; a 9 requires live-verified results on the ten-board portfolio, which does not exist yet.

| Dimension | Weight | Score | Basis |
|---|---:|---:|---|
| Hardware engineering correctness | 25 % | 4 | formulas correct for IPC-2221 but mislabelled; unknown current defaults to 1 A; clearance unsafe above 50 V; no diff-pair, impedance or via-current models; production router ignores the profile |
| PCB execution and routing quality | 20 % | 4 | supervised Freerouting pipeline, escape analysis and connectivity verifier exist offline; rectangle-only outline; no undo; verifier result on the only dataset is 1/59 nets |
| Reliability and integration | 15 % | 4 | 352 offline tests green; lock race and dirty-timeout fixed; 28 non-atomic writers remain; rework executor is offline; nothing live-verified |
| Performance and responsiveness | 15 % | 5 | engine sub-ms; wall clock dominated by Freerouting and EasyEDA waits; L1 model call cut from 30.6 s to 1.1 s |
| AI orchestration quality | 10 % | 4 | router now correct and verified with three NVIDIA models; not wired into any stage |
| Professional workflow and UX | 10 % | 3 | six hand-edited JSON files and four manual EasyEDA dialogs per board; doctor added |
| Documentation and maintainability | 5 % | 5 | extensive and honest status docs; counts disagree; skills cite non-existent code; duplicated logic |

**Completed this milestone:** six team audits, reference assessment, capability and compatibility matrices, gap register with interview script, performance baseline, roadmap, organisation charter, agent-system architecture; router hardening; direct NVIDIA adapter; capability registry; lock race fix; atomic writes for identity files; dirty-on-timeout; fail-closed readiness report; congestion veto; doctor.
**Blocked:** live EasyEDA verification (QA-05) needs a Founder-scheduled session with a disposable project open in EasyEDA Pro. Client confirmation of hypotheses needs the interview.
**Critical risks:** (1) a board routed with DESK defaults above 50 V or with an undeclared high-current rail is unsafe (H-01, H-02); (2) the production router ignores the design profile (H-03); (3) SES import deletes all tracks with no undo (PX-04); (4) the only routing dataset shows 1.7 % connectivity, so routing claims are unsupported (QA-03).

## WHAT WE DISCOVERED

- DESK's deterministic core is fast and well tested offline; its value proposition, safe mutation of real boards, has never been exercised live.
- The AI layer had no product effect: the router was dead code with a broken fallback, a hard-coded unservable frontier model and a shell-injection path. It now works and is verified, but still needs wiring into stages.
- Calling a cheap model through a coding-agent CLI costs 4k-24k tokens and 4-30 s for a one-line task; a direct HTTP call costs ~150 tokens and 1 s. Thinking must be off for L1/L2 Nemotron models or they return nothing.
- Four models gave four different trace widths (10.4 to 110 mil) for the same 1 A question; DESK's engine gives 11.9 mil. Models must never compute.

## WHAT THE CLIENT IS LIKELY MISSING (hypotheses, see the register)

Safe clearance above 50 V; verified widths from declared currents; differential-pair and impedance verification; undo; a single pipeline command without hand-written JSON; live routing visibility; a report they can sign; rework that touches the real board.

## WHAT THE REPOSITORY ALREADY DOES WELL

Fail-closed quality gates and approval tokens; single-writer lock with journal; incremental spatial snapshot with proven invariant; pad-escape analysis at 12 ms per board; credential vault with redaction; honest capability status document; zero dependencies.

## WHAT IS ACTUALLY BROKEN OR INCOMPLETE

Unknown-current fail-closed path dead; clearance model above 50 V; `rework.audit_power_thermal` AttributeError; `DiffPairVerification` unused; three inconsistent ampacity rules; readiness flags fabricated (fixed); rework executor offline; task inbox unused and in-memory; B5 connectivity 1.7 %; skills referencing missing code.

## TEAM REPORTS

Each in `docs/product_assessment/`: `HARDWARE_AND_PCB_ENGINEERING_ASSESSMENT.md` (A, D), `SOFTWARE_ARCHITECTURE_ASSESSMENT.md` (B), `AI_ORCHESTRATION_ASSESSMENT.md` (C), `QUALITY_AND_VERIFICATION_ASSESSMENT.md` (E), `PRODUCT_WORKFLOW_ASSESSMENT.md` (F); `docs/agent_system/REFERENCE_ARCHITECTURE_ASSESSMENT.md`.

## ENGINEERING EVIDENCE

| Item | Result |
|---|---|
| Full test suite before changes | 338 passed, 3 skipped |
| Full test suite after M1 | 352 passed, 3 skipped (`python -m unittest discover -s tests -p "test_*.py"`) |
| Offline pipeline benchmark | 112.8 ms (T01 discovery 99 ms) |
| Routing benchmark | ingestion 2.13 ms; escape 11.75 ms; priority 13.71 ms; connectivity 8.14 ms (1/59 nets, under investigation) |
| Mission Control overhead | 0.80 ms per op, 50 MB |
| NVIDIA models | all three intended ids reachable; thinking off: 1.1 s / 51.6 s / 0.7 s; Super-VL intermittently 503 |
| Router live dispatch | L1 1.1 s valid JSON; L2 31.8 s valid JSON |
| `desk doctor` on this machine | 0 failed, 2 warnings |
| Live EasyEDA integration | not run |

## CLIENT ALIGNMENT

Confirmed requirements: none recorded. Implemented requests: none attributable. Pending validation: 17 interview questions. Newly discovered: G-01 to G-20 in the gap register.

## NEXT PRIORITIES (top five)

| # | Item | Team | Lead | Depends on |
|---|---|---|---|---|
| 1 | H-01 clearance and creepage model above 50 V | Hardware | Principal Hardware Architect | — |
| 2 | H-02 unknown-current fail-closed, H-03 router reads the profile, H-10 single ampacity module | Hardware + PCB | Hardware Architect, PCB Lead | H-02 before H-03 |
| 3 | PX-04 undo for route import, PERF-01 live routing progress with abort | Software + PCB | Software Architect | — |
| 4 | QA-01 disposable fixture boards, QA-03 connectivity investigation, QA-05 live checklist | QA | Verification Engineer | Founder session for QA-05 |
| 5 | AI-01 wire the router into intake and DRC-diagnosis behind validators, AI-06 numeric override | AI | AI Systems Engineer | — |

## REMAINING RISKS AND DEPENDENCIES

- The free NVIDIA tier rate-limits at about 40 requests per minute and showed a content-safety outage; L2 needs the `pi`/`agy` fallback configured.
- Local Pi extension configuration on the development machine is broken (duplicate subagent candidate); DESK bypasses it with `-ne`, but interactive Pi use will fail until it is fixed.
- The Freerouting JAR is git-ignored; a fresh clone cannot route until the JAR is placed; doctor now reports this.
- `tools/desk.py` and `desk/routing/modes.py` carried uncommitted Founder edits that were included in the M1 commit (rework window binding; PRECISION timeout 900 s, recovery attempts 6).


---

# Product Manager Report — Milestone 2 (2026-11-12)

**Commits:** `56792e7` (hardware P0), `863aea9` (rework terminal: post-mortem + orchestrator/route changes), this commit (dense-board programme, rework items A-G, ecosystem architecture, 225-minute programme baseline).
**Suite:** 427 passed, 3 skipped (was 359 at M1 close).

## What was discovered (measured)

- The WATCH rev B routing failure is fully explained: no planes in the DSN, placement keep-outs exported as router keep-outs, an engine (Freerouting 2.1.0 on Java 23) that ignores every stop setting and writes a SES only at 100 %, and an outline drawn as 36 segments (`learning/lessons/LSN-20261111-004.md`, `INC-20261112-009`).
- Read-only live observation of the WATCH board (13 getter calls, 484 ms, no mutation): 87 parts, 313 pads, 60 nets, 233 crossings; seven of the ten worst congestion regions are power trunks (VBUS/VBUS_BOOST/VSYS/VBAT) competing with signals on the two routable layers; 12 pour outlines, none poured; no signal copper at that moment.
- Smoke proof on this host: the engine writes a SES in 3.2 s when it completes; the missing SES on WATCH was never an I/O problem.

## What was implemented and verified offline

Dense PCB intelligence (congestion map with measured causes, corridors, priority order, incremental update), placement-routing co-optimisation (authorised minimal moves), power distribution planner (IPC sizing, drop, via arrays, zone checks), pours-as-conductors connectivity with physical layer order, improvement-based engine supervision with per-pass progress.json and problem nets by name, highest-compatible-JAR and bundled-JDK discovery, fail-closed routing pre-flight (planes / one closed outline / no pad in a router keep-out), engine smoke run before long jobs, plain-R outline helpers, plan-vs-board sync in the placement gate, hardware P0 (standards-table clearance/creepage, fail-closed unknown currents, profile-driven widths), ecosystem inventory and architecture (LCSC, JLCPCB, EasyEDA), the 225-minute programme specification, baseline, acceptance criteria, live-test status and cross-platform notes.

## Rework terminal items A-G

| Item | Status |
|---|---|
| A pre-flight gate + tests/test_route_preflight.py | DONE (fixture passes; a pad inside a keep-out is refused) |
| B smoke run, plateau stop, graceful stop | DONE; graceful stop is SIGINT on POSIX, terminate on Windows (no JVM hook) |
| C Java 25 + Freerouting >= 2.4 | discovery, startup check and doctor guidance DONE; the JDK download was blocked by the sandbox: HUMAN STEP (unzip Temurin 25 into library/tools/jdk25/ or set DESK_JAVA), then re-run the scratch A/B and record in INC-20261112-009 |
| D per-pass telemetry with net names | DONE (state/route/progress.json) |
| E outline helpers and skill text | DONE |
| F deterministic placer / plan-vs-board sync | sync check DONE in pcb_check --gate; placer determinism not changed (needs the owner's generator run to reproduce) |
| G skill failure guidance | DONE |

## Evidence-based score

Unchanged at **4.1 / 10** for production readiness: nothing is live-verified beyond read-only observation, and the routing stage still cannot return a partial board on this host until Java 25 is installed. Offline engineering depth moved materially (hardware models, dense-board intelligence, connectivity truthfulness, engine supervision).

## Next five

1. Install Java 25 (human), prove a stopped job returns a SES on the scratch WATCH DSN, then route the disposable copy with --continue (ENG-01).
2. QA-05 live checklist on a disposable project: pours, repour, poured-copper readback getter (EE-03).
3. Declare rail currents for WATCH in a design_profile.json and run the power planner; move VBUS/VSYS/VBAT to polygons or plane taps.
4. Freeze the C2/C3 benchmark designs (ESP-01) and start stage timing (ESP-02).
5. LC-01/JL-01: live-verify the LCSC client and versioned JLCPCB profiles with credentials.
