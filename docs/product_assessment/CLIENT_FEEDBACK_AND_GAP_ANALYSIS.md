# Client Feedback Register and Gap Analysis

**Client:** a hardware engineer with about 20 years of experience who evaluated DESK at the institution, used it and reported that features and limitations prevent it from covering their full professional workflow. **No structured list of their feedback exists yet.** Nothing in this document is attributed to the client as a statement; every item is classified as one of:

- **CONFIRMED** — direct client feedback (none recorded yet).
- **REPO-GAP** — discovered by inspecting the repository and running it.
- **RECOMMENDATION** — engineering judgement from the team audits.
- **HYPOTHESIS** — likely client pain, requires confirmation in the interview.

The interview questions are in `PRODUCT_WORKFLOW_ASSESSMENT.md` §9 and summarised at the end.

## Gap register

| ID | Class | Existing capability | Expected professional workflow | Observed behaviour | Why it matters | Proposed solution | Team | Depends on | Verification | Priority |
|---|---|---|---|---|---|---|---|---|---|---|
| G-01 | REPO-GAP | Clearance derived from net voltage, two tiers | IPC-2221B/IEC 60664 clearance and creepage by voltage, coating, pollution degree | 300 V nets get 24 mil (`profile.py:279-282`) | A mains or isolated design routed with DESK defaults is unsafe | H-01 clearance/creepage model with explicit net-pair voltages; refuse to route HV nets without it | Hardware | — | table-value tests; LIGHT project | P0 |
| G-02 | REPO-GAP | Power-net current from profile | Unknown current must block, not guess | Unknown rails sized at 1 A silently | Under-sized traces on a fabricated board | H-02 fail-closed default | Hardware | — | undeclared VBAT blocks routing | P0 |
| G-03 | REPO-GAP | Profile computes widths | Router uses computed widths | `tools/route.py` hard-codes VBAT/VSYS 10 mil | Profile work has no effect on the board | H-03 route.py reads DesignProfile | PCB | G-02 | DSN class widths == profile | P0 |
| G-04 | REPO-GAP | Readiness report | Report states only what was checked | Was fabricating verified=True | Engineer trusts a fake pass | Fixed M1 | QA | — | `test_m1_reliability` | done |
| G-05 | HYPOTHESIS | Manual uuid paste, Node bridge, Java, JARs | One command tells me what is missing and how to fix it | Java missing surfaced only in route phase 10 | First-day failure on a new machine | `desk doctor` (done M1); `ping --write` (PX-02) | Software | — | clean VM run | P1 |
| G-06 | HYPOTHESIS | Per-block JSON specs with every pin | Engineer edits a schematic, not JSON | Hand-written `blocks/NN_ID.json`, `placement.json` with mandatory reason strings | Hours of transcription per board | PX-03 single `desk pcb` pipeline with resume; PX-02 generators from EasyEDA readback | Product Experience | — | WATCH-like board end to end | P1 |
| G-07 | REPO-GAP | Route import | Revert a bad route | SES import deletes all lines and vias; no rollback | One stalled route destroys hand work | PX-04 snapshot + `desk undo route` | Software + PCB | — | readback equals pre-state fingerprint | P1 |
| G-08 | HYPOTHESIS | Freerouting with 300 s timeout | See routing progress and stop early | WATCH rev B stalled at 108/320 unrouted (INC-007); no live view | Engineer waits blind | M1 congestion veto and patience 4; PX-05 events to Mission Control | PCB + Software | — | dashboard shows per-pass unrouted | P1 |
| G-09 | REPO-GAP | Rework executor | Repairs applied to the live board | Executes against an in-memory snapshot | Rework mode cannot repair anything real | PX-07 live executor or `--simulate` label | Software + QA | QA-05 | live disposable test | P1 |
| G-10 | REPO-GAP | Diff-pair profile | USB/LVDS pairs verified for skew and impedance | Verification class never used; no impedance | USB boards shipped unverified | H-04, H-05 | Hardware | — | synthetic SES fixtures | P2 |
| G-11 | REPO-GAP | Fixed 24/12 mil vias | Via count and size from current and thermal budget | No via ampacity | Power stages under-vialed | H-06 | Hardware | — | tests vs published data | P2 |
| G-12 | REPO-GAP | Return-path sampling | Plane-split detection on real copper | Ignores poured copper | EMI failures slip through | H-07 | Hardware + PCB | live readback | split-plane fixture | P2 |
| G-13 | REPO-GAP | Rectangular outline | Real outline with slots to the router | DSN boundary overwritten | Odd-shaped boards unroutable | H-08 | PCB | — | L-shaped DSN round trip | P2 |
| G-14 | HYPOTHESIS | csv BOM, rework final_report.md | Design report for review/sign-off | No aggregated report, no reviewer identity | Cannot hand off to a client or reviewer | PX-09 report generator; sign-off identity | Product Experience | — | report for WATCH matches ledger | P2 |
| G-15 | REPO-GAP | Mission Control | Real DRC list, routing completion, approvals | Stage status from file heuristics; WATCH hard-coded | Dashboard misleads | PX-05 | Software | — | runs without seeded state | P3 |
| G-16 | REPO-GAP | 66 `SystemExit` sites | Errors with code, cause, next command | Bare strings | Engineer cannot self-recover | SW-06 | Software | — | every tool `--help`; fuzz | P3 |
| G-17 | HYPOTHESIS | — | KiCad/Altium import | Skill references missing adapter | Cannot bring existing boards | PX-10 | Software | — | import fixture | P4 |
| G-18 | REPO-GAP | — | Panelisation | Human dialog only | Production prep manual | P4 | PCB | — | — | P4 |
| G-19 | RECOMMENDATION | L0-L4 router (unused) | AI explains DRC failures and plans rework narratively, never computes numbers | Router not wired | AI value unrealised; risk of LLM arithmetic | AI-01 wiring behind validators; AI-06 numeric override | AI | — | live dispatch tests | P2 |
| G-20 | REPO-GAP | 338 offline tests | Representative boards verified live | Live checklist never run; B5 shows 1/59 connectivity on the only dataset | Production claims unsupported | QA-01, QA-03, QA-05 | QA | — | recorded transcripts | P1 |

