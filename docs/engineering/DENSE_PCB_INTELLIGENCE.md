# Dense PCB Intelligence

**Module:** `desk/routing/density.py` (`DensePCBIntelligence`, `DenseBoardReport`). **Tests:** `tests/test_dense_intelligence.py`. **Benchmark:** `tools/dense_benchmarks.py`. **Consumers:** `tools/route.py` (priority classes, plane nets, via costs to the engine; `state/route/dense_analysis.json`), `desk/placement_refine.py`, Mission Control payload via `DenseBoardReport.to_mission_control()`.

## Why

Before this engine, DESK's escape, congestion, priority and strategy modules were computed and discarded: nothing they produced changed what Freerouting did (routing audit, `docs/product_assessment/HARDWARE_AND_PCB_ENGINEERING_ASSESSMENT.md` and the routing pipeline audit). The board was handed to the engine as a flat list of nets with identical rules, and the engine burned its whole timeout on the dense regions.

## Model

- **Grid.** Square cells, 25-50 mil (adaptive: min board dimension / 30). WATCH (30 × 45 mm) uses 39 mil cells, 31 × 46.
- **Supply** per routable signal layer = cell width × (1 − blocked fraction). Blocked fraction comes from pad bodies plus clearance (SMD on their layer, through-hole on all layers) and keep-outs. Plane layers (declared in `placement.json`) are not routable for signals.
- **Demand** = Σ over ratsnest (MST) edges of (track width + clearance) for every cell the edge's two Manhattan L-routes cross, each L weighted 0.5. Track width per net comes from the design profile when present, else 5 mil (10 mil for power-pattern nets). Plane nets add no corridor demand.
- **Score** = demand / Σ supply. < 0.5 comfortable, 0.5-0.8 busy, ≥ 0.8 hotspot, ≥ 1.0 overloaded. A fully blocked cell with demand is capped at 5.0 and reported as "keep-out or pad crossing (detour required)".
- **Crossings** are attributed to cells so a region's crossing count is measured, not guessed.
- **Escape** uses `PadEscapeEngine` for every pad (cached); fine pitch = pitch ≤ 0.65 mm or a RESTRICTED/CRITICAL/NO_LEGAL_ESCAPE classification.

## Outputs per hotspot region (8-connected hotspot cells)

bbox (mm), max and mean score, pads, fine-pitch pads, nets, crossings, free layers, preferred escape directions (from the legal directions of the fine-pitch pads inside), power nets passing, **measured causes** and a **recommended strategy**:

| Cause (measured) | Strategy |
|---|---|
| ≥ 6 fine-pitch pads | ESCAPE_FIRST (stage-2 scheduling, neckdown to pad width, escape toward the open side) |
| power demand ≥ 30 % of the region's demand | POWER_TO_POLYGON (polygon or plane tap with via arrays; see power distribution) |
| ≥ 4 crossings | layer split H/V or corridor reservation |
| ≤ 1 free layer, or mean blocked ≥ 0.6 | PLACEMENT_REFINE_THEN_ROUTE (minimal passive moves) |
| ratsnest through a keep-out | reserve the neighbouring corridor (detour) |

Corridors: maximal runs (≥ 3 cells) of quiet, unblocked cells, ranked by adjacency to hotspots; these are the channels to reserve for constrained nets.

Priority order: escape difficulty × 2 + hotspot involvement × 5 + differential pair + power + terminal count. The top third is passed to Freerouting as `router.autorouter.priority_net_classes` (EasyEDA exports one DSN class per net, so class names are net names).

## Incremental use

`update_components({ref: new_record})` removes the moved parts' pads and their nets' demand contributions, re-adds them and rescores only the touched cells. Equivalence with a full rebuild is tested (`test_incremental_update_matches_rebuild`). The placement refiner relies on it.

## Measured results (2026-11-11, `tools/dense_benchmarks.py --runs 3`)

| Board | Kind | Parts | Pads | Nets | Crossings | Congestion | Overloaded | Regions | Analysis ms (P50) | Top cause |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| WATCH (repo dump) | REAL-BOARD | 87 | 313 | 60 | 212 | 0.62 | 11 | 16 | 83 | power trunk through signal corridor |
| WATCH (live read, 18:05Z) | REAL-BOARD | 87 | 313 | 60 | 233 | 0.69 | 11 | 18 | 43 | power trunk through signal corridor |
| esp32_4layer | SYNTHETIC | 44 | 187 | 57 | 352 | 2.53 | 86 | 10 | 25 | keep-out crossing |
| qfn_fine_pitch | SYNTHETIC | 14 | 105 | 47 | 157 | 1.27 | 48 | 4 | 32 | fine-pitch escape |
| dense_sensor | SYNTHETIC | 28 | 135 | 12 | 172 | 1.47 | 64 | 15 | 42 | fine-pitch escape |
| multi_terminal | SYNTHETIC | 17 | 149 | 14 | 502 | 1.21 | 47 | 14 | 47 | fine-pitch escape |
| mcu_2layer_compact | SYNTHETIC | 18 | 83 | 28 | 69 | 0.76 | 24 | 11 | 12 | fine-pitch escape |

Synthetic rows show algorithm behaviour only. On the real board the engine's finding, seven of the top ten regions caused by VBUS / VBUS_BOOST / VSYS / VBAT trunks competing with signals on the two routable layers, is consistent with the recorded Freerouting run that could not get below 7 unrouted.

## Limitations

- Scores are relative indices calibrated on one real board and ten synthetic boards; they are not predictions of Freerouting's unrouted count until validated on more datasets (QA-01).
- Demand uses L-routes, not real paths; detours around keep-outs are flagged, not modelled.
- Via accessibility is captured through the escape engine's via candidates only.
- Thermal constraints are not part of the score (placement rules handle heat spacing).
