---
name: high-current-design
description: Procedural workflow for power electronics, MOSFET switching loops, heavy copper traces, and multi-via stitched arrays.
triggers:
  - "high current"
  - "power trace"
  - "ampere"
  - "copper weight"
  - "mosfet"
  - "buck"
inputs:
  net_names: list
  peak_current_a: float
  profile: DesignProfile
outputs:
  power_polygons: list
  stitched_vias: list
  thermal_margin: float
authoritative_pipeline: M3/M4
replay_safety: SAFE_IDEMPOTENT
---

# High Current Design Skill

## Purpose
Directs high-current distribution, switching node ($SW$) loop reduction, thermal dissipation, and parallel layer routing.

## Procedural Execution Checklist

1. **Minimise High di/dt Loop Area**:
   - The critical high-frequency loop (Input bulk capacitor $\rightarrow$ High-side MOSFET $\rightarrow$ Low-side MOSFET/Diode $\rightarrow$ Ground return) must have the smallest physical area possible.
2. **Current Carrying Capacity**:
   - For currents $> 3\,\text{A}$, use dedicated polygonal copper pours or multiple layers stitched with arrays of vias.
   - Calculate via current capacity (typically $1.5\,\text{A}$ per $0.3\,\text{mm}$ hole diameter via on $1\,\text{oz}$ copper).
   - Place via stitching arrays in thermal relief zones or directly under exposed MOSFET thermal pads.
3. **Switch Node ($SW$) Containment**:
   - Keep $SW$ copper area as small as possible while satisfying thermal limits to avoid radiated EMI (E-field antenna).
