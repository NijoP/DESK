# Run 2b T+030 report

RETROACTIVE and LATE: the coordinator missed the T+20..T+50 checkpoints and I was only re-invoked at T+57 (14:51). This report is reconstructed after the fact from file mtimes, execution.jsonl, drc_s3_*.json names and the hardware CSV, not observed live. Content as of the window below only where file timestamps prove it.

Window 14:14:08-14:24:08.
- Stage 2 STAGE_END_PASS 14:17:58 (12.304 min of 45; 40/40 placed, outline 74x44 mm rounded 2 mm R, 4x 3.2 mm NPTH, pcb_check gate OK, 0 errors, routability 0.88, bypass caps 0.85-0.88 mm from U3 pin 2, antenna keep-out clean per builder). Gate numbers come from the builder's log; placement files exist under pcb\placement (not re-run by me): UNVERIFIED independently. Stage 3 STAGE_START 14:18:04.
- R2-F-007 (outline create API/orientation mistakes, 3 min lost) logged 14:16: plausible, recovery shown by outcome, "DESK fix pending".
- Freerouting run 1: r2b_run1 files 14:19:16-14:22:20 (fr.log 84.7 KB, route.ses). u1_escape/plan_gnd_links 14:25.
- Hardware: CPU mean 58.2%, max 71.3%; min free RAM 553 MB (lowest of run); java (Freerouting) WS up to 1.1 GB.
