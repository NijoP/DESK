# Plotus — ESP32-S3 Development Board — Final Engineering Report (builder: Claude Opus 5.5)

Engineering clock 04:50:28 → 06:33:18 IST = **102.8 min of 225** (ended early: Stage 4 failed a hard gate and the
stop rule forbids starting Stage 5). Independent grading is in `C:\nemotron test\Plotus\evaluation\` (Sonnet examiner);
this report is the builder's own record and does not grade itself beyond the evidence listed.

## Builder's verdict: **FAIL** (major hard gate unmet), with valuable partial output
The board is **not manufacturable as-is**: 5 GND connection errors leave the USB ESD array (U1 pins 3/8), the CC2 Rd
pull-down (R2.2) and the EN RC capacitor (C8.2) floating (F-019). Everything else listed below is verified.

| Stage | Budget | Used | Result | Key evidence |
|---|---:|---:|---|---|
| 1 Schematic | 45 | 28.3 | PASS | `schematic/reports/verify_all.txt` VERIFIED (38 parts, 43 nets, no single-pin nets); `lint_final.txt` PASS; `erc_report.txt` EasyEDA ERC 0 errors |
| 2 Placement | 45 | 11.9 | PASS_WITH_DEVIATION | `pcb/placement/` — 38/38 readback-matched; DESK gate 1 error (C5 bulk 10 µF 2.7 mm > 2.0 mm, F-011); rounded corners deferred |
| 3 Routing | 90 | 38.1 | PASS_WITH_DEVIATION | `pcb/routing/` — 42/43 nets copper-connected (GND deferred to pours), EasyEDA DRC 0 clearance / 0 short, power 10 mil, USB ΔL ≈ 2.8 mm |
| 4 Copper | 30 | 23.3 | **FAIL** | `pcb/copper/drc_final_stage4.json` — 0 clearance/short, **5 GND connection errors** |
| 5 Manufacturing | 15 | 0 | NOT STARTED (blocked) | `manufacturing/NOT_RELEASED/` evidence export only |

## Design summary
ESP32-S3-WROOM-1-N16R8 (C2913202); USB-C TYPE-C-31-M-12 (C165948) with 5.1 k Rd on CC1/CC2, TPD4E05U06DQAR 4-line ESD
(D+/D−/CC1/CC2), SMD1206P050TF 0.5 A polyfuse → SMF5.0A TVS → SS34 Schottky → 5 V rail → AP2112K-3.3 LDO (600 mA);
native USB on GPIO19/20; EN 10 k/1 µF RC + RESET; GPIO0 10 k pull-up + BOOT; GPIO3 pull-up, GPIO45/46 pull-downs;
green power LED, blue GPIO48 status LED; 8 RH-5015 test points (VBUS, 5V, 3V3, GND, EN, GPIO0, D+, D−); 2 × 1×20
2.54 mm headers (31 GPIO + UART0 + EN + power); 74 × 44 mm 2-layer board, 4 × M3 NPTH, antenna flush at the edge with a
full-width keep-out. All parts LCSC-resolved through DESK (`libraries/`, block specs carry the LCSC numbers).

## Deviations from the frozen requirements (all recorded, none silent)
- DESIGN_PARAMETERS calls GPIO4-7/15-17 strapping pins; ESP32-S3 datasheet strap pins are 0/3/45/46 → no extra pull-ups.
- DESIGN_PARAMETERS "38 pins, 0.5 mm pitch" module is wrong (41 pads, 1.27 mm); actual footprint used.
- Board 74 × 44 mm vs "~60 × 40 (adjustable)": 20-pin headers + corner M3 + antenna keep-out.
- GPIO19/20 not on headers (USB, avoids stubs); GPIO35-37 NC (octal PSRAM).
- USB pair not impedance-controlled (2-layer); TP7/TP8 are stubs on D+/D− (required test points).
- Rounded corners not applied (DESK: only plain 'R' outlines export a correct DSN).
- C5 bulk cap 2.7 mm from the module 3V3 pin (F-011).

## Human interventions
Pre-clock: Captain reconnected the stale EasyEDA window. H-001 Captain clicked Apply in Import Changes (API cannot apply).
H-002 Captain approved downloading Freerouting 2.1.0 (no engine in the repo). H-003 GUI copper rebuild requested and
**declined** by the Captain. Mid-run requirement additions by the Captain: schematic neatness, manufacture-grade placement neatness.

## DESK changes made in the benchmark copy (committed locally, not pushed)
- `desk/copper_fill.py`, `tools/copper_fill.py`: API-only copper planes (pcb_PrimitiveFill) — needed because
  `rebuildCopperRegion()` fails in this client (F-018). Verified: Gerbers contain 16 G36 regions (12 top, 4 bottom).
- `tools/stitch_orphans.py`: clearance-checked vias for orphan plane islands/pads.
DESK defects found and only worked around (not patched): outline JS signature (F-008), outline origin (F-009),
pcb_check text printer (F-010), Freerouting probe (F-013), DRC parser counts (F-015), resolve --pick (F-006),
clear_block rectangle Y sign (F-005), stale short-uuid library entries (F-001).

## What would close the FAIL (not done — out of time/stage)
Re-route with GND kept for the enclosed pads (U1.3/U1.8/R2.2/C8.2) or move CC2/USB tracks to open a via site beside U1;
root-cause the ~0.1-0.15 mm discrepancy between DESK fill geometry and EasyEDA's fill-clearance measurement so the
fill can run at 0.2 mm; then Stage 5 preflight with silkscreen labels and LCSC columns in the BOM.

Failure register: `failures/failure_register.json` (23 entries). Timing: `benchmarks/timing.json`, `stage_metrics.json`,
`logs/execution.jsonl`.
