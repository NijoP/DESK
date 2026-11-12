# UPS_1000 — Why routing failed (post-benchmark investigation)

The benchmark ended at 78.22 min with S3 FAIL. Afterwards the Captain asked for routing to be retried. Attempt 6 (PRECISION, `--passes 16`) also failed: 103 → 90 unrouted after 3 passes, chunk TIMEOUT at 420 s, no SES. The evidence below comes from `projects/UPS_1000/state/route/` (freerouting.log, desk_route_tuned.dsn, dense_analysis.json) and `builder-records/route_run3..6.txt`.

## Root blocker: creepage used as router clearance on fine-pitch IC pins
The DSN sent to Freerouting gives these net classes a **49.21–51.18 mil (1.25–1.30 mm)** clearance to every other net:

`VBUS, VIN_RAW, SW, PHASE, SW12, RIP12, VOUT_EXT` (49.21 mil) and `GH, BST, BST12` (51.18 mil).

* **Source of the value.** It comes from `desk/profile.py derive_clearance_mil` → `desk/ipc.required_spacing_mil`, which takes max(IPC-2221B clearance, IEC 60664-1 creepage). The profile sets PD2 and material group IIIa, so creepage for 58.4–70.4 V (the 63/80 V table rows) is 1.25–1.30 mm. IPC-2221B B2 clearance alone is **0.6 mm**.
* **Why it cannot be met.** Several of these nets terminate on ICs with a 1.27 mm pin pitch: LM5164 (SW12, BST12, RIP12) and UCC21520 (GH, BST, SW). On those packages the copper gap between neighbouring pads is about 0.6–0.7 mm, which is smaller than the rule, so the pads violate it before any trace is drawn. `dense_analysis.json` agrees: **64 pads have NO_LEGAL_ESCAPE_FOUND** and 58 more are RESTRICTED.
* **Effect on the router.** Freerouting retries these impossible connections on every pass with rip-up and reroute. That makes each pass very slow; attempt 6's freerouting.log shows:
  * Pass 1: **4 min 24.9 s** (103 unrouted)
  * Pass 2: 50.3 s (95 unrouted)
  * Pass 3: 50.1 s (90 unrouted)
* **Doubt about the creepage table itself.** Up to 40 V, DESK's PD2 rows use the printed-wiring value (0.04 mm), but from 50 V up they use the much larger general-material values (0.60–1.25 mm). The table is already marked UNVERIFIED in DESK (`verified_against_standard=False`). It must be checked against IEC 60664-1 Table F.4 before it is used as a hard rule.
* **Requirement question.** Rev A is a SELV ≤ 60 V functional board with no safety insulation (REQUIREMENTS.md). Whether creepage applies to functional spacing on this board is a requirements decision; it is not a router setting.

## Contributing blocker: chunked execution throws away all work on slow boards
`desk/routing/pipeline.py` runs the router in chunks with these settings:
* `chunk_timeout_sec = min(300, mode timeout)`: every mode, including PRECISION, is capped at 300 s per chunk.
* `chunk_passes = max(4, …)`: at least 4 passes per chunk.

A chunk that hits its timeout writes **no SES**, and the orchestrator discards it. When one pass takes longer than about 75 s, no chunk can ever finish, so every attempt imports nothing, whatever the mode or budget. This happened in attempts 5 and 6.

DESK should either adapt the chunk size to the measured pass time or recover the partial SES. This is a DESK defect.

## Secondary factors
* **Effectively 2 signal layers.** Inner1 and Inner2 are both GND planes (a ledger deviation from the client's "L3 DC distribution"). The router therefore has only Top and Bottom for 123 parts and 58 nets, and DESK's density model counts all 4 layers as routable.
* **Placement hotspots** (dense_analysis):
  * H1/H2: J2/J3 sit at x = 157.2 mm on the right edge, with blocked escape and the 3V3 trunk crossing the signal corridor.
  * H4: the UCC21520 barrier keep-out.
  * H5: J5 at the left edge, with the VBUS trunk crossing.
  * In total: 112 overloaded cells and 151 ratsnest crossings.
* **Builder errors in the benchmark run:**
  * F-010: GND fills poured before routing broke the DSN.
  * F-011: an invalid hand-edit to design_profile.json stopped the profile from loading.

## Fix options (clearance changes need Captain sign-off, AGENTS.md §A)
1. **Correct the spacing requirement** (recommended).
   * Use IPC-2221B B2 clearance (0.6 mm, 23.6 mil) for the ≤ 70 V functional nets, and record a ledger decision that rev A is a functional-insulation SELV board.
   * Or verify the IEC 60664-1 printed-wiring column and use that value.
   * Even 0.6 mm cannot be met between adjacent 1.27 mm-pitch IC pins, so the DSN must apply the high-voltage rule net-to-net away from the pins, keeping the fabricator minimum at the IC pads.
2. **Fix the chunking defect.** Size each chunk from the measured pass time, and use the PRECISION budget per chunk.
3. **Then** pour VBUS/SW/PHASE as polygons rather than routed trunks (the dense analysis recommends POWER_TO_POLYGON), and move the decoupling capacitors and edge connectors before rerouting.
