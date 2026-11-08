---
name: engineering-diagnostics
description: Procedural workflow for DRC violation analysis, airwire diagnostics, and physical clearance recovery.
triggers:
  - "diagnostics"
  - "drc"
  - "violation"
  - "short circuit"
  - "airwire"
  - "unrouted"
inputs:
  snapshot: dict
  profile: DesignProfile
outputs:
  violation_report: list
  clearance_errors: integer
  short_circuits: integer
authoritative_pipeline: M5
replay_safety: SAFE_READ
---

# Engineering Diagnostics Skill

## Purpose
Scans the active PCB snapshot for design rule violations, short circuits, dangling track stubs, and incomplete connectivity.

## Procedural Execution Checklist

1. **Clearance Matrix Inspection**:
   - Evaluate all track-to-track, track-to-pad, pad-to-pad, and via-to-copper clearances against `profile.clearance_rules`.
   - Flag any clearance $< \text{rule}$ as a critical DRC violation.
2. **Short Circuit & Net Conflict Audit**:
   - Traverse the spatial grid index to detect overlapping copper primitives belonging to different net identifiers.
   - Any un-isolated intersection triggers an immediate `FAIL` state.
3. **Airwire & Connectivity Verification**:
   - Check all netlist pin nodes against routed track segments using disjoint-set union (connected components).
   - Report any unrouted pin pairs as airwire defects.
