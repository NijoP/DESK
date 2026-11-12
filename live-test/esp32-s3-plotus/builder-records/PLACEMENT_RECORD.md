# Placement record (Stage 2)
Board 74 x 44 mm, 2 layers, outline single closed rectangle (bbox readback -5..2918 x -5..1737 mil incl. 10 mil line).
Rounded corners: deferred - DESK verified only plain 'R' outlines export a correct DSN for routing (INC-20261111-008); corner radius to be applied before manufacturing and re-verified.
Mounting holes: 4x NPTH 3.2 mm at (3.5,3.5) (3.5,40.5) (64,3.5) (64,40.5) mm; screw-head keep-outs 5.5 mm square.
Antenna keep-out: x >= 66.9 mm full width, both layers; module antenna flush with right edge (U3 at 57.4,22 rot 270; body edge -0.02 -> fixed).
USB-C J1 centred on left short edge (y=22), mouth flush; ESD U1 1.35 mm behind the pads; BOOT/RESET at the left edge.
Headers J2/J3 1x20 2.54 mm on the long edges, pin 1 toward the module, 1.17->0.82 mm from edge.
Gate (tools/pcb_check.py --gate --json): 1 error remaining: C5 bulk 10uF 2.2 mm from U3 pin2 (limit 2.0) - see failure F-011. C6 1uF and C7 100nF compliant.
Routability score 0.6, escape congestion 0.16, MST 1636 mm (placement_check_2.json).
Switch footprint check: SW1/SW2 pads 1 (-3,+1.88) and 4 (+3,-1.88) are diagonal -> switched under either internal pairing.
Evidence images: placement_v3.png (render may be stale; outline confirmed by bbox readback).

## Rework for neatness (Captain requirement, ~05:30, within Stage 2 deadline)
- Grid-aligned functional rows: power chain y=15 (F1, D2, C2, U2 rot270 in-left/out-right, C3, C4); test points y=7 at 4.5mm pitch (TP1-TP4, TP6); indicators y=10 (LED1, R3, LED2, R9); strap resistors column x=46 (R5, R7, R6, R8); USB column x=10.6 (R1, C1, R2) symmetric about the connector axis y=22; TP7/TP8 symmetric; BOOT/RESET symmetric (y=10.5 / 33.5); TP5 aligned with RESET row and the x=14.5 column.
- Each functional group uses a single orientation; all body gaps >= 0.25mm (0 spacing warnings).
- Gate (placement_check_4.json): only error = C5 bulk 2.7mm from U3 pin 2 (F-011). Readback: 38/38 parts match plan (pos +/-0.06mm, rotation exact).
- Silkscreen designator positioning and header pin labels to be done in Stage 5.

## Post-closure change (disclosed)
- Stage 3 routing recovery F-016 moved U1 (ESD) from x=10.6 to x=11.6 mm. Placement gate was not re-run after that move; the
  Stage 2 artefacts above describe the 05:30:51 state. Current positions: schematic/desk/placement.json and pcb_dump.json in this folder.
