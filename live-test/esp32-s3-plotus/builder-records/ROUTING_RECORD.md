# Routing record (Stage 3) — final = run6

Engine: Freerouting 2.1.0 (official jar, sha256 2c07d58f...5def, Captain-approved download H-002) on OpenJDK 23.
DSN: exported from the live board by DESK tools/route.py --dry (via benchmarks/route_wrapper.py, probe override F-013),
then rule edits in benchmarks/route_pipeline.py:
- clearance 6.1 mil default / 6.5 mil SMD (EasyEDA rule set: track-track 4, pad/via-track 6, slot 11.8; frozen criterion >= 5 mil)
- signal width 6 mil; power (VBUS, VBUS_PROT, 5V, 3V3) 10 mil;
- GND removed from the router: it is connected by the Stage 4 GND pours and stitching vias (42 GND connection items open by design);
- keep-outs: antenna (x>=66.9mm full width), 4 mounting holes, 4 USB-C shell slots (+20 mil), 2 VBUS-side slot regions.
SES import: DESK route.py Phase-15 code (benchmarks/ses_import_verify.py). EasyEDA imports every track at 5.9 mil;
power nets were then widened to 10 mil with the DESK Phase-16 mechanism (benchmarks/widen_power.py): 99/99 widened, 0 necked down.

## Results (evidence)
- Independent union-find pad-to-pad check (benchmarks/connectivity.py, run6/connectivity_independent.json): 42/43 nets fully
  connected by copper; only GND open (pour pending).
- EasyEDA DRC (drc_raw_run6_widened.json): 42 items, all "Connection Error GND"; 0 clearance, 0 short, 0 slot errors.
- Widths readback: power 99 tracks @10 mil (0.254 mm), signal 285 tracks @5.9 mil (0.150 mm).
- 384 tracks, 28 vias; 379/383 segments at 0/45/90 deg (4 short odd-angle segments).
- USB: USB_DP 67.6 mm, USB_DN 64.8 mm (sums incl. TP7/TP8 branches) -> mismatch ~2.8 mm < 5 mm. 4 vias each (duplicate-pad crossing at J1).
  Not routed as a coupled 90-ohm pair: 2-layer 1.6 mm FR-4 cannot reach 90 ohm differential at these widths (~150 ohm est.); acceptable for USB FS 12 Mbps, recorded as a deviation.
  TP7/TP8 are short T-branches on D+/D- (test-point stubs) - deviation against "no stubs", required by the frozen TP list.
- Recovery actions: F-012 engine missing, F-013 probe, F-014 supervised-run stagnation without SES, F-015 DESK DRC parser reports 0 clearance
  for 174 real errors, F-016 ESD moved from x=10.6 to 11.6 mm to free the USB-C duplicate-pad crossing.

## Run history
run1 (DESK route.py, no engine) FAIL; run2 FAIL(probe); run3 FAIL(import path); run4 BALANCED: STAGNATED 4 unrouted, no SES;
run5 PRECISION: STAGNATED 1 unrouted, no SES; direct 4-mil run: 1 unrouted, 174 clearance errors (rejected);
run2/ 6.5-mil+GND: 7 unrouted, killed (no SES); run3/ 5-mil+GND: 9 unrouted; run4/ no-GND 5-mil: 66 clearance errors + USB opens;
run5/ no-GND 6.1-mil: USB_DP/DN open (ESD too close); run6 (ESD moved): 42/43 + 0 clearance  -> ACCEPTED.
