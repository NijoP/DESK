# DESK Product Charter, Product Manager Protocol and Team Charter

**Organisation:** Tusk Innovations Global Pvt Ltd. **Product:** DESK, The Electronics Design Engineering System, identity THE SENTINEL. **Primary ECAD:** EasyEDA Pro.
**Principle:** engineering intent in, verified engineering execution out. AI proposes; deterministic validation decides. Target product-quality score 9/10, evidence-based.

This single file replaces the proposed `PRODUCT_CHARTER.md`, `PRODUCT_MANAGER_PROTOCOL.md`, `TEAM_CHARTER.md` and `TEAM_RESPONSIBILITIES.md` to avoid file sprawl. The backlog lives in `docs/product_assessment/PRODUCT_ROADMAP.md`; the client register in `CLIENT_FEEDBACK_AND_GAP_ANALYSIS.md`; the status dashboard in `PRODUCT_MANAGER_REPORT.md`.

## 1. Reporting structure

```
Founder / Product Owner
    |
AI Product Manager (single source of truth for requirements, priorities, assignments,
                    dependencies, milestone acceptance, client feedback, reporting)
    |
    +-- Team A  Hardware Architecture        lead: Principal Hardware Architect
    +-- Team B  Software Engineering         lead: Principal Software Architect
    +-- Team C  AI Engineering               lead: Principal AI Systems Engineer
    +-- Team D  PCB Engineering              lead: Principal PCB Routing and Layout Engineer
    +-- Team E  Verification and QA          lead: Principal Verification Engineer (independent)
    +-- Team F  Product Experience           lead: Principal Product Experience Engineer
```

Team leads report to the Product Manager only. Team members report to their lead. No lead implements an architectural change that conflicts with another team's contract without the Product Manager's resolution. The Founder has one interaction point: the Product Manager.

## 2. Product Manager protocol

1. **Intake.** Every request (Founder, client, repository finding) becomes a backlog item with an ID, class (CONFIRMED / REPO-GAP / RECOMMENDATION / HYPOTHESIS), owner, acceptance criteria, dependencies, test strategy, complexity and priority.
2. **Decomposition.** SCOUT tasks (read-only investigation, may run in parallel) precede SHIP tasks (authorised changes, one writer per target, isolated when parallel).
3. **Review gates.** H-* and PCB-* items need Hardware Architect review before merge. Every item needs independent QA validation; no team approves its own claim.
4. **Evidence.** A capability is VERIFIED only by a reproducible test or a recorded live run. "Tests passed" is stated only when executed in the session. Benchmarks are recorded with command, dataset and machine.
5. **Safety.** Live EasyEDA mutation, destructive changes, clearance waivers and manufacturing release need explicit human authorisation. Customer projects (WATCH, BEEBOX) are never mutated; disposable projects are used for mutation tests. Credentials are never persisted in records or logs.
6. **Memory.** Decisions go to the project ledger with source, timestamp, evidence and status; superseded decisions are preserved and linked, never rewritten. Instruction changes to `AGENTS.md` go through the human-gated learning engine.
7. **Reporting.** After each milestone the Product Manager updates `PRODUCT_MANAGER_REPORT.md` with status, team reports, evidence, client alignment and the next five priorities.
8. **Honesty rule.** If a specialist role is performed by the Product Manager itself (no separate agent available), the report says so.

## 3. Team charters

### Team A — Hardware Architecture
Responsibilities: electrical models (ampacity, clearance/creepage, impedance, diff pairs, via current, thermal), component and pin-map provenance, compatibility matrix, review of every physics-touching change.
Deliverables: `HARDWARE_AND_PCB_ENGINEERING_ASSESSMENT.md`, `HARDWARE_COMPATIBILITY_MATRIX.md`, items H-*.
KPIs: number of hardware models with numeric reference tests; dangerous defaults remaining (baseline 11, see assessment §12); compatibility categories at PARTIALLY_IMPLEMENTED or better.
Interfaces: provides constraints to Team D; reviews Team C numeric outputs; supplies fixtures to Team E.

