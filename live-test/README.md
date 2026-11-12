# DESK live tests

These are real end-to-end runs of DESK against a live EasyEDA Pro session, with independent review.
Each run keeps its frozen requirements, timing, failure register, reviewer analysis and output files, so
the results can be checked rather than taken on trust.

| Run | Board | Builder | Reviewer | Graded benchmark verdict | Current board |
|---|---|---|---|---|---|
| [`esp32-s3-plotus/`](esp32-s3-plotus/) | ESP32-S3 development board, 2 layers, 74 × 44 mm | Claude Opus 5.5 driving DESK | Claude Sonnet examiner (separate session) | **FAIL**, scored 50/100 | ✅ **EasyEDA DRC 0 errors**, all 43 nets connected (fixed after the benchmark) |

---

# ESP32-S3 development board: "Plotus" live benchmark (2026-11-12)

## 1. What was tested
Could an AI agent, using DESK as its only design tool, take a frozen requirements pack to a manufacturable
ESP32-S3 dev board in a live EasyEDA Pro project, within a fixed time budget and with no help in the GUI?

- **Tool under test:** DESK, an isolated benchmark copy of this repository. The live repository was not touched
  during the run.
- **CAD:** EasyEDA Pro 3.2.149, driven only through the local API gateway (`POST /execute`, one designated window
  ID). The rules were documented API calls only, readback after every change, and no GUI clicks by the agent.
- **Builder:** Claude Opus 5.5, as Claude Code.
- **Reviewer:** a Claude Sonnet examiner (`plotus-sonnet-examiner`) running as a separate session. It could write
  only to the evaluation folder and could not touch EasyEDA. Its job was 10-minute progress reports, hardware
  telemetry, a final independent verdict and a comparison with an earlier Nemotron 3 Ultra attempt.
- **Machine:** Windows 11, 15.3 GB RAM. Inference ran remotely, so the local GPU sat idle.

## 2. Benchmark parameters
### Time budget (monotonic clock, `time.monotonic_ns`)
| Stage | Budget (min) | Scope |
|---|---:|---|
| 1 Schematic | 45 | All essential blocks, LCSC-resolved parts, ERC evidence |
| 2 Placement | 45 | All parts placed, outline, holes, decoupling ≤ 2 mm, antenna keep-out, deterministic placement check |
| 3 Routing | 90 | Every net physically connected, 0 shorts / 0 critical DRC, USB constraints, routing record |
| 4 Copper | 30 | GND pour on top and bottom, every GND pad connected, no islands, stitching, clearances |
| 5 Manufacturing | 15 | Gerber, drill, BOM (LCSC), CPL, preflight checks |
| **Total** | **225** | **A stage cannot borrow time from another stage.** |

### Rules
- **Frozen requirements:** [`requirements/`](esp32-s3-plotus/requirements/). The SHA-256 hashes in
  `FROZEN_HASHES.txt` were checked during the run and never changed.
- **Stop rule:**
  - If a stage fails a hard gate, later stages that depend on it are not started.
  - Never force-terminate EasyEDA or unrelated sessions.
  - No orders are placed.
  - Nothing is pushed during the run.
- **Allowed verdicts:** PASS, PARTIAL PASS, TIME TARGET FAILED, FAIL, INCONCLUSIVE.
- **Required records:**
  - `timing.json`, `stage_metrics.json`, `progress.json`, `execution.jsonl`
  - a failure register
  - the reviewer's 10-minute reports, a telemetry CSV, a hardware report, a final evaluation and a comparison
    report

### Key design parameters (from `DESIGN_PARAMETERS.md`)
- **Board:** 2 layers, 1.6 mm, 1 oz copper. Minimum 5 mil track and space, 0.3 mm via drill. Rectangular outline
  with rounded corners. 4 × M3 holes.
- **Power path:** USB-C VBUS (5 V) → polyfuse → TVS → Schottky → AP2112K-3.3 LDO. Decoupling of 10 µF + 1 µF +
  100 nF per domain.
- **USB-C interface:**
  - native USB on GPIO19/20;
  - 5.1 kΩ pull-downs on CC1 and CC2;
  - a 4-line ESD array on D+/D−/CC1/CC2;
  - the connector centered on a short edge.
