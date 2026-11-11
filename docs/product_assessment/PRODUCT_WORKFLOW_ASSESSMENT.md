# Product Experience and Workflow Assessment (Team F)

**Scope:** how an experienced hardware engineer actually uses DESK end to end, and where friction, waiting, confusion or manual effort appears. Read-only; evidence cites files in this repository.
**Date:** 2026-11-11. **Owner:** Principal Product Experience Engineer.

## 1. End-to-end workflows as the user must perform them

### (a) New board (DESIGN_MODE)

Prerequisite setup every session: start the Node bridge (`node bridge-server.mjs`, not shipped; `docs/06_EASYEDA_API.md`), open EasyEDA Pro with the "Run API Gateway" extension, open the schematic page, run `python tools/ping.py`, hand-paste `sheet_uuid` / `pcb_uuid` / `window_id` into `projects/<P>/project.json` (`templates/project/project.json` literally says "PASTE_FROM tools/ping.py").

1. `python tools/new_project.py NAME`, then hand-write REQUIREMENTS.md (10 dimensions, 8 tables), BOM_SELECTION.md (F1–F7 matrix per IC), BLOCK_PLAN.md. No tool validates gate R or B; "gate passed" is a ledger line typed by hand (`projects/WATCH/LEDGER.jsonl` L-0003/L-0004).
2. Per block, one at a time (enforced by `desk/ops.py`): hand-write `blocks/NN_ID.json` (every pin number → net, `nc`, `qa` with formula and source) → `resolve.py` (wait on EasyEDA library search; ambiguous results need `--pick`) → `pins.py` (wait: places the part off-sheet and deletes it) → hand-edit pins from `library/pins/<MPN>.json` → `lint.py` → `build.py` (wait: chunked JS, bridge timeout 280 s) → `verify.py` (wait: full netlist read) → on failure `clear_block.py`, fix spec, rebuild (max 2 attempts) → hand-edit `RESULT.md`, `ledger.py add`, manual EasyEDA save and revision, `git commit`.
3. Sheet finish: `verify.py all`, `lint.py --final`, `erc.py` (wait), `bom.py` (csv only).
4. PCB: manual "Update PCB from schematic" in EasyEDA (`pcb_Document.importChanges()` only opens a dialog the human must click, `learning/incidents/INC-20261111-006.md`); manual board outline (must be a single closed polyline or the DSN export returns undefined, INC-008, EasyEDA froze twice); hand-write `placement.json` (every part needs x, y, rot, side and a reason string, or `pcb_place.py` exits); hand-write `pcb_rules.json`; `pcb_dump.py` (wait) → `pcb_place.py [--auto]` (wait) → `pcb_dump.py` again → `pcb_check.py --gate --freeze`. Net-class widths and clearances must be typed into EasyEDA's rule dialog by hand because the API cannot write rule tables (INC-006 §2).
5. Route: `route.py --mode BALANCED` → wait on the DSN export, wait on Java/Freerouting (300 s BALANCED timeout; WATCH rev B stalled at 108/320 unrouted, INC-007). SES import deletes all existing lines and vias first (`tools/route.py` import JS), then widening and repour (wait). `drc.py --converge` loops route + DRC up to 3× (wait on `pcb_Drc.check`, 600 s timeout). Planes must be hand-declared in `placement.json` `"planes"` or the router routes GND as traces (INC-007).
6. `release.py <REV> --layers 4`: offline gates, live ERC/DRC (wait), 6 exports (wait), cross-checks, MANIFEST.json. Any failure is a `SystemExit` with nothing written.

LLM waits: none inside the tools. The orchestrator is not invoked by any pipeline stage (`docs/09_STATUS.md` row 1d); the LLM is the agent driving the CLI.

### (b) Rework of an existing board

