---
name: copper-ground-engineering
description: Procedural workflow for ground planes, power polygons, thermal reliefs, keepouts, and via stitching.
triggers:
  - "copper"
  - "pour"
  - "plane"
  - "ground"
  - "gnd"
  - "polygon"
  - "thermal relief"
  - "stitch"
inputs:
  net_name: string
  layer: string
  boundary_polygon: list
  profile: DesignProfile
outputs:
  zone_id: string
  poured_area_mm2: float
  islands_removed: integer
authoritative_pipeline: M4
replay_safety: SAFE_IDEMPOTENT
---

# Copper & Ground Engineering Skill

## Purpose
Synthesizes uninterrupted ground return planes, power distribution polygons, and thermal spoke connections.

## Procedural Execution Checklist

1. **Continuous Reference Ground Plane**:
   - Establish an uninterrupted ground plane on the layer directly adjacent to high-speed/RF signals.
   - Avoid routing through the reference plane. If a split is mandatory, bridge return paths with local stitching capacitors.
2. **Thermal Relief vs Solid Connections**:
   - Hand-soldered or through-hole pins: 4-spoke thermal relief (spoke width calculated from net current).
   - SMT power/thermal pads and grounding vias: Solid pour connection for minimum thermal and electrical resistance.
3. **Island Pruning & Keepout Enforcements**:
   - Invoke `desk.copper.detect_copper_islands()` and prune floating, unreferenced copper islands.
   - Respect route keepout polygons and board edge clearance ($\ge 0.5\,\text{mm}$).
4. **Invoke M4 Copper Engine**:
   - Execute `desk.copper.create_copper_zone(...)`.
