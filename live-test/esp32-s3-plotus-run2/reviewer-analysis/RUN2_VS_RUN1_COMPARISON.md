# Run 2 (run 2b) vs Run 1 comparison
Run 2b is a WARM START (run 1 generator, tooling and lessons carried over; DESK fast-forwarded to 2c9de1a; attempt-1 failures carried in). Time and failure counts are therefore NOT like-for-like. Run 1 data is from its examiner's final evaluation (verdict FAIL, 50/100); I did not re-audit run 1's files.

| Dimension | Run 1 | Run 2b | Note |
|---|---|---|---|
| Verdict | FAIL (50/100) | PARTIAL PASS (81/100) | same rubric |
| Electrical correctness | Stage 4 closed with 5 GND Connection Errors; floating USB ESD array, CC2 pull-down and EN capacitor | DRC 0, 43/43 with fills, strict GND = 1 group before stitching; 2 ERC warnings unread | the run 1 failure mode (via-to-fill joins) did not recur; evidence is builder tooling + raw DRC JSON |
| PCB quality | not releasable | rounded 74x44, solid GND pours both layers, thermals, 35+6 stitching vias, antenna keep-out 0 mm2 | no teardrops; static pours |
| Placement | Stage 2 passed with deviation (hard gates not fully met) | gate OK, 40/40, routability 0.88, caps 0.85-0.88 mm from U3 pin 2 | one Captain Import Apply |
| Routing | GND deferred to copper stage; passed with deviation | GND routed and verified inside Stage 3; DRC 0, 43/43; hybrid routing (hand USB, Freerouting, fills/links) | USB Zdiff ~153 ohm (disclosed), D- tap |
| Power / ground | GND connectivity failed in S4 | 12 mil power (0.305 mm) with 18 neck-downs; GND pours + stitching, DRC 0 | |
| Manufacturing readiness | Stage 5 NOT STARTED | Full package: Gerber+drills, BOM with LCSC on 18/18 lines, CPL, PDF, .epro (hashes verified) | Gerbers not opened by me; no SVG |
| Time | 102.83 min total (S1 28.30, S2 11.92, S3 38.09, S4 23.28, S5 0) | 66.705 min (11.21, 12.30, 33.04, 3.08, 6.36) | warm start; not comparable; attempt 1 (~101 min wall, aborted) excluded |
| Failures logged | F-001..F-0xx (many, incl. long losses of ~12-21 min each) | R2-F-001..012 (5 from attempt 1/carried) | several of run 1's DESK bugs recurred (clear_block rects) or new ones found |
| Recovery | one stage failure ended the run | R2-F-004 crash recovered by Captain reopen; all others recovered in-session | |
| Human intervention | Router/GUI related (e.g. H-002) | 2 in 2b (EasyEDA reopen, Import Apply) + Captain wipe in attempt 1 that forced the restart | the restart cost ~89 min of wall time, not counted on the 2b clock |
| Process honesty | disclosed failure | disclosed defects (ghost texts, impedance, post-end change); retroactive checkpoints | |
| Hardware | see run 1 examiner | CPU mean 57%, free RAM min 553 MB, EasyEDA private ~11-12 GB | memory-bound; likely the cause of the crash (unproven) |
