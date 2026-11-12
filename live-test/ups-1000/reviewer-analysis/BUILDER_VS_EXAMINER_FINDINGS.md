# Builder claim vs examiner
| Claim | Examiner |
|---|---|
| S1 PASS | AGREE (verify, lint, ERC raw files). Open design-quality majors remain. |
| S2 PASS | AGREE with caveat: placement gate OK but decap rule unmet and hot-loop gate advisory; one probable human Apply intervention. |
| S3 FAIL | AGREE. |
| Attempt 3 "crash" caused by builder pre-pouring fills | PARTLY: route_run3.txt shows a 420 s TIMEOUT with 0 passes, not a crash. The fills cause is plausible (attempt 5 with declared planes ran 5 passes) but unproven. |
| Attempt 4 refusal due to builder profile patch | AGREE (route_run4.txt: profile not loaded, STOP). Fail-closed behaviour worked. |
| Attempt 5: 106->70 then timeout | AGREE (freerouting.log: 70 unrouted after pass 5; passes 3 min and 2 min on some). Throughput/environment limit. |
| Stopped at retry ceiling | AGREE with AGENTS.md; about 105 min of budget unused. Alternatives (power polygons, longer budget) correctly left to the Captain. |
| S4 DRC 349, all unconnected-pad class | AGREE (drc_s4_unrouted.json). Release gate printed 1 violation: unreconciled. |
| S5 FAIL, nothing exported, skip flag unused | AGREE. |
| One human intervention | AGREE; plausible and honestly counted (B-001, EasyEDA/DESK limitation). |
| No gate weakened | AGREE; diffs reviewed in interim, 721 tests OK on my rerun. |
| Thermal margin 92 K | Arithmetic OK; assumptions (40 ns tr+tf, 50 K/W) unmeasured; Qrr omitted. |
| Interim findings addressed | Only hot loop and gate loop partially; decap, TVS, OV, hysteresis, reverse polarity remain open. |
