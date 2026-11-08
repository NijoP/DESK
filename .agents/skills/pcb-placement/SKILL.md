---
name: pcb-placement
description: Mechanical envelope constraints, connector orientation, and thermal dissipation clusters.
triggers:
  - "placement"
  - "place"
  - "footprint"
  - "mechanical anchor"
  - "thermal cluster"
inputs:
  board_outline: dict
  components: list
  keepouts: list
outputs:
  placed_components: dict
  clearance_verified: boolean
authoritative_pipeline: M2
replay_safety: SAFE_IDEMPOTENT
---

# PCB Placement Skill

## Purpose
Governs physical placement of component footprints based on mechanical boundaries, connector interfaces, thermal zones, and routing accessibility.

## When to Use
- Establishing board outline and placing fixed mechanical connectors (USB, headers, mounting holes).
- Grouping bypass capacitors immediately adjacent to target IC power pins.
- Isolating sensitive analog blocks from switching power regulators.

## Required Inputs
- Board mechanical envelope (dimensions, mounting holes, edge keepouts).
- Component bill of materials and package footprint mappings.
- Thermal dissipation requirements for power semiconductors.

## Relevant DESK Modules
- `desk/placement.py` (or M2 placement engines).
- `desk/profile.py`: Mechanical setback and edge keepout rules.

## Required Engineering Constraints
- Locked Anchors: Edge connectors, user switches, and mounting holes must remain locked once placed.
- Decoupling Proximity: Bypass caps must be placed within $< 2\,\text{mm}$ of the targeted IC power pin with minimal loop area.
- Clearance Boundaries: Observe component-to-component and component-to-edge clearances.

## Recommended Workflow
1. Lock mechanical outline and edge connectors according to `REQUIREMENTS.md`.
2. Group components into functional clusters (Power, MCU, RF, Analog).
3. Place high-power switching regulators and thermal dissipators with adequate copper relief zones.
4. Place microcontrollers and arrange passives in signal-flow order.
5. Verify escape routing channels before locking layout.

## Validation Steps
- Execute placement verifier: `python tools/lint.py projects/<P> placement`.
- Check thermal clearances and loop areas against DRC criteria.

## Failure Conditions & Recovery
- Boundary collision: Re-orient component footprint or expand board boundary with Captain sign-off.
- Pin escape blockage: Increase component spacing to provide sufficient routing channels.

## Expected Output
- Complete component placement mapping (`x, y, rotation, layer`) satisfying mechanical and thermal invariants.

## Documentation References
- [Placement Guide](file:///docs/04_PLACEMENT.md)
