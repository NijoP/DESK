# Run 2b T+010 report (window 13:54:08-14:04:08)
Written ~14:06 wall: LATE by ~2 min (checkpoint arrived after the due time); evidence is read live, not reconstructed. T+020 (due 14:14:08) is not yet due.

## Timing (timing.json / execution.jsonl, monotonic)
- Clock start 13:54:08.472, deadline 17:39:08. Stage 1 closed STAGE_END_PASS at 14:05:21 = 11.213 min of 45 (33.8 min unspent; no borrowing). Stage 2 STAGE_START 14:05:40 (11.53 min elapsed).
- Note: the 11.2 min includes ~5.5 min of build + EasyEDA outage; log has no entries between ENV_FAILURE 13:59:35 and SAVE 14:05:21, so the reopen time is not timestamped.

## Artifacts checked
- schematic\reports\erc_report.txt (14:04:59), sch_r2b.pdf (14:04:44), sch_r2b.png (14:04:41): present, content read. LEDGER.jsonl 40 entries, L-0037..39 verify equal spec (40 parts / 43 nets), L-0040 decision. I did not visually inspect the PNG/PDF and cannot query EasyEDA.
- failures\failure_register.json exists (R2-F-001..005, run "run2b").

## Failure register review
- R2-F-001 (clear_block leaves rects, +y/-y bug): ACCEPT as a recurrence of run-1 F-005; recovery by id delete is plausible; (b) in R2-F-005 shows it is NOT fixed in DESK 2c9de1a. Not verifiable against EasyEDA by me.
- R2-F-002/R2-F-005 (orphan TEXT records, 17): root cause "CONFIRMED by .esch inspection" -- I have not inspected the .esch; ACCEPT as plausible, UNVERIFIED. The status MITIGATED is honest: the design still ships 17 stray title texts in the schematic (cosmetic, non-electrical, disclosed).
- R2-F-003 (ERC count only): ACCEPT as API limitation; the 2 warnings stay UNVERIFIED; the independent pin audit is a substitute, not an equivalent of itemized ERC.
- R2-F-004 (EasyEDA crash, suspected OOM): cause "SUSPECTED" is correctly worded. Telemetry corroborates severe memory pressure (RAM available 752-1219 MB in every sample 13:54-14:04, EasyEDA ~11 GB private) but the 1-min CSV never shows the EasyEDA process count dropping (13 procs in all samples incl. 13:59:29 and 14:00:29-14:04:30). So the crash/outage is not corroborated by telemetry (sampling gap or window-only disconnect); OOM remains a hypothesis. The register's "examiner recorded 2.1 GB" refers to attempt 1 start, before memory fell; accepted as context only.
- time_lost values (1/3/2/2.5/4) are builder estimates, UNVERIFIED.

## S1 gate status (independent)
- Four blocks built and verified spec==live netlist, 40 parts/43 nets: MET (ledger).
- ERC: 0 errors / 2 unitemized warnings: PARTIAL (error count 0 from raw API return recorded in erc_report; warnings' text UNVERIFIED; itemized audit is builder-produced from readback).
- Decoupling 5V and 3V3 10uF+1uF+100nF: builder claim; UNVERIFIED until I check block JSON (to do at T+20).
- Schematic clean/readable: PARTIAL (17 orphan title texts print above frames, disclosed).
- Saved and exported: MET on file evidence (save true per log, PDF/PNG exist).
- Overall S1 "PASS" claimed: provisionally acceptable as PASS with documented defects; final grade pending the decoupling check.
- Human interventions so far in 2b: 1 (EasyEDA reopen, R2-F-004); H-R2-001 (Captain wipe) belongs to attempt 1 / the restart decision. Disclosed warm start: same generator + R2-F-001..003 lessons + latest DESK 2c9de1a.

## Hardware (CSV, 12 samples since 13:54:08)
- CPU total mean 63.0%, max 75.7%. Free RAM min 752 MB, mostly <1.2 GB of 15.3 GB; 2305 MB only at 14:05:30. EasyEDA 13 procs ~11.1-11.4 GB private. RAM is the binding constraint. Collector PID 33504 still alive; it self-terminates ~16:32, before the 17:39 deadline, so a relaunch is required (reminder).