### Team B — Software Engineering
Responsibilities: runtime, concurrency, IPC, persistence, error model, maintainability, backward compatibility.
Deliverables: `SOFTWARE_ARCHITECTURE_ASSESSMENT.md`, items SW-*, PERF-*.
KPIs: non-atomic state writers remaining (baseline 31, now 28); `SystemExit` sites in library modules (baseline 19); duplicate implementations (baseline: 3 token estimators, 4 project loaders, 3 DRC parsers); bridge calls per tool run.
Interfaces: provides the durable task runtime to Team C and the event stream to Team F.

### Team C — AI Engineering
Responsibilities: router, adapters, capability registry, context efficiency, structured outputs, evidence and confidence tracking, preventing hallucinated engineering instructions.
Deliverables: `AI_ORCHESTRATION_ASSESSMENT.md`, items AI-*.
KPIs: tokens and seconds per L1 call (baseline 23,683 / 30.6 s via CLI; now ~150 / 1.1 s direct); router stages wired (baseline 0); model-produced numbers reaching the board (must be 0).
Interfaces: consumes validators from Teams A and D; never computes engineering numbers.

### Team D — PCB Engineering
Responsibilities: placement, escape, routing strategy, Freerouting supervision, copper, vias, outline, connectivity verification, recovery.
Deliverables: `HARDWARE_AND_PCB_ENGINEERING_ASSESSMENT.md` (shared), items PCB-*, H-03/H-07/H-08 (shared).
KPIs: routing completion on fixture boards; stalled-run detection time; connectivity verifier agreement with EasyEDA DRC.
Rule: routing success is claimed only from physical pad-to-pad connectivity, never from the presence of a track.

### Team E — Verification and QA (independent)
Responsibilities: unit, integration, system and live tests, fixtures, failure injection, benchmarks, CI, evidence standard.
Deliverables: `QUALITY_AND_VERIFICATION_ASSESSMENT.md`, items QA-*.
KPIs: tests (baseline 338, now 352); fixture boards (baseline 0); live checklist stages executed (baseline 0 of 9); numeric reference tests (baseline 0).

### Team F — Product Experience
Responsibilities: onboarding, workflow, CLI consistency, errors, Mission Control, reports, client interview.
Deliverables: `PRODUCT_WORKFLOW_ASSESSMENT.md`, client register, items PX-*.
KPIs: manual steps per board (baseline: 6 hand-edited JSON files, 4 EasyEDA dialogs); time to first verified block; doctor failures on a clean machine resolved by printed fixes.

## 4. Task classes and isolation

- **SCOUT:** read-only; may run concurrently; output is a report under `docs/product_assessment/` or a backlog item.
- **SHIP:** changes code, docs or a project; one writer per target; parallel SHIP tasks use separate git worktrees and branches; integration through review before `main`.
- Agent lifecycle states (adopted from the runtime assessment): CREATED, QUEUED, STARTING, WORKING, WAITING_FOR_TOOL, WAITING_FOR_REVIEW, BLOCKED, COMPLETED, FAILED, CANCELLED, RECOVERING, with UNKNOWN never promoted to idle or busy. Implementation tracked as SW-04.

## 5. Scorecard dimensions and weights

| Dimension | Weight | Owner of evidence |
|---|---:|---|
| Hardware engineering correctness | 25 % | Team A |
| PCB execution and routing quality | 20 % | Team D |
| Reliability and integration | 15 % | Team B + E |
| Performance and responsiveness | 15 % | Team B + C |
| AI orchestration quality | 10 % | Team C |
| Professional workflow and UX | 10 % | Team F |
| Documentation and maintainability | 5 % | Team F + B |

A score is awarded only on evidence; untested live integration and untested features do not earn production credit.
