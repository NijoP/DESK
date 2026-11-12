# Post-benchmark DRC remediation (2026-11-12, after the clock stopped at 06:33:18)

Requested by the Captain after the benchmark ended ("make the drc error to 0"). **This does not change the benchmark
result**: Stage 4 FAIL / overall FAIL stand as graded. This work is outside the timed run.

## Result
EasyEDA DRC `pcb_Drc.check(true,false,true)`: **5 → 0 errors** (`drc_r11.json`, confirmed again in `drc_r12_confirm.json`).
- The independent copper-track checker (`benchmarks/connectivity.py`, no fills) shows 42/43 nets fully connected by tracks.
  GND relies on the plane fills by design.
- The geometric model with fills (`benchmarks/remed_conn_model.py`, `snap_final.json`) puts all GND objects in
  **1 group** (106 objects).

## Root cause of the last 5 errors (F-019)
1. **U1.3, U1.8 (ESD) and C8.2 (EN RC):** real opens. The pads were walled in by CC1/CC2/USB and 3V3 copper, so no
   fill could reach them.
2. **R2.2 and fill e156/e172/e188:** the copper is physically connected. The Gerber copper covers the vias, and the
   geometric union-find connects them. EasyEDA's DRC connectivity still did not link these particular vias to the
   API-created `pcb_PrimitiveFill` pours.
   - The behavior depends on creation order. Recreating via (65.80, 36.61) split its group further (drc_r7: 4 errors).
     Re-creating the fills restored it (drc_r10).
   - Ratline recalculation (`stopCalculatingRatline` / `startCalculatingRatline`) did not change the result (drc_r4).
   - **Lesson for DESK:** do not rely on a via-to-API-fill join for a pad's only connection. Give it an explicit
     track path to copper that is already connected.

## Changes (all through documented `pcb_PrimitiveLine` / `pcb_PrimitiveVia` calls)
Each plan was clearance-checked offline before creation (min 0.16 mm vs. 6 mil rule). Created IDs are in `*_applied.json`.

| Plan | Change | Min clearance |
|---|---|---|
| plan1 | Bottom GND tracks: via(11.63,19.00)→via(11.76,16.84); via(65.80,36.61)→via(64.53,33.66) (experiment; kept, harmless, same net) | 0.74 mm |
| plan2 | Bottom GND track: via(11.76,16.84)→J1.1 USB-C shell TH pad (experiment; kept) | 1.99 mm |
| plan3 | **Top GND track U1.3→U1.8→lane west of U1→R2.2** (cleared U1_3, U1_8, R2_2). Probe stub created and deleted. | 0.219 mm |
| exp4 | Via (65.80,36.61) deleted and recreated at the same spot (new id 074449b8fa79c493) | — |
| plan4 | **3V3 jog around C8 moved to the bottom layer.** Deleted 4 top segments; added 1 top segment, 2 × 3V3 vias (60.90,37.69)/(63.20,35.55) and 1 bottom segment. **Top GND C8.2→via(65.80,36.61); top GND U3.1→new via (66.29,29.35)→bottom track to via(64.53,33.66)** (cleared C8_2 and the fill) | 0.259 mm |

Then `DESK tools/copper_fill.py --clearance 0.3` re-poured both GND planes around the new copper.

Notes:
- The new GND via at (66.29, 29.35) sits under the WROOM module body. It is tented by default. It is 0.3 mm from the
  antenna keep-out edge (x = 66.9) and outside it.
- C8.2 now reaches GND through a 3.4 mm, 0.25 mm-wide track. That is acceptable for an RC timing capacitor.

## Not done
- Gerber/BOM/CPL in `manufacturing/NOT_RELEASED/` were **not** re-exported. They reflect the board at 06:32, the
  benchmark state. A new export is needed before any release.
- The other release blockers from the final report remain: C5 2.7 mm from the module 3V3 pin, no LCSC column in the
  BOM, rounded corners, silkscreen review.
