---
name: manufacturing-verification
description: Procedural workflow for PCB fabrication constraints, drill aspect ratios, solder mask webs, and Gerber export.
triggers:
  - "manufacturing"
  - "gerber"
  - "drc check"
  - "fab"
  - "drill"
  - "soldermask"
  - "release"
inputs:
  snapshot: dict
  mfg_constraints: dict
outputs:
  mfg_ready: boolean
  fab_violations: list
  gerber_manifest: dict
authoritative_pipeline: M5/M6
replay_safety: SAFE_READ
---

# Manufacturing Verification Skill

## Purpose
Verifies physical PCB geometry against target PCB fabricator capabilities (e.g., JLCPCB, PCBWay) before manufacturing release.

## Procedural Execution Checklist

1. **Drill & Aspect Ratio Rules**:
   - Minimum drill diameter $\ge 0.2\,\text{mm}$ (or $0.3\,\text{mm}$ for standard process).
   - Annular ring width $\ge 0.13\,\text{mm}$ around all through-hole pads and vias.
   - Hole-to-hole clearance $\ge 0.5\,\text{mm}$ to prevent substrate fracturing.
2. **Solder Mask & Silkscreen**:
   - Solder mask dam width $\ge 0.1\,\text{mm}$ between adjacent SMT pads.
   - Ensure silkscreen does not overlap exposed solder pads (clipping check).
3. **Board Edge & Mechanical Keepout**:
   - Copper pullback from board edge $\ge 0.5\,\text{mm}$ for V-cut routing or $0.3\,\text{mm}$ for mouse-bites.
4. **Gerber Manifest Validation**:
   - Verify presence of Top/Bottom Copper, Top/Bottom Mask, Top/Bottom Silk, Drill, and Outline layers.