- **Controls and straps:** EN reset with a 10 kΩ / 1 µF RC network, BOOT on GPIO0, strapping pins handled.
- **Headers and indicators:** 2.54 mm headers on the long edges, a power LED and a status LED.

## 3. The design that was built
- **Module:** ESP32-S3-WROOM-1-N16R8 (LCSC C2913202).
- **USB-C:** TYPE-C-31-M-12 (C165948) with 5.1 k Rd on CC1 and CC2, and a TPD4E05U06DQAR ESD array (C125795).
- **Power:** SMD1206P050TF polyfuse, SMF5.0A TVS, SS34 Schottky, AP2112K-3.3 LDO (600 mA).
- **Controls and straps:**
  - EN 10 k / 1 µF RC network with a RESET button;
  - GPIO0 pull-up with a BOOT button;
  - GPIO3 pull-up, GPIO45/46 pull-downs.
- **Indicators and test points:** green power LED, blue LED on GPIO48. 8 test points: VBUS, 5V, 3V3, GND, EN,
  GPIO0, D+, D−.
- **Headers:** 2 × 1×20 2.54 mm headers carrying 31 GPIOs, UART0, EN and power.
- **Board:** 74 × 44 mm, 2 layers, 4 × M3 NPTH. Antenna flush with the edge and a keep-out across its full width.
- **Parts and nets:** 38 parts, 43 nets, every part with an LCSC number.

Deviations from the frozen text, all recorded:
- The parameter file lists GPIO4–7/15–17 as strapping pins. On the ESP32-S3 the straps are GPIO0/3/45/46, so no
  extra pull-ups were added.
- The "38 pins, 0.5 mm pitch" module description is wrong. The real footprint (41 pads, 1.27 mm pitch) was used.
- The board is 74 × 44 mm instead of about 60 × 40 mm, to fit 20-pin headers, corner M3 holes and the antenna
  keep-out.

| Schematic | Placement (Stage 2) | Copper (end of Stage 4) |
|---|---|---|
| ![schematic](esp32-s3-plotus/images/sch_overview_v2.png) | ![placement](esp32-s3-plotus/images/placement_v4_neat.png) | ![copper](esp32-s3-plotus/images/copper_final.png) |

## 4. Benchmark results (graded run)

> **Current status:** the board now passes EasyEDA DRC with **0 errors** (see §7). The table below keeps the
> graded result from when the clock stopped and adds the board's current state in the last column.
Clock ran from 04:50:28 to 06:33:18 IST: **102.8 of 225 minutes**. It stopped early because Stage 4 failed a hard
gate.

| Stage | Budget | Used | Builder result | Reviewer result | Current board (after fixes) |
|---|---:|---:|---|---|---|
| 1 Schematic | 45 | 28.3 | PASS (DESK verify and lint pass; EasyEDA ERC 0 errors) | PASS with caveats (1 ERC warning not itemised) | PASS |
| 2 Placement | 45 | 11.9 | PASS_WITH_DEVIATION | NOT FULLY MET: C5 is 2.7 mm from the module power pin (limit 2.0 mm), no rounded corners, DESK placement check `passed=false` | Unchanged deviations: C5 2.7 mm, no rounded corners |
| 3 Routing | 90 | 38.1 | PASS_WITH_DEVIATION: 42/43 nets, 0 clearance, 0 short; GND left to the pours | NOT FULLY MET: GND gate moved to Stage 4; USB not impedance-controlled; test-point stubs | ✅ 43/43 nets connected, 0 clearance, 0 short |
| 4 Copper | 30 | 23.3 | **FAIL**: 5 GND connection errors | **FAIL** | ✅ **DRC 0 errors**, GND fully connected |
| 5 Manufacturing | 15 | 0 | Not started (stop rule) | NOT STARTED | Rev A files exported (§8); release preflight not yet run |

- **Verdict:** **FAIL**. The builder and the reviewer agree.
- **Reviewer's production-readiness score:** **50/100**:

| Electrical | Physical | Manufacturing package | Evidence and honesty |
|---:|---:|---:|---:|
| 17/30 | 15/25 | 3/25 | 15/20 |

