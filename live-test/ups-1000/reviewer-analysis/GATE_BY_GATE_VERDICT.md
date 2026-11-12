# Gate by gate (raw files checked)
| Gate | Verdict | Evidence |
|---|---|---|
| Gate R (LV prototype) | PASS (LV scope); system HV Gate R explicitly NOT passed (M-01..M-13) | projects/UPS_1000/REQUIREMENTS.md, stage_metrics.json S1 note |
| Gate B | PASS with 10 open verification items V-01..V-10 | projects/UPS_1000/BOM_SELECTION.md |
| lint --final | PASS (1 false-positive WARN on BST cap) | builder-records/lint_final_s1.txt |
| Offline/EasyEDA ERC | PASS, 0 errors, 1 warning-type (count 5) | erc_report_s1.txt; release_attempt_revA_2.txt |
| verify all | PASS VERIFIED (123 parts, 58 nets) | verify_all_s1.txt, verify_all_s5.txt |
| Placement gate | PASS as printed, but weak: decap 2 mm rule not evaluated/not met; Q1-R24 0.4 mm; 97 hotspot cells; hot-loop rule advisory | placement_check_final.txt, failure_register F-008 |
| Schematic<->PCB nets/designators | PASS designators (missing/extra none); net connectivity not provable without copper | release_attempt_revA_2.txt |
| Routing/connectivity | FAIL: 0 connections routed on live board; attempt 5 went 106->70 unrouted, timed out (445 s vs 300 s budget) | route_run3..5.txt, freerouting.log |
| DRC | FAIL: 349 violations (unconnected SMD pads), 0 clearance, 0 shorts. Release gate reported "1 violations": different counting, unreconciled | drc_s4_unrouted.txt/.json, release_attempt_revA_2.txt |
| Copper | FAIL/ABSENT: 0 fills | stage_metrics S3, state/copper_fills.json |
| Electrical verification (post-layout) | NOT PERFORMED; conductor sizing is calc only | conductor_sizing.txt |
| Thermal | CALC ONLY, engine rule UNSUPPORTED, no measurement; Tj 58 C for Q1/Q2 plausible | manufacturing-revA/THERMAL_ASSESSMENT.md |
| Safety/HV gate | NOT APPLICABLE / correctly blocked; no HV claimed | FAB_AND_ASSEMBLY_NOTES.md, REQUIREMENTS s11-12 |
| Release gates | CORRECTLY BLOCKED (attempt 1 stale verify; attempt 2 live DRC); nothing exported; skip flag unused | release_attempt_revA.txt, _2.txt |
| Test suite | PASS: examiner rerun 721 tests OK, skipped=9, env vars unset | own run; tests_after_changes3.txt |
| Evidence manifest | 68/71 hashes match; 3 mismatches are live logs appended later (execution.jsonl, progress.json, stage_metrics.json) | EVIDENCE_MANIFEST.json |
