# Failure register review (builder-records/failure_register.json)
| ID | Root cause correct? | Recovery honest? | Class |
|---|---|---|---|
| F-001 multiple EasyEDA windows | Yes | Yes, bound to window, no wrong mutation | EasyEDA/environment |
| F-002 window IDs rotated | Yes | Yes, fail-closed rebind | EasyEDA limitation |
| F-003 domains arg parsing | Yes | Yes; fix plus regression test present | DESK bug |
| F-004 schematic->PCB import blocked | Yes; known earlier limitation | Marked recovered:false; the human Apply later happened and was counted as an intervention | EasyEDA limitation / DESK gap |
| F-005 passives stacked, 277 errors | Yes | Fixed in pcb_place.py; no unit test | DESK limitation |
| F-006 POSIX jar path | Yes | Yes, but the same fix poured fills pre-route, which likely caused F-010 | Builder error |
| F-007 Freerouting probe timeout | Yes | Fix plus 3 tests; slightly loosens the probe (banner on timeout = compatible) | DESK limitation |
| F-008 hot loop/decap gate not evaluating | Yes (from my interim review) | Partly fixed; decap still open and recorded as recovered:false | DESK gate defect plus builder placement |
| F-009 profile compiler ignores mechanical/stackup | Yes | Manual patch acceptable in intent but caused F-011 | DESK limitation |
| F-010 attempt 3 routing 0 passes | Plausible (fills); unproven | Honest | Builder error (probable) |
| F-011 profile loader TypeError | Yes | Fixed correctly | Builder error |
| F-012 router throughput | Yes (freerouting.log) | Honest; ceiling respected | Router performance / environment |

Missing from the register: mounting holes not creatable (only in FAB notes); DRC count discrepancy 349 vs 1.