- **The failure is electrical:**
  - The USB ESD array (U1 pins 3 and 8) has no ground.
  - The CC2 pull-down (R2) floats, so USB-C won't attach in one plug orientation.
  - The EN reset capacitor (C8) floats.
- **Cause:** GND was left out of the router to save time, which walled these pads in with other nets' copper.
- **Time was not the problem.** No stage ran over its budget, and 122 minutes were unused.

### Human interventions (all recorded)
- **Before the clock:** the Captain reconnected an EasyEDA window whose ID had gone stale.
- **H-001:** the Captain clicked *Apply* in Import Changes, because the API cannot apply schematic-to-PCB changes.
- **H-002:** the Captain approved downloading Freerouting 2.1.0, since no routing engine was installed.
- **H-003:** the agent asked for a GUI "rebuild copper" click, and the Captain **declined** it.
- **Requirements added during the run:** schematic neatness and manufacture-grade placement neatness.

### Failure register
The register holds 23 entries (F-001…F-020 and H-001…H-003): [`failure_register.json`](esp32-s3-plotus/builder-records/failure_register.json).
DESK defects it exposed:
- **DRC summary:** DESK's summary reported 0 clearance errors when there were 174 real ones (F-015). The raw
  EasyEDA DRC was used instead.
- **Board outline:** the outline JS had the wrong signature and placed the origin at the top-left (F-008, F-009).
- **Library:** stale short-UUID library entries made part creation hang for 120 s (F-001).
- **Pours:** `rebuildCopperRegion()` cannot be driven through the API in this client (F-018). This led to the new
  API-only copper fill, see §6.

## 5. Reviewer analysis (uploaded unchanged)
All files are in [`reviewer-analysis/`](esp32-s3-plotus/reviewer-analysis/):
- [`FINAL_INDEPENDENT_EVALUATION.md`](esp32-s3-plotus/reviewer-analysis/FINAL_INDEPENDENT_EVALUATION.md): a
  gate-by-gate verdict, a review of the failure register and the score.
- [`OPUS_VS_NEMOTRON_COMPARISON.md`](esp32-s3-plotus/reviewer-analysis/OPUS_VS_NEMOTRON_COMPARISON.md): **not
  comparable.** The Nemotron 3 Ultra project folder holds the requirements and empty templates only. The reviewer
  declares no winner.
- [`HARDWARE_PERFORMANCE_REPORT.md`](esp32-s3-plotus/reviewer-analysis/HARDWARE_PERFORMANCE_REPORT.md) and
  [`HARDWARE_RESOURCE_METRICS.csv`](esp32-s3-plotus/reviewer-analysis/HARDWARE_RESOURCE_METRICS.csv): 103
  samples, one per minute.
  - CPU averaged 64 %, and EasyEDA held a steady ~41 %.
  - Free RAM dropped as low as 317 MB when EasyEDA and the Freerouting JVM ran together.
  - The GPU sat idle.
- [`10_MIN_REPORTS/`](esp32-s3-plotus/reviewer-analysis/10_MIN_REPORTS/) holds the progress reports from T+10 to
  T+100. **Five of them (T+20, T+60, T+70, T+90, T+100) were written late, after the fact.** The reviewer could
  only run while prompted, so supervision was not continuous. This is disclosed in
  [`EVALUATOR_LIMITATIONS.md`](esp32-s3-plotus/reviewer-analysis/EVALUATOR_LIMITATIONS.md).
- Two questions the reviewer raised for the Founder remain open:
  - The "stop rule" is not in the frozen files.
  - A DESK connectivity report said 2/43 nets, against 42/43 from EasyEDA DRC and the independent check. This
    was never explained.

## 6. DESK changes made because of this run
- **`desk/copper_fill.py` and `tools/copper_fill.py`: API-only GND planes.** DESK now computes the plane copper
  itself and writes it as `pcb_PrimitiveFill` polygons. The design:
  - clearance to other-net copper;
  - thermal spokes on through-hole pads;
  - removal of islands that have no via or through-hole anchor;
  - idempotent re-runs, tracked in `state/copper_fills.json`.

  This cut ground opens from 73 to 5 with no help in the GUI.
