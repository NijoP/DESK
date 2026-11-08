---
name: component-selection
description: Procedural workflow for component search, footprint assignment, electrical derating, and BOM verification.
triggers:
  - "component"
  - "part"
  - "footprint"
  - "package"
  - "bom"
  - "datasheet"
  - "lcsc"
inputs:
  component_specs: dict
  profile: DesignProfile
outputs:
  selected_parts: list
  derating_status: dict
  bom_ready: boolean
authoritative_pipeline: M1
replay_safety: SAFE_READ
---

# Component Selection Skill

## Purpose
Selects components matching voltage, current, thermal, frequency, and manufacturing footprint criteria.

## Procedural Execution Checklist

1. **Derating Evaluation**:
   - Apply 50% voltage derating for ceramic capacitors (especially MLCCs subject to DC bias capacitance loss).
   - Apply 25% current and power derating for power inductors, MOSFETs, and diodes.
2. **Footprint & Package Validation**:
   - Ensure surface-mount packages align with manufacturing capabilities (e.g., minimum 0402 for standard assembly, 0201 only if high-density HDI is specified).
   - Ensure thermal pad footprint connects to correct thermal via array.
3. **BOM Verification**:
   - Verify active availability and manufacturer part numbers (MPN) or LCSC part codes.
   - Attach selected package geometry to component database.