`desk.py rework start <P>` (tries live binding, falls back to "offline inspection mode") → requires `state/pcb_dump.json` already produced by `pcb_dump.py` (otherwise audits `{}`) → `rework audit` → `rework issues` → `rework plan` → `rework approve RP-XXXX` → `rework execute RP-XXXX` → `rework report`.
`execute` does not touch EasyEDA: `desk/rework/executor.py:118-127` mutates the in-memory `IndexedPCBSnapshot` and "reads back" from the same Python object; `ProjectBinding` is built with a synthetic uuid and `window_id="offline"` (`tools/desk.py:339-345`). README §12 admits "Live Bridge Mutation: IMPLEMENTED BUT NOT LIVE VERIFIED". README §11 demos rework on `projects/WATCH` while `desk/eda/easyeda_pro.py:165` lists WATCH as PROTECTED: contradictory guidance.

### (c) Audit only

No dedicated command. Options: `rework start --policy AUDIT_ONLY` + `rework audit` (board dims default to 50×50 mm in `audit.py:run_full_audit`, so edge-clearance findings are wrong for any other board); `pcb_check.py`; `drc.py` single pass (writes `state/recovery_plan.json` even in audit); `erc.py`. `AUDIT_MODE` exists only as regex intent in `desk/rework/mode.py`; nothing dispatches on it.

## 2. Tool catalogue (`tools/*.py`)

| Tool | Purpose | Overlap / notes |
|---|---|---|
| api_probe.py | dump live EasyEDA API map | pairs with `ctx.py api` |
| benchmarks.py | offline performance suite | overlaps routing_benchmarks.py and profile_perf.py |
| bom.py | BOM csv from block specs | release.py also exports an EasyEDA BOM |
| build.py | draw one block | |
| clear_block.py | remove one block | |
| ctx.py | context packs (brief/block/net/req/find/doc/delta/api) | agent-facing |
| desk.py | dispatcher: tools, dashboard, serve, status, rework, auth, settings, recover, doctor (M1) | |
| drc.py | live DRC, recovery plan, converge, readiness report | `rework report` makes a second readiness report with a different engine |
| erc.py | live ERC | release.py re-implements the call inline |
| learn.py | learning engine | dev-only |
| ledger.py | add/list decisions | |
| lint.py | offline block lint | |
| live_disposable_test.py | 9-stage live test, DISPOSABLE projects only | |
| new_project.py | scaffold project | |
| pcb_check.py | placement QA, routability gate, freeze | |
| pcb_dump.py | read PCB components → `state/pcb_dump.json` | must be re-run by hand before most PCB tools |
| pcb_place.py | apply or auto-generate placement | |
| pcb_rules.py | net classes, diff pairs | widths still manual in EasyEDA |
| ping.py | print project/document uuids | |
| pins.py | dump symbol pins | |
| profile_perf.py | 20-op profiling | benchmark overlap |
| release.py | gated manufacturing release | |
| resolve.py | MPN → library device | |
| route.py | DSN / Freerouting / SES pipeline | |
| routing_benchmarks.py | routing benchmark | benchmark overlap |
| verify.py | live netlist == spec | |

## 3. Friction points

