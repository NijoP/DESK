# Release record: run 2b, Stage 5 (rev A)

All files come from the live EasyEDA project (window 17ea844c) through read-only exports
(`benchmarks/export_release_files.py`). **No order was placed.**

## Final gates (after the silkscreen changes)
- **EasyEDA DRC:** **0** (pcb/drc_final_r2b.json).
- **DESK PhysicalConnectivityVerifier with fills:** 43/43 nets fully connected.
- **Silkscreen** (pcb/silk/silk_check.json, live text boxes from `getPrimitivesBBox`): **PASS**.
  - 90 texts: 40 designators plus 50 labels.
  - Minimum height 0.914 mm (rule ≥ 0.8 mm); stroke 0.15 mm.
  - Minimum gap to a pad is 0.358 mm (rule ≥ 0.15 mm).
  - Every text is at least 0.4 mm inside the board, and no two texts overlap.
- **Designators** (pcb/silk/silk_place.json): moved clear of pads, part bodies and holes.
- **Labels** (pcb/silk/silk_labels.json):
  - Top: the brand line "PLOTUS ESP32-S3 DEV  REV A" (1.27 mm), and a net-function label at each of TP1–TP8
    (VBUS, 5V, 3V3, GND, EN, IO0, D+, D-).
  - Bottom (mirrored): the brand line "PLOTUS ESP32-S3 DEVKIT  REV A  2026-11", and a pin label for every pin of
    J2 and J3.

## Post-end refinement (disclosed, logged as bench event POST_END_REFINEMENT at T+68.1 min)
Two open 45-degree 5V track junctions at C9 (from `pcb/routing/angle_check.json`) were removed (`plan_5v_c9_angles.json`). The joins now sit on the C9.1 pad.
Re-verified afterwards: GND refill, **DRC 0**, **43/43**, silkscreen PASS. Files re-exported (hashes below).

**Acute-corner audit** (`angle_check.json`): 5 corners under 90 degrees remain, and none is open copper. Three are covered by a same-net pad or via (U3.41, U2.5, the USB_DN J1 join via). The other two are one GND junction at (14.54, 22.6) inside the solid bottom GND pour (0.3 mm margin). Teardrops: none (not available through the API).

## Files
| File | SHA-256 (first 16) | Content |
|---|---|---|
| PLOTUS_ESP32S3_revA_gerber.zip | E954589CA8E64E53 | GTL, GBL, GTO, GBO, GTS, GBS, GTP, GKO, plus Drill_PTH, Drill_NPTH and Drill_PTH_Via |
| PLOTUS_ESP32S3_revA_BOM_JLCPCB.csv | 88B9C16AA2F361CC | 18 lines, 40 parts, **LCSC part # on every line** (make_bom_lcsc.py, MPN cross-checked against the block specs) |
| PLOTUS_ESP32S3_revA_bom.csv | C3447B1AED681828 | raw EasyEDA BOM export |
| PLOTUS_ESP32S3_revA_cpl.csv | 57E0101DF3E052B8 | pick and place, 40 parts, mm, layer and rotation |
| PLOTUS_ESP32S3_revA_schematic.pdf | 7D740966E0D0C4CD | schematic |
| PLOTUS_ESP32S3_revA_project.epro | 72F2386617A2C91F | EasyEDA project |

The files without an extension are the raw exports. The `.zip`/`.csv` files are identical copies (same hash).

## Not produced
- **Schematic SVG:** `eda.sch_ManufactureData.getSvgFile` does not exist in this client ("is not a function").
  The PDF is the schematic deliverable.
- **DESK `tools/release.py`:** not used, because its ledger and offline-lint gates expect a `projects/<P>` DESK project.
  The equivalent live gates (DRC 0, connectivity, BOM designators equal to spec designators) are recorded above.
