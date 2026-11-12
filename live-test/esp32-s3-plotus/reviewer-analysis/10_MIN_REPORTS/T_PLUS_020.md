# T+20 Report (clock 04:50:28 +05:30; T+20 = 05:10:28)
**LATE. Written retroactively at wall 2026-11-12 ~05:21 +05:30 (about T+30).** My timer fired at 05:10:38 but my run had already been ended by a handback, so I was not running; I was re-engaged by the coordinator's checkpoint at ~05:19. This is a reconstruction from file mtimes and logs, not live observation. Hardware numbers come from the CSV, which kept running independently.

## State at T+20 (reconstructed)
- Stage 1 running (elapsed 20 of 45 min). Log trail: F-001/F-002 at 05:00:18; retry of block 01 timed out again 05:02:46 (F-003); recovery 05:03-05:07. gen_blocks.py and block specs regenerated 05:07:17 (new LCSC uuids). First verify run 05:07:53 failed (logs/verify_all_1.txt) -> F-004 (46 errors, power nets merged into 3V3). sheet_geometry_1.json at 05:08:49 is the readback used to find orphan wires. I did not independently time each rebuild.

## Failure review (register read at 05:19)
- F-001 (U1 TPD4E05U06 create hang, 120 s timeout): builder claims CONFIRMED stale library uuid, isolated by per-part create timing. PARTLY ACCEPTED: switching to the re-resolved uuid (C125795) and the rebuild succeeding is consistent with that, and it explains why the retry (F-003) timed out identically. I did not observe the timing isolation itself. The "contributing: memory pressure" claim is supported only as correlation (RAM available 579-731 MB at 04:59-05:02, EasyEDA WS 2.6-3.0 GB). The retry also timed out at 731 MB, and the fix worked later at 1.5 GB, so I cannot separate the two causes; the uuid cause has the stronger evidence.
- F-002 labelled UNCONFIRMED by the builder: honest label, accept as unconfirmed.
- F-004 (orphan wires from failed builds joined power nets): plausible and consistent with the 46-error verify output and the geometry readback; not re-derived by me. Provisionally accepted.
- F-005/F-006: DESK tool bugs, worked around, not patched in source. F-007 netlist export timeout: minor; desk/state/netlist.net (05:18) exists.
- Builder-reported time lost sums to about 21.5 of 28.3 min of Stage 1 (self-reported; my wall-clock reading is consistent: first block built 04:59, verified only about 05:10-05:14).

## Acceptance at T+20: not yet verifiable; see T+30 for the end state.

## Hardware 05:00-05:10
- Overall CPU 51-68 %. EasyEDA constant ~40-42 %. Claude Code 0.8-1.9 %. Python 0 % (60 s sampling misses short bursts).
- RAM available 579-731 MB until 05:02, then 1.5-1.85 GB from 05:03 (EasyEDA WS fell 2.6 -> 2.1-2.4 GB). The pressure episode coincided with the build timeouts. Claude WS ~1.6-1.75 GB, no leak visible.
- Disk read bursts to 2.2 MB/s, net to 95 KB/s. GPU 0 %/0 MB/47-49 C (idle; expected with remote inference). C: free 162.5-162.9 GB.