- Hand-edited JSON: block.json (every pin), placement.json (reason string mandatory), pcb_rules.json, project.json uuids, design_profile.json (undocumented, no template), placement.json `"planes"` (documented only in INC-007).
- File naming: blocks must be `blocks/NN_ID.json`; anything in `blocks/` is loaded (`desk/spec.py:37`), so projects use `blocks_unused/` and `_removed_revB/` as ad-hoc exclusion folders.
- Undocumented flags: `route.py --adaptive`, `--reuse-dsn`; `desk.py dashboard --project/--no-open`; `desk.py rework --policy`; `clear_block.py --force-unlock`; env `DESK_PROJECT`, `EDA_WINDOW_ID`, `FREEROUTING_JAR/BIN`, `DESK_TELEMETRY`.
- CLI inconsistency: `desk.py` subcommands vs `tools/*.py` positionals; argv parsed by hand (`a.index("--port")+1` raises IndexError if the value is missing); `rework` detects the project by `startswith("projects/")`, so absolute paths silently fall to the default; `docs/getting-started.md` says open port 49620 (the bridge port) for the dashboard, which is wrong.
- Hard-coded defaults: `projects/WATCH` in `tools/desk.py:39,73,85,152`, `desk/runtime/server.py:293-465`, `projection.py:273/969`, `index.html:414`, `pins.py:20`, `profile_perf.py`, `benchmarks.py`. Board size 50×50 mm default in route.py, drc.py, audit.py, pcb_place.py. Power-net widths hard-coded for VBAT/VSYS/VBUS/3V3 (`route.py:134-141, 243-262`).
- Bare `SystemExit` strings at 40+ sites, e.g. `tools/desk.py:290 "No repair plan found."`, `release.py:41 "RELEASE BLOCKED"`, `bridge.py:354 "STOP: {res}"`.
- Silent fallbacks: `rework start` prints "[NOTE] Live ECAD connection offline" and continues; `rework audit` on a missing dump audits an empty dict and reports "Discovered N issues".
- Test-count claims disagree: README 332, AGENTS.md "195+", getting-started "195+"; the repo has 338 tests.

## 4. Professional expectations: present / partial / missing

- Schematic review or annotation export: PARTIAL (schematic PDF only inside `release.py`).
- Revision history / diff of board state: PARTIAL (fingerprints in `rework/baseline.py`, `ops.jsonl`, ledger; no diff view; `ctx.py delta` diffs docs, not the PCB).
- Design-review sign-off trail: PARTIAL (`RW-APR-` tokens with actor hard-coded "CAPTAIN", `planner.py:130`; `learn.py accept --reviewer`; `release/<REV>/MANIFEST.json`; no reviewer identity on releases).
- Engineering report: PARTIAL (`state/rework/<sid>/final_report.md`, `readiness_report.json`; no PDF, no aggregated design report).
- BOM export formats: PARTIAL (csv only; JLC PCBA BOM/CPL exist in `desk/component_intelligence` with no CLI).
- Gerber and assembly outputs: PRESENT via `release.py`, only after all gates pass; no "export now, warn" path.
- KiCad/Altium import: MISSING (`.agents/skills/kicad-integration/SKILL.md` references `desk/adapters/kicad_adapter.py`, which does not exist).
- Multi-board / panelisation: MISSING in code (no `desk/panelisation/`; panelisation is a human EasyEDA dialog, INC-005).
- Library management: PARTIAL (caches only; no versioning, no footprint review).
- Version control of the design: PARTIAL (git for JSON specs; EasyEDA revisions manual).
- Undo of a DESK mutation: MISSING (`checkpoints.py` has save/load only; `route.py` deletes all lines and vias before SES import with no rollback).

## 5. Mission Control

Shows: project badge (hard-coded "projects/WATCH"), execution status, SSE pill, 5 metric cards, 12-stage list, timeline, results table, log stream. Routes exist for `/api/rework/*` but no panel renders them.
Missing for an engineer: DRC violation list with locations; per-net routing completion (`route.py` writes `state/route/routing_attempt.json` but no tool emits events); pending-approval queue; "open in EasyEDA" link. `projects/WATCH/state/execution_state.json` shows stages COMPLETED with `start_time: null`, `duration 0.0` and activity "Testing SSE push": status is seeded, not derived from tool runs. `readiness_report.json` shows 363 DRC violations yet the summary counts clearance/shorts/unconnected as 0.

## 6. Onboarding

