---
name: pcb-routing
description: Procedural workflow for single-ended, high-speed, and general PCB trace routing.
triggers:
  - "route"
  - "routing"
  - "track"
  - "trace"
  - "via"
  - "fanout"
  - "clearance"
inputs:
  net_names: list
  routing_layers: list
  profile: DesignProfile
outputs:
  routed_tracks: list
  unrouted_nets: list
  drc_passed: boolean
authoritative_pipeline: M3
replay_safety: SAFE_IDEMPOTENT
---

# PCB Routing Skill

## Purpose
Coordinates deterministic track routing using IPC-2152 equations, net-class constraints, and impedance profiles.

## Procedural Execution Checklist

1. **Calculate Trace Widths**:
   - Determine current capacity and allowable temperature rise ($\Delta T = 10^\circ\text{C}$ or $20^\circ\text{C}$).
   - Query `profile.trace_width(net_name, layer)` to compute exact width from layer copper weight (oz/ft²).
2. **Layer Allocation**:
   - High-speed and sensitive analog traces routed on Top layer with solid ground plane on Layer 2.
   - Avoid routing across ground plane splits or voids.
3. **Geometry Constraints**:
   - Strict 45° chamfered bends (no 90° right angles to minimize acid traps and impedance discontinuities).
   - Enforce net-class clearance rules against neighboring copper.
4. **Invoke M3 Routing Engine**:
   - Call `desk.router.route_nets(net_names, routing_layers, profile)`.
