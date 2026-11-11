# Placement-Routing Co-optimisation

**Module:** `desk/placement_refine.py` (`PlacementRefiner`). **Tests:** `tests/test_dense_intelligence.py::TestPlacementRefiner`. **Inputs:** PCB dump, `placement.json`, optional `DesignProfile`. **Output:** `RefinementResult` with ranked `MoveProposal`s; `apply_to_plan()` writes `placement.json` only, with an explicit authoriser recorded. The live board changes only when the operator runs `tools/pcb_place.py`.

## Problem

`PlacementAcceptanceGate` accepted the WATCH placement at routability score 0.60 with 355 ratsnest crossings; the gate cannot fail on routability and no refinement loop existed (routing audit §4). A mechanically valid placement produced a routing problem the engine could not finish.

## Workflow

1. Understand the board: `DensePCBIntelligence` on the current dump (hotspots, crossings, wirelength).
2. Immovable anchors: connectors, switches, microphones, modules, antennas, battery pads, ICs, mounting holes, anything in `placement.json` `locked`, `roles.connectors`, or a keep-out `allow` list (`LOCKED_RX`, `IC_RX`).
3. Functional constraints: every 2-pad capacitor between a power net and GND is bound to the nearest IC pad on that power net; a proposal that moves it beyond `decap_max_mm` (2.0 mm) is rejected.
4. Hard geometry: inside the board with 0.3 mm edge clearance, outside keep-outs for its side, no body overlap (0.25 mm gap).
5. Candidates: for each movable passive (R, C, L, FB), ±0.5 mm and ±1.0 mm in four directions and a 90° rotation. Parts inside hotspot regions are tried first.
6. Evaluate each candidate with the incremental engine update; objective
   `J = 100 Σ max(0, score − 0.6) + 2 × crossings + wirelength_mm / 10`.
7. Accept the best improving move (≥ 1.0 objective units), repeat up to `max_moves` (default 5).
8. Report proposals with before/after hotspot cells and crossings and a one-line reason.

What is never done: moving locked parts, changing identities, footprints or pin-to-net mappings, altering RF/crystal/feedback placements (ICs and RF role refs are locked), or touching EasyEDA.

## Measured

| Board | Moves accepted | Objective before → after | Time |
|---|---:|---|---:|
| WATCH (repo dump) | 3 | see `tools/dense_benchmarks.py` output | 12.6 s |
| dense_sensor (synthetic) | 3 | improves | 4.7 s |
| mcu_2layer_compact (synthetic) | 3 | improves | 0.4 s |

Each candidate currently rebuilds the board model and the net graph (the incremental path reuses demand bookkeeping but not the spatial index), which is why WATCH takes 12 s for roughly 500 candidate evaluations. PERF-08 (reuse the spatial index across candidates) is the next optimisation; correctness is already covered by the equivalence test.

## Acceptance for Stage 2 of the 225-minute programme

A placement is accepted when the mechanical and electrical placement checks pass **and** the dense-board report has no overloaded region whose cause is placement-related (layer scarcity / pad-blocked / keep-out crossing) after refinement, or the operator has authorised the remaining ones.
