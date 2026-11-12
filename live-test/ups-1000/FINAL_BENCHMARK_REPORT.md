# UPS_1000 — Final benchmark report (builder)

**Verdict: FAIL.** The board was not routed, so DRC and the manufacturing package were not achieved. No safety gate was weakened or bypassed. The independent examiner scored the run **46/100** and recommends FAIL. Final manufacturing release is still the Captain's decision; no fabrication order was placed and nothing was pushed or published.

## Measured time (monotonic clock, builder-records/timing.json)
| Stage | Result | Measured | Budget |
|---|---|---|---|
| S1 Requirements, DDIS, schematic | PASS | 26.44 min | 35 |
| S2 Placement, board outline, layers | PASS | ≈ 14 min | 35 |
| S3 Routing | FAIL (retry ceiling reached) | 31.31 min | 65 |
| S4 Copper / DRC | FAIL (blocked by S3) | ≈ 0.8 min | 20 |
| S5 Release | FAIL (release gate refused) | ≈ 0.7 min | 10 |
| S6 Independent examiner | PASS (6 documents) | ≈ 3.9 min | 15 |
| **Total** | | **78.22 min** | 180 |

The run ended well inside the 180-minute budget. It stopped because of the retry ceiling, not the deadline.

## Results by evidence class
* **Live EasyEDA, verified:**
  * Schematic: 123 parts and 58 nets; `verify all` VERIFIED in S1 and re-run fresh in S5. Lint (final mode) PASS; ERC 0 errors.
  * Board: 160 × 120 mm outline and 4 copper layers, both read back from the board.
  * Pad nets: 355 match between schematic and PCB, 0 mismatches.
  * Current board state: 123 components, 0 tracks, 0 vias, 0 fills.
  * DRC: 349 violations, all in the unconnected-pad class (0 clearance, 0 shorts). Readiness REJECTED.
* **Release gates (`tools/release.py revA --layers 4`):**
  * PASS: lint, offline ERC, blocks verified fresh, no pending live operations, live ERC 0, designators match the specs.
  * FAIL: live DRC.
  * Nothing was exported, and the option to skip DRC was not used.
* **Offline tests:** 721 tests, OK, 9 skipped (live-only). The examiner reproduced this result independently.
* **Calculated, not measured:**
  * IPC conductor sizing via `desk.ipc`, whose tables are UNVERIFIED.
  * The thermal assessment, done by hand because the thermal rule THERM-TJ-050 is unsupported.
* **Independently reviewed:** 6 examiner documents in `reviewer-analysis/`.

## Routing failure chain (S3)
* **F-010 (my error):** I poured the inner GND planes before routing. EasyEDA exported those fills into the router's input file as pseudo-pins. Freerouting threw an exception while loading the file and then ran 420 s with 0 passes until the timeout. The examiner is right that this showed up as a timeout. The underlying cause was the file-loading error recorded in `freerouting.log`.
  * **Fix:** a new `copper_fill.py --remove` option, and the rule that pours happen after routing.
* **F-011 (my error):** I hand-patched `design_profile.json` with free-text keys the loader does not accept. The profile failed to load, so the router saw the board's currents as undeclared and stopped. The notes now live in `PROFILE_NOTES.md`.
* **F-012:** the router itself ran: unrouted connections went from 106 to 70 in 5 passes, at about 84 s per pass. That exceeded the 300 s engine budget and no routed result was imported. This was the second retry, so the retry ceiling is reached.
* **Captain's decision before the next attempt:** route the power nets as polygons, narrow the router widths, or use PRECISION mode with a longer budget.

## Open discrepancy
The release gate reports "1 violations" for DRC, while the full DRC run in S4 reports 349. The two tools probably count differently (grouped categories versus individual items). I have not reconciled this. Both results are failing.

## Safety and release blockers
* **HV gate BLOCKED:** none of the high-voltage stages were designed (PFC, 380 V DC link, charger, BMS, 230 V inverter, mains EMI). No IEC 62040 or IEC 60664 compliance is claimed. Creepage and clearance figures come from DESK tables that are UNVERIFIED.
* **Electrical risks:**
  * RK-01: reverse polarity is not safely protected.
  * RK-02: the TVS clamp (96.8 V) exceeds the INA240 common-mode range (80 V), and margin to the 100 V parts is thin.
  * RK-03: the overvoltage trip margin is thin.
  * RK-04: there is no hysteresis or hardware latch.
  * RK-05: shoot-through current bypasses the shunt.
* **Board blockers:**
  * Decoupling capacitors sit 3.7–14.7 mm from their pins, against the 2 mm rule. The placement gate does not evaluate this rule, which is a DESK gap.
  * The 4 M4 mounting holes do not exist; there is no verified API for creating them.
  * The fabricator stackup for the 2.0 mm board is TBD.
* **Datasheet and part checks:** verification items V-01 to V-10 and missing requirements M-01 to M-13 are open.

## Human intervention
One. The schematic-to-PCB import appeared after every API path had failed (F-004 / B-001). There is still no working API path for this import.

## DESK changes (uncommitted, not pushed)
* `tools/desk.py`: fixed argument parsing for `domains validate`, with a test.
* `tools/resolve.py`: new `--refresh` option.
* `tools/pcb_place.py`: collision-aware placement of passives. It has **no unit test**.
* `tools/pcb_board.py`: new tool.
* `tools/copper_fill.py`: new `--remove` option.
* `desk/routing/orchestrator.py`: handles a timeout in the Freerouting compatibility probe, with a test.

## Comparison with ESP32-S3 Run 2
| | ESP32 Run 2 | UPS_1000 |
|---|---|---|
| Time | 66.7 min | 78.2 min |
| Board | 74×44 mm, 2 layers | 160×120 mm, 4 layers |
| Parts / nets | 40 / 43 | 123 / 58 |
| Routed | 43/43 | 0/58 |
| DRC | 0 | 349 (unrouted) |
| Manufacturing package | yes | none (release gate blocked) |
| Examiner score | 81/100 | 46/100 |

## Deliverables present
* REQUIREMENTS.md, BOM_SELECTION.md, BLOCK_PLAN.md and bom.csv.
* Block specs.
* DRC, ERC, lint and verify reports.
* THERMAL_ASSESSMENT.md and FAB_AND_ASSEMBLY_NOTES.md.
* EVIDENCE_MANIFEST.json (SHA-256 hashes of evidence files only). 3 of its hashes no longer match because those live logs grew after the manifest was written.
* The full set of benchmark records.

**Absent:** .epro file, schematic PDF, Gerber ZIP, drill files and CPL.

## Post-benchmark addendum (after the timed run, Captain-requested)
* **Routing attempt 6** (PRECISION, `--passes 16`) also failed: 103 → 90 unrouted in 3 passes, chunk TIMEOUT at 420 s, no SES imported. Live board unchanged (no copper).
* **Root cause found** (see `ROUTING_BLOCKERS.md`): the router clearance on 58–70 V nets is set to 1.25–1.30 mm, taken from the IEC 60664-1 creepage table. Those nets sit on 1.27 mm-pitch IC pins (LM5164, UCC21520), where the measured copper gap is about 0.67 mm, so the rule cannot be met. That leaves 64 pads with no legal escape and makes pass 1 take 4 min 25 s.
* **Second cause (DESK chunking defect):** chunks are capped at 300 s and must run at least 4 passes, and a chunk that times out keeps no SES, so all of its routing is discarded.
* **Next step:** the spacing-rule decision needs Captain sign-off before the next attempt.
