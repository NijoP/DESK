# T+30 Report (T+30 = 05:20:28)
Written at wall 2026-11-12 ~05:21 +05:30 (about T+30.5). Data snapshot ~05:19:20, so the last ~1.5 min is not covered. T+20 was late (see that file).

## Stage status
- Stage 1 ENDED 05:18:46.642: 28.30 min of 45 (within budget; stages may not borrow, so the 16.7 unused min are not carried over). Builder result PASS.
- Stage 2 (placement, 45 min) started 05:18:56; deadline 06:03:56. At snapshot nothing placed (pcb/ empty).
- Overall elapsed ~29 min at snapshot, ~196 remaining.

## Stage 1 Must Pass gates, independent review
- Native schematic saved: only indirect evidence (desk/state/snapshot.json and netlist.net at 05:18:24; builder says saved). UNVERIFIABLE by me.
- ERC evidence: schematic/reports/erc_report.txt reads "ERC: 0 errors, 1 warnings" plus a raw line `1x {"type":"warn","count":2}`. The warning is not itemised, and "1 warning" vs "count 2" is inconsistent. Report exists in the required location; content incomplete.
- verify_all.txt: VERIFIED (38 parts, 43 nets, no single-pin nets). lint_final.txt: PASS. These are the builder's own tools; I read outputs but did not re-run them.
- Content vs 15 blocks: the build has 4 composite DESK blocks. From block specs it contains: WROOM-1-N16R8 (pin map spot-checked OK), USB-C with CC1/CC2 5.1k, 4-ch ESD TPD4E05U06, polyfuse, TVS, Schottky, AP2112K-3.3 LDO with in/out caps, EN RC + RESET, BOOT, strap resistors (GPIO3 up, 45/46 down), GPIO48 LED, power LED, test points TP1-TP8 (VBUS, 5V, 3V3, GND, EN, GPIO0, D+, D-), two 1x20 headers with 5V/3V3/GND and all GPIOs except 19/20 (on USB-C). Largely satisfies the checklist on paper.
- Items to check later, not judged failures: decoupling only at module 3V3 pin 2 (check vs criteria wording); LCSC numbers not stock-verified by me; no USB series resistors (optional).
- Overall: plausibly MET on content, but I am not marking it definitively MET because of the unresolved ERC warning and no independent save evidence.

## Captain's mid-run requirement: "neatness of schematics is important"
- Evidence: schematic/reports/sch_overview.png (05:14:51), sch_overview_v2.png, sch_blk01_02.png, sch_blk03_04.png (all 05:16:10).
- FINDING: sch_overview_v2.png, sch_blk01_02.png and sch_blk03_04.png are byte-identical (MD5 57e20cf2..., 137661 bytes). The "per-block" images are copies of the v2 overview, not block views. Only 2 distinct images exist.
- Visual inspection: v2 shows four framed blocks in a 2x2 arrangement, parts on a regular grid with net-label stubs, no overlaps or crossing wires. The earlier overview (four blocks in one row, one cut off at the left edge) was clearly less tidy, so the improvement is real. The images are low resolution; labels and reference designators are not legible, so label readability cannot be confirmed. Style is parts with net-label stubs rather than drawn connections: neat, but not a conventional readable schematic. Neatness is PARTIALLY supported, not fully verified.

## Failure register (updated 05:18:55)
7 entries F-001..F-007, all marked resolved or accepted; my review is in T+20. The register now matches ops.jsonl for Stage 1 (it was empty at T+10). F-005/F-006 are DESK bugs left unpatched.

## Hardware 05:10-05:18
- CPU 56-71 %, peak 71.3 % at 05:14:39 with a 6.5 MB/s disk read burst (probably render/export). EasyEDA ~41-43 % CPU steady; WS 2.1-2.5 GB; private memory rising 6.3 -> 6.77 GB over 10 min (watch for growth). Claude WS 1.61-1.67 GB flat. Available RAM 1.4-1.85 GB (vs 0.58 GB trough at 05:00). C: free 162.47 GB. Net bursts to 323 KB/s. GPU idle 0 %/0 MB/46-49 C (expected, inference is remote).
- Local bottleneck: EasyEDA (memory and a constant ~41 % CPU). It is the only component linked to failures (timeouts). Model latency is remote and not measurable from this data.
- Telemetry PID 33512 alive at 05:19. Frozen-file hashes still match.
