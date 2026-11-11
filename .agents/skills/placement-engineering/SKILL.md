---
name: placement-engineering
description: Procedural workflow for PCB component placement, thermal domain separation, and decoupling proximity.
triggers:
  - "place"
  - "placement"
  - "cluster"
  - "thermal"
  - "decoupling"
  - "orientation"
inputs:
  components: list
  board_outline: dict
  profile: DesignProfile
outputs:
  placed_components: list
  violations: list
authoritative_pipeline: M2
replay_safety: SAFE_IDEMPOTENT
---

# Placement Engineering Skill

## Purpose
Directs deterministic component placement respecting functional domain isolation, thermal zones, and RF keepouts.

## Procedural Execution Checklist

1. **Domain Partitioning**:
   - Isolate Power Stage (MOSFETs, inductors, bulk caps) from Sensitive Analog / MCU.
   - Maintain minimum 3.0 mm physical creepage for high-voltage domains (> 60 V).
2. **Decoupling Capacitor Placement**:
   - Place high-frequency MLCC capacitors ($0.1\,\mu\text{F}$) within 1.5 mm of target IC power pins.
   - Ensure the capacitor pad connects directly to IC pin before hitting any via to ground/power planes.
3. **Orientation & DFM**:
   - Align passive components along standard 0°/90° orthogonal axes for automated pick-and-place nozzles.
   - Enforce courtyard clearances to prevent component collisions.
4. **Invoke M2 Placement Engine**:
   - Generate with `PlacementIntelligenceEngine.generate_hierarchical_placement(reqs, blocks, keepouts)` (tools/pcb_place.py --auto), check with `desk.placement.check(dump, plan, blocks, profile)`, then refine routability with `desk.placement_refine.PlacementRefiner(dump, plan).refine()` (proposals only; apply needs authorisation).
