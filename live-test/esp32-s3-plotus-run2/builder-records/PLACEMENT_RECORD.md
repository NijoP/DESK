# Placement record, run 2b Stage 2

DESK 2c9de1a (latest GitHub main) plus a local fix to the `pcb_check.py` text-mode crash (see failures R2-F-006).
Window 17ea844c.

## Board
- Size 74 x 44 mm, 2 layers.
- Outline: one closed polyline on layer 11 from `["R", 0, 1732.2835, 2913.3858, 1732.2835, 0, 78.7402]`. That is a
  rectangle with **2 mm rounded corners**, and the readback matches.
  - Finding (R2-F-007): the EasyEDA "R" polygon is `[x, y_TOP, w, h, rotation_deg, corner_radius]`.
  - DESK's `desk/routing/outline.py` passed y=0 and treated field 6 as the radius. That drew the board below the
    parts, and a non-zero field 6 rotated it into the "skewed" shape that DESK had blamed on rounded corners.
- Mounting holes: 4 NPTH, 3.2 mm, at (3.5,3.5), (3.5,40.5), (64,3.5) and (64,40.5) mm, with 5.5 mm screw-head keep-outs.
  Readback: MH1..MH4 at 137.8/1594.5 and 137.8/2519.7 mil.
- Import Changes: 40/40 parts imported. The Apply click was done by the Captain (planned intervention).

## Placement: 40 parts on the top side; plan in placement.json
The functional rows are carried over from run 1's neat layout. Run 2b changes:

| Change | Why |
|---|---|
| C7 100nF / C6 1uF / C5 10uF placed as a row directly above U3 pin 2 (3V3), at y=33.3, x=64.6/66.2/62.9 | Run 1 F-011: C5 was 2.7 mm away. Now **0.85 / 0.86 / 0.88 mm** body-to-pad (decoupling_distances.txt). |
| C9 1uF / C10 100nF on 5V at the U2 input, column x=27.0 under C2 | New parts (Stage 1). |
| R4/C8 (EN RC) moved to x=60.6 | Clears the C5 body (gap warnings removed). |
| `reserved` corridor [18,18]-[48,30] mm | Keeps the USB D+/D- pair path (J1 -> U1 -> TP7/TP8 -> U3 IO19/IO20) and the 3V3 trunk free of parts. |

## Gate: `tools/pcb_check.py --gate` -> PLACEMENT & ROUTABILITY OK (placement_check_final.json)
- 0 errors. Routability score 0.88 (run 1: 0.6). Escape congestion 0.16. MST 1286 mm. 58 ratsnest crossings.
- 1 warning: hotspot cells at (1.2..3.8, 18.8..23.8) mm. That is the USB-C receptacle J1 itself (dense 24-pin
  footprint at the edge), not crowding between parts.
- Antenna keep-out x >= 66.9 mm, full width, both sides: no violations. Plan/board sync: in sync.

## Mechanical criteria
- USB-C at the board edge, centred on the left short edge (y=22).
- BOOT/RESET at the left edge (y=10.5 / 33.5).
- Headers: 1x20 at 2.54 mm on both long edges.
- Regulator U2 sits in the power row and will get the GND/5V pour in Stage 4.
- Render: placement_r2b.png.
