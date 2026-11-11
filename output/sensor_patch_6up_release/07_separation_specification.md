# Separation Specification — sensor patch 6-up panel

Source document: PCB1_1 (uuid a6e933d56b6ca092), recovery copy of PCB1 (7dac46c2fc1176fd). PCB1 untouched.
Method: EasyEDA Pro native **Tools → Panelize** (PANELIZE record in the PCB document), exported as Gerber RS-274X step-and-repeat.

| Parameter | Value | Source |
|---|---|---|
| Separation type | **V-CUT** | Panelize dialog (Type = V-CUT) |
| Grid | 2 columns × 3 rows = **6 boards** | PANELIZE record `row:3,column:2,on:true` |
| Board-to-board spacing | 0 mm (shared V-cut edge) | `rowSpacing:0,columnSpacing:0` |
| Single board size | 11.05 × 24.51 mm (435 × 965 mil outline) | PCB1 outline polyline R(790,1360,435,965) |
| Step-and-repeat step | 11.04392 × 24.50592 mm | Gerber `%SRX2Y3I11.04392J24.50592*%` (all 16 layers) |
| Boards area | 22.09 × 73.52 mm | 2 × 11.044, 3 × 24.506 |
| Technology side (rails) | Top and Bottom, 6.0 mm each (236.2 mil) | Panelize dialog |
| Panel outline (Gerber) | x 20.069→42.156, y 4.036→89.553 → **22.09 × 85.52 mm** | gerber_inspection.json, GKO |
| Positioning holes | 2.0 mm (78.7 mil), NPTH, in rails | Panelize dialog; Drill_NPTH_Through.DRL |
| Fiducials | 1.0 mm (39.4 mil) pads, mask expansion 0.5 mm | Panelize dialog |
| Mirroring | none ("Rotated: No, Reflected: No") | Gerber header |
| Content | All Objects (full copper, mask, paste, silk, outline) | `onlyOutline:false`, Gerber header "Panelized Method: All Objects" |

## Why V-CUT (engineering decision, logged)
- Outline is a plain rectangle with straight shared edges; no component overhang, no cut-outs.
- 11 mm board edge is too short for mouse-bite tab groups without leaving large burr fraction.
- 4-layer rigid stack-up (Top, Inner1, Inner2, Bottom) — V-cut is the standard separation for rigid rectangular multiples.
- The "2 mm initial separation" from the brief applies to tab/mouse-bite channels; for V-cut the correct spacing is 0.

## Measured copper pull-back from board edge (from Gerber SR block vs outline cell)
- Copper bbox inside SR block: x 20.323→30.858, y 10.290→34.287; outline cell: x 20.069→31.112, y 10.036→34.544.
- Pull-back ≈ **0.254 mm (10 mil)** on all four edges → copper-to-copper gap across each V-cut line ≈ 0.51 mm.
- This clearance is inherited from the master design (PCB1) and was NOT altered. DESK manufacturing-verification skill recommends ≥ 0.5 mm pull-back for V-cut; fabricator's V-cut copper clearance must be confirmed (see verification report → REVIEW item).

## Fabricator constraints NOT verified in this session (no spec available locally)
- Minimum V-cut panel dimension / minimum board width for V-cut scoring.
- Required copper clearance to V-cut line.
- Whether the fab CAM accepts RS-274X `%SR` step-and-repeat (standard, but some fabs request flattened Gerbers).