- **`tools/stitch_orphans.py`: clearance-checked stitch vias for orphan copper and pads.** After the run it also
  gained `explicit_link()`. Every via placed for an orphan pad now also gets a straight, clearance-checked bottom
  track to an existing GND via. Pads that already have a GND track are skipped. Why: EasyEDA's DRC does not
  reliably join a via to a static fill. Two vias sitting fully inside both GND fills, with copper confirmed in the
  Gerbers, still raised "Connection Error", and the outcome depended on creation order.
- **Library:** refreshed the stale entries for TPD4E05U06DQAR and SS34, and added the Plotus parts.
- **Tests:** `tests/test_copper_fill.py` has 4 tests, all passing.

## 7. After the benchmark: DRC 5 → 0 (not graded)
At the Captain's request, after the clock stopped, the last five errors were fixed with explicit copper:
- a GND track U1.3 → U1.8 → R2.2;
- the 3V3 track around C8 moved to the bottom layer, freeing a top GND track from C8.2 to a GND via;
- a link from the module GND pin U3.1 to the ground area near C5/C6.

Every change was clearance-checked before it was made (minimum 0.219 mm, against a 6 mil rule). Then both GND
planes were recomputed.

- **EasyEDA DRC:** `pcb_Drc.check(true,false,true)` reports **0 errors**, confirmed twice:
  [`drc_final_post_remediation.json`](esp32-s3-plotus/builder-records/drc_final_post_remediation.json).
- **Connectivity:** all 42 signal and power nets are connected by tracks, and GND forms one connected group.
- **Full record:** [`REMEDIATION_RECORD.md`](esp32-s3-plotus/builder-records/REMEDIATION_RECORD.md).

![C8 area after remediation](esp32-s3-plotus/images/remediation_C8_area.png)

## 8. Output files: revision A (exported after remediation)
These are in [`manufacturing-revA/`](esp32-s3-plotus/manufacturing-revA/), exported from the live project:

| File | Contents |
|---|---|
| `PLOTUS_ESP32S3_revA_gerber.zip` | Gerber for copper (top/bottom), solder mask, silkscreen, paste, outline and document layers; PTH, NPTH and via drill files (67 vias); flying-probe data |
| `PLOTUS_ESP32S3_revA_schematic.pdf` | Schematic, 4 blocks on one sheet |
| `PLOTUS_ESP32S3_revA_BOM_JLCPCB.csv` | JLCPCB-format BOM with an **LCSC Part #** column: 18 lines covering 38 parts, cross-checked against EasyEDA's BOM |
| `PLOTUS_ESP32S3_revA_bom_utf8.csv` | EasyEDA's own BOM export, converted to UTF-8 |
| `PLOTUS_ESP32S3_revA_cpl_utf8.csv` | Pick-and-place (CPL), 38 parts, in mm |
| `PLOTUS_ESP32S3_revA_project.epro` | The full EasyEDA Pro project. Import it with *File → Open → EasyEDA Pro project* |

> **Not production-released.** DRC is clean, but these items are still open before ordering:
> - C5 is 2.7 mm from the module 3V3 pin (limit 2.0 mm).
> - The board corners are not rounded.
> - The silkscreen labels have not been reviewed.
> - The USB pair is not impedance-controlled, and test points TP7/TP8 add stubs on D+/D−.
> - Two stray block-title labels sit at the right edge of the schematic sheet.
> - A new GND via sits under the module body. It is tented, and outside the antenna keep-out.
>
> Run Stage 5 preflight (`tools/release.py`) before placing any order.

## 9. Folder map
```
live-test/esp32-s3-plotus/
  requirements/        frozen requirements, design parameters, acceptance criteria and hashes
  builder-records/     final engineering report, failure register, timing, stage metrics,
                       placement/routing/remediation records, DRC results
  reviewer-analysis/   independent evaluation, comparison, hardware report, telemetry CSV,
                       10-minute reports, limitations, examiner log
  manufacturing-revA/  Gerber, schematic PDF, BOMs, CPL, EasyEDA project (.epro)
  images/              schematic, placement, copper, remediation views
```