## Interview and validation document (for the next client interaction)

Goal: convert HYPOTHESIS rows to CONFIRMED or dropped, and rank the P1/P2 engineering gaps by the client's actual circuit classes. Record answers verbatim in this register with date and interviewer; never paraphrase into stronger claims.

1. Which circuit classes do you design most: buck/boost, isolated or mains, motor, RF, USB/high-speed, precision analog? (ranks H-01..H-07)
2. On a new machine, what failed first when you set DESK up? (G-05)
3. How long from opening EasyEDA to the first verified block, and where did the time go? (G-06)
4. Did you write the block JSON pin maps yourself? How many corrections? (G-06)
5. Which EasyEDA dialogs do you still click by hand? (G-06, PX-03)
6. When routing stalled, what told you? Did you want to stop it earlier? (G-08)
7. Have you needed to revert a DESK change? What did you do? (G-07)
8. Did `rework execute` ever change your live board? (G-09)
9. What clearance and creepage rules do you apply above 50 V, and would you trust a tool default? (G-01)
10. Do you verify USB or other pairs for skew and impedance today, and with what? (G-10)
11. What report do you hand to a reviewer or client, and who signs off? (G-14)
12. Do you open Mission Control, and what do you look at? (G-15)
13. Do you trust the readiness report numbers you saw (363 violations, 0 categorised)? (G-04, G-15)
14. Do you need KiCad or Altium import? (G-17)
15. Would a single pipeline command with explicit pauses for manual steps fit your workflow? (PX-03)
