# Routing record: run 2b, Stage 3

DESK 2c9de1a (latest GitHub main) plus run 2b fixes (see the failure register). Freerouting 2.1.0 on OpenJDK 23.
Window 17ea844c. All numbers below come from live readback in this session.

## Passes
| Pass | What | Result |
|---|---|---|
| r2b_run1 | Freerouting, all 43 nets **including GND** (run 1 had excluded GND), 3 min | 42/43 nets; GND plateaued at 29 unrouted from pass 4 to pass 360. USB topology unusable: TP7 on a ~7 mm branch, U1 on a ~9 mm branch, and a run under the module. **Discarded** (all 444 tracks, 33 vias and 7 fills deleted). |
| usb_route.py | Hand-designed USB D+/D- chain plus the U1 GND escape, clearance-checked (min 0.158 mm), injected into the DSN as `(type protect)` wiring | ALL OK |
| r2b_run2 | Freerouting around the protected wiring, 4 min | 42/43 nets; GND 26 islands; SES imported (445 tracks, 26 vias) |
| usb_widen.py | EasyEDA's SES import applies the 6-mil rule width, so the pair was restored to its 10-mil design width (24 segments); 2 zero-length/duplicate slivers deleted | done |
| copper_fill.py + stitch_orphans.py | GND fills on both layers (0.3 mm clearance, 0.5 mm edge inset, 2.5 mm rounded-corner keep-outs) plus 7 stitch vias / 4 links | done |
| gnd_links.py + remed_apply.py | Strict GND model (**a via is NOT joined to a fill**): 7 explicit bottom-layer links, each clearance-checked before creation | GND = 1 group |
| plan_j1_gnd.json | J1 GND pins A1B12/B1A12 -> existing GND stitch vias (0.375 mm clearance) | done |
| widen_power.py | VBUS / VBUS_PROT / 5V / 3V3 to 12 mil (0.305 mm), DRC-driven neck-down | 100/118 at 0.305 mm, 18 at 0.254 mm |
| TP7/TP8 in-line move | TP8 at (51.05, 36.4) rot 90 on the D- corner; TP7 at (49.1, 33.2) rot 0, so the D+ drop (x = 49.78) runs through its 2.8 × 1.5 mm pad. Rot 90 at x = 49.78 failed the gate (overlapped the U3/TP8 bodies). D+ drop re-segmented (plan_tp7_resegment2.json) | gate OK; DRC 2 (TP7 pad vs 3V3) |
| plan_3v3_tp7.json | Two 3V3 top segments rerouted west/south of the TP7 pad (min clearance 0.153 mm; the diagonal necked down to 0.254 mm) | **DRC 0** (drc_s3_8.json) |

## Result (hard gates, final readback after the TP move, snap_r2b_s3o.json)
- **EasyEDA DRC** (`pcb_Drc.check(strict, verbose)`): **0 violations** (drc_s3_8.json = `[]`; earlier drc_s3_4.json also `[]`).
- **DESK PhysicalConnectivityVerifier** with the live fills as zones: **43/43 nets fully connected (100.0%)**, 0 illegal
  (connectivity_report.json).
- **Strict model** (gnd_links.py / remed_conn_model.py): GND is a single connected group even when via-to-fill joins are
  not trusted, so run 1's failure mode (F-0xx: via-to-fill joins rejected by DRC) cannot recur.
- GND was routed and verified **inside Stage 3**. Run 1 had deferred it to Stage 4.

## USB D+/D- (usb_pair_check.json, from live readback)
| Item | D+ (USB_DP) | D- (USB_DN) |
|---|---|---|
| Path | J1 A6+B6 -> **U1 pin 1 (flow-through: in from below, out east)** -> **TP7 in-line** -> U3 pin 14 (IO20) | J1 A7+B7 -> via -> bottom under U1 -> via -> U1 pin 2 -> **TP8 in-line** -> U3 pin 13 (IO19) |
| J1 -> U3 length | 63.05 mm | 63.76 mm |
| Difference | **0.71 mm** (limit 5 mm) | |
| Width / gap | 0.254 mm / 0.246 mm (constant 0.5 mm pitch), 45-degree chamfers | same |
| Branch points (not at a pad) | **none** | 2: the J1 A7/B7 receptacle-duplicate join (inherent to USB-C) and the U1 pin-2 tap |
| Layer / reference | top layer over the solid bottom GND fill (2084.8 mm²) | the 4.5 mm bottom segment runs under U1 (top GND fill as reference) |

- **Disclosed limitation: U1 pin 2 tap.** In the TPD4E05U06 DQA pinout, D- (pin 2) sits between D+ (pin 1) and GND
  (pin 3), and the opposite column is NC. D- can therefore only be reached from the east, which leaves a 1.1 mm via-to-pad
  tap (0.8 mm beyond the pad edge). At USB 2.0 Full Speed (12 Mb/s, edges of 4 ns or more) this is far below any
  electrically significant length.
- **Impedance (approximate, IPC-2141 edge-coupled microstrip, εr 4.5, h 1.5 mm, 1 oz):**
  - The pair as built has Z0 ≈ 130 Ω and **Zdiff ≈ 153 Ω**.
  - Reaching ~90 Ω on a 1.6 mm 2-layer board would need about 1.0 mm traces at a 0.15 mm gap (≈ 96 Ω). That does not fit
    the module's 1.27 mm pad pitch or the ESD array's 0.5 mm pitch.
  - For 12 Mb/s Full Speed over 63 mm (electrically short), impedance control is not critical. The deviation from
    90 Ω is stated, not hidden. A 90 Ω design would need a 4-layer stack-up (h ≈ 0.2 mm), which DESIGN_PARAMETERS allow
    as an option.
- TP7/TP8 were moved onto the pair's final drops (Stage 3 placement change, recorded in placement.json and re-gated):
  TP7 (49.1, 33.2) rot 0 with the D+ drop through the pad, and TP8 (51.05, 36.4) rot 90 at the D- corner. Re-checked
  with usb_check.py on snap_r2b_s3o: no D+ branches, no dangling ends, lengths 63.05 / 63.76 mm.

## Power
- VBUS / VBUS_PROT / 5V / 3V3 tracks are 0.305 mm (12 mil), with 18 neck-downs to 0.254 mm (10 mil).
- Design current is 500 mA (design_profile.json).
- The GND explicit links are 0.3 mm; the GND fills are on both layers.