Must install or configure: Python 3.9+; Node.js 18+ and a third-party `bridge-server.mjs` (not in repo); the EasyEDA "Run API Gateway" extension; Java 17+ and Freerouting JARs in `library/tools/` (`.gitignore` excludes `*.jar`, so a fresh checkout has none, INC-007); optional `pi` / `agy` CLIs; env `EDA_PORT`, `EDA_WINDOW_ID`, `DESK_PROJECT`, `LCSC_CLIENT_ID/SECRET`, `FREEROUTING_JAR`.
Detection before M1: `desk.py settings` checked the bridge socket, kicad-cli and the vault only. Java missing surfaced as a RuntimeError only when `route.py` reached phase 10, after the DSN export. M1 adds `desk.py doctor`.

## 7. Learning and incident records

Useful: INC-20261111-006 (importChanges needs a saved schematic and a human Apply; rule tables not writable), INC-20261111-007 (planes must be declared to the router), `LES-20261111-mains-dropper-pcb.md` (DRC rule set that reached 0, pour polygon format). Noise: INC-20251111-001 / LSN-001 (bridge plumbing), `SESSION-20251111-1430` (agent operations log). Indexes are stale (INCIDENT_INDEX lacks 006–008; LESSON_INDEX lacks LES-20261111); ID formats drift. None of it is surfaced by any tool at the point of failure.

## 8. Top 10 workflow improvements (customer impact order)

1. `desk doctor`: check Python, Node bridge, extension, Java, Freerouting JAR, uuids in project.json; print a fix per item. Software. S. **Done M1.**
2. Replace hand-pasting of uuids: `ping --write projects/<P>`. Software. S.
3. Single `desk pcb` pipeline command (dump → place → check → rules → route → drc) with resume and explicit "manual step required" prompts that block until readback confirms. Product Experience + PCB. L.
4. Rollback for route import: snapshot lines/vias before delete, `desk undo route`. Software + PCB. M.
5. Make Mission Control data-driven: tools emit events; render `/api/rework/*`; remove the WATCH default. Software. M.
6. Project-agnostic routing: net widths, planes, board size from `design_profile.json` with a template and validator; drop VBAT/VSYS hard-coding. PCB + Software. M.
7. Rework executor against the live bridge, or label commands `--simulate`. Software + QA. L.
8. Unified error layer: code + cause + next command; consistent argparse across desk.py and tools. Software. M.
9. Engineering report generator (MD/PDF) from requirements, power tree, QA table, BOM cost, DRC/ERC evidence, release manifest. Product Experience + Hardware. M.
10. Surface lessons at failure time: map known failures to tool error messages; fix stale indexes. AI + QA. S.

## 9. Client interview questions

Hypothesis tested in brackets. No client statements are asserted here.

1. How long did your last session take from opening EasyEDA to a verified block? [H1: setup and uuid pasting dominate]
2. Did you write the block JSON pin maps yourself or did the agent? How many corrections? [H2: hand JSON is the main effort]
3. When routing stalled, what told you it was stalling? [H5: no live routing visibility]
4. Have you ever needed to revert a DESK change? What did you do? [H4: no undo]
5. Which EasyEDA dialogs do you still click by hand (Import Changes, rules, panelise, outline)? [H3: manual steps undocumented]
6. Do you open Mission Control? What do you look at? [H5]
7. Did `rework execute` ever change the live board? [H7: rework is offline]
8. On a new machine, what failed first? [H1: prerequisites]
9. What report do you send a client or reviewer today, and how do you produce it? [H9: no report generator]
10. Do you need KiCad or Altium import? [KiCad missing]
11. Which incident or lesson files have you read? Were they useful? [H10]
12. How many boards do you run through DESK concurrently? [hard-coded WATCH]
13. Do you trust the readiness report numbers (363 violations, 0 categorised)? [evidence quality]
14. Would a single pipeline command with pauses for manual steps fit how you work? [H3]
15. What does design sign-off look like in your process, and who signs? [sign-off trail]
16. Which circuit classes do you design most (buck/boost, isolated, motor, RF, USB, mains)? [compatibility matrix priority]
17. What clearance and creepage rules do you apply above 50 V, and would you trust a tool default? [H-clearance]
