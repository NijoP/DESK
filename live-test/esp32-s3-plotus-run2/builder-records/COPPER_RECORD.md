# Copper record: run 2b, Stage 4

Window 17ea844c. All numbers below come from live readback (benchmarks/snap_r2b_s4b.json) in this session.

## Pour
- **Method.** GND pours on both layers come from DESK `tools/copper_fill.py` (desk/copper_fill.py) as static
  `pcb_PrimitiveFill` polygons. EasyEDA's pour engine cannot be driven by the API (see the run 1 register).
- **Clearance.** 0.3 mm to other-net copper.
- **Edge clearance.** 0.5 mm inset from the board edge, plus 2.5 mm rounded-corner keep-outs and the J1 slot keep-outs.
- **Thermal reliefs.** Every through-hole GND pad gets a 0.3 mm gap and four 0.35 mm spokes: J1.1–4, J2.2, J3.1/16/20.
- **Slivers and islands.** Slivers are removed by an opening of 0.2 mm minimum neck. Islands are pruned, meaning any
  piece that does not touch a GND via or a through-hole GND pad, or is smaller than 2 mm², is removed.

| Layer | Pieces | Copper | Bounds (mm) |
|---|---|---|---|
| Top (1) | 13 | 1668.7 mm² | 0.5 .. 66.9 × 0.5 .. 43.5 |
| Bottom (2) | 2 | 2095.2 mm² | 0.5 .. 66.9 × 0.5 .. 43.5 |

- **Antenna keep-out.** The keep-out runs x 66.9 .. 74.0 mm across the full board width, on both layers. Pour copper
  inside it measures **0.000 mm²** on both layers. No tracks or vias are placed there.
- **Regulator.** U2 (LDO, rot 270) has its GND pin 2 joined to the top pour as well as its routed GND track.

## Stitching
- **Grid.** `stitching.py` runs DESK `CopperPlaneEngine.synthesize_stitching_vias` on a 5.08 mm grid over the 74 × 44 mm
  board, with the keep-outs and copper keep-outs applied.
- **Filters.** Each grid point keeps an 8 mil clearance to tracks and vias, sits at least 0.4 mm from component bodies,
  and avoids the mounting holes.
- **Vias.** 68 grid points were evaluated and **35 vias** created, each 0.3 mm drill / 0.6 mm pad
  (`stitching_vias.json`).
- **Second vias.** `stitch_second_via.py` found 6 pour pieces with no pad or track anchor, each held by a single via.
  Each got a **second GND via** at least 3.2 mm from the first (`second_vias.json`). A re-run finds no single-via pieces.
- **Totals.** The board has 50 GND vias. 49 sit inside the pour on both layers. The remaining one, U1's GND escape via
  at (10.3, 22.6), is joined by tracks on both layers.

## Result (hard gates)
- **EasyEDA DRC** (`pcb_Drc.check(strict, verbose)` after the final refill): **0 violations** (drc_s4_2.json; drc_s4_1.json was also 0).
- **DESK PhysicalConnectivityVerifier** with the live fills as zones: **43/43 nets fully connected (100.0%)**, 0 illegal.
- **Strict GND model** (the run 1 lesson that a via is not trusted to join a fill).
  - The routed GND (pads + tracks + routing vias) was one group before stitching (Stage 3, gnd_links.py).
  - Only the stitching vias and the via-only pour pieces depend on via-to-fill joins. EasyEDA DRC (0 Connection Errors)
    and the DESK verifier both confirm those joins after the final refill, and every such piece has at least 2 vias.
- **Saved.** `pcb_Document.save()` returned true.
