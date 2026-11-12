# Run 2b T+060 report (window 14:44:08-14:54:08; evidence cut 14:51:47, written early, so not late)

## Timing (timing.json / execution.jsonl, monotonic)
- Elapsed at cut: 57.6 min of 225. Stage 1 PASS 11.213/45, Stage 2 PASS 12.304/45, Stage 3 STAGE_END_PASS 14:51:06 at 33.041/90. No stage borrowed time. Stage 4 (30 min) not yet logged as started.
- Human interventions to date: 1 in 2b stage 2 (Import Apply), 1 EasyEDA reopen (R2-F-004). Attempt-1 H-R2-001 (Captain wipe) caused the restart.

## Failure register review (R2-F-008..011 new)
- R2-F-008 pad geometry (POLYGON pad double-rotated): ACCEPT root cause (readback-confirmed, regression test named); fix is on an UNCOMMITTED local DESK branch.
- R2-F-009 Freerouting topology: ACCEPT. Note it means routing was not fully autorouter-driven; USB hand-routed, GND by pour/links. Disclose.
- R2-F-010 SES width override: ACCEPT as an unresolved tool defect worked around.
- R2-F-011 TP relocation: ACCEPT; DRC files show the 0 mil pad-track errors before the fix (drc_s3_5/6/7 non-empty 14:44-14:48), then [] at 14:49:57.
- time_lost figures are builder estimates, UNVERIFIED.

## Artifact checks (content read)
- drc_s3_8.json (14:49:57) content is exactly "[]": 0 DRC violations from EasyEDA, raw. MET on evidence. I cannot see which DRC rules/categories were enabled (a bare [] can hide disabled rules); UNVERIFIED breadth.
- connectivity_report.json: "43/43 nets fully connected (100.0%). Partially routed 0, Unrouted 0, Illegal 0". Note the builder's tool, not EasyEDA's.
- usb_pair_check.json: D+ 63.05 mm, D- 63.76 mm, diff 0.71 mm (<5 mm: MET). D+ has no branch nodes. D- has two vias, each with 3 connections ((9.2,21.849) and (13.101,21.501)); the builder discloses the J1 join via and the U1-pin-2 tap via. A tap via with a third connection is a possible stub: its length is not in the JSON, so "No stubs" is PARTIAL pending a stub-length number. Also widths 0.15 mm and 0.254 mm on the pair (two widths), spacing/impedance (90 ohm) and GND-reference are not evidenced in this JSON: UNVERIFIED.
- ROUTING_RECORD.md (14:51:00, 5.1 KB) and routing passes r2b_run1/run2 exist: Routing Record Saved MET (content not graded in depth).

## S3 Must Pass gate status
- All required nets physically connected: MET by builder verifier (43/43) + raw JSON; EasyEDA's own connectivity not examined by me.
- No unintended shorts / zero DRC shorts: MET (DRC []), breadth UNVERIFIED.
- No new critical DRC (clearance/width/via): MET per DRC [].
- Correct via/layer transitions: PARTIAL/UNVERIFIED (D- via count and topology disclosed).
- USB constraints: length match MET; spacing/90 ohm UNVERIFIED; GND reference UNVERIFIED (S4 pour); no stubs PARTIAL as above.
- Physical pad-to-pad verification 100%: MET (builder verifier).
- Routing record saved: MET.
- Should-pass: power traces 12 mil = 0.305 mm (>=0.3: MET per builder); teardrops, acute angles UNVERIFIED.
- S3 overall: PASS claim acceptable provisionally; the strict-GND single group claim (gnd_links.py, benchmarks\snap_r2b_s3o.json) is pre-pour, so GND connectivity relies on fills and links; I did not re-run it.

## Hardware (CSV)
- 14:44-14:51: CPU mean 51.9%, max 55.7%, min free RAM 1348 MB (recovered from earlier lows 553-944 MB). Whole run so far: CPU mean ~57%, free RAM min 553 MB at 14:14-14:24. EasyEDA private ~11.5-11.9 GB, Freerouting java up to 1.31 GB. Collector PID 33504 still running; self-terminates ~16:32, run ends 17:39: needs relaunch.
