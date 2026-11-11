# Manufacturing Verification Report — sensor patch 6-up panel
Date: 2026-11-11 (IST). Writer: Claude Code (single writer). Gateway v1.0.5 / port 49620 / window cdb4f4b9-2470-478a-80fb-0815afcba72e.
Project "sensor patch" 3c48f00e08124f708d274da6a5f8abda. Panel source: **PCB1_1** a6e933d56b6ca092 (recovery copy). Master **PCB1** 7dac46c2fc1176fd untouched.

## 1. Geometric copy comparison (PCB1 → PCB1_1)
| Item | PCB1 | PCB1_1 | Match |
|---|---|---|---|
| Components (designator, x, y, rot, layer) | 22 | 22 identical | ✅ |
| Track segments (L1/L2/In1/In2) | 466 (149/204/74/39) | 466 (149/204/74/39) | ✅ |
| Vias | 44 | 44 | ✅ |
| Copper pour definitions (P3_GND, L1/L2/L15/L16) | 4 | 4 (POUR1-4) | ✅ |
| Poured fills | 4 | 4 | ✅ |
| Board outline | R(790,1360,435,965) mil | identical | ✅ |
| Document source diff after Panelize | — | only DOCHEAD + PANELIZE line changed | ✅ |

## 2. Panel instance verification (independent, from exported Gerber/drill — not from EasyEDA UI)
- All 16 Gerber layers carry `%SRX2Y3I11.04392J24.50592*%` → 2 columns × 3 rows, step 11.044 × 24.506 mm = **6 instances, same orientation** ("Rotated: No, Reflected: No").
- Gerber header: `Panelize: V-CUT, Column: 2, Row: 3, Panelized Method: All Objects, Copper Areas: 4`.
- Drill_PTH_Through_Via.DRL: **264 hits = 6 × 44 vias**, T01 Ø0.305 mm. Drill_PTH_Through.DRL: 264 hits (same, no PTH component holes in design).
- Drill_NPTH_Through.DRL: 10 hits = 4 × Ø2.0 mm rail positioning holes + 6 × Ø0.4 mm (one per board instance).
- Per-layer SR-block contents (×6 at fab): Inner1 44 via flashes/4 fill regions; Inner2 44/2; Top 94 flashes/12 regions/999 draws; Bottom 103/5/1087; Top silk 59 draws; Bottom silk 103 draws; outline 4 edges per board.
- Outside the SR block: panel outline + V-cut marker lines (14 segments), 4 fiducial flashes per copper/mask/paste layer (rails).
- Panel outline bbox: x 20.069→42.156, y 4.036→89.553 → **22.09 × 85.52 mm** (expected 22.10 × 85.53). Board cell 11.044 × 24.506 mm (expected 11.05 × 24.51; −5 µm from outline-centreline rounding, negligible).
- No overlapping boards: cells tile exactly at the step; copper of adjacent cells separated by 2 × 0.254 mm pull-back.

## 3. Native DRC (eda.pcb_Drc.check strict=true) on PCB1_1 after Panelize + refill
- **0 violations, 0 items** (rule set "Custom Config", not modified). Evidence: `05_drc_report/drc_PCB1_1_native.json`.
- PCB1 (bound to Board1) still shows its 1 pre-existing "Netlist Error / Import Changes" item.

## 4. Netlist-mismatch investigation
- Schematic page ecb3bdee5dab1c0b designators: C101-105, D101, FPC101-102, LED101, Q101-102, R101-105, U101/102/103/105/106/109.
- PCB designators: identical set with 3xx prefix. 22 = 22; same part roles.
- Verdict: **stale designator-prefix drift (1xx vs 3xx), not a genuine electrical mismatch**. Nets on PCB: 20 (P3_GND etc.). Not renumbered, schematic not altered, DRC not suppressed — Captain decision required on which numbering is canonical.

## 5. Copper
- 4 pour definitions and 4 poured fills present on PCB1_1; forced refresh via `pcb_PrimitivePour.modify` accepted for all 4; fill fingerprints identical before/after (geometry unchanged → identical fill is the expected outcome). Gerber "Copper Areas: 4" and G36 fill regions present on L1/L2/In1/In2.
- Limitation: EasyEDA exposes no "rebuild copper" API; the refill could not be independently distinguished from the existing valid fills. Fills are consistent with the current (unchanged) geometry.

## 6. Electrical isolation between the six boards
- Instances are RS-274X step-and-repeat copies; no copper is drawn across cell boundaries (block bbox x 20.323→30.858 / y 10.290→34.287 lies strictly inside the 20.069→31.112 / 10.036→34.544 cell).
- Rail copper consists only of 4 isolated fiducial pads (no nets). Positioning holes are NPTH.
- Gap between adjacent cells' copper = 0.508 mm (2 × 0.254 mm). → **Electrically independent by construction.**

## 7. Export inventory (`02_gerber_6up/sensor_patch_6up_gerber.zip`, sha256 1fc6c352d5799a9fd268a655ac897b6a9a599430f714a931cb784aa8abc02582)
Copper: GTL, G1, G2, GBL · Mask: GTS, GBS · Paste: GTP, GBP · Silk: GTO, GBO · Outline: GKO (board cells via SR + panel outline + V-cut lines) · Drill drawing GDD · Document GDL · Drills: PTH, PTH_Via, NPTH (Excellon, mm, 4.5) · JLC readme txt. Units mm, format 4.5, leading zeros omitted, absolute.

## 8. Open manufacturing constraints (not confirmable from local data)
1. Copper-to-V-cut clearance is **0.254 mm** (inherited from master). DESK rule of thumb ≥ 0.5 mm; fabricator figure must be confirmed. Fix would require changing the master pour clearance (design change → Captain sign-off).
2. Fab acceptance of `%SR` step-and-repeat Gerbers (standard RS-274X; some fabs request flattened files).
3. Fab minimum V-cut panel/board dimensions for a 22.09 mm-wide panel.
4. Designator prefix (1xx/3xx) canonical choice.

## Verdict
**REVIEW REQUIRED** — six-up panel produced, verified native, 0 DRC violations, exports complete; items 1-4 above are external/design decisions not confirmable here.
