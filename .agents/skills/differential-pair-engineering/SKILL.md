---
name: differential-pair-engineering
description: Procedural workflow for differential pair impedance matching, trace spacing, and intra-pair length tuning.
triggers:
  - "diff pair"
  - "differential"
  - "usb"
  - "can"
  - "ethernet"
  - "skew"
  - "length match"
inputs:
  pair_names: list
  target_impedance_ohms: float
  profile: DesignProfile
outputs:
  routed_pairs: list
  length_skew_ps: float
  skew_pass: boolean
authoritative_pipeline: M3
replay_safety: SAFE_IDEMPOTENT
---

# Differential Pair Engineering Skill

## Purpose
Enforces controlled differential impedance ($90\,\Omega$ USB, $100\,\Omega$ Ethernet, $120\,\Omega$ CAN) and length matching.

## Procedural Execution Checklist

1. **Calculate Pair Geometry**:
   - Compute trace width $W$ and edge-to-edge separation $S$ for target differential impedance $Z_{\text{diff}}$ based on substrate dielectric constant $\varepsilon_r$ and dielectric thickness $H$.
2. **Coupling Integrity**:
   - Keep $S$ constant along the entire route.
   - Symmetrically route pair around obstacles; avoid splitting pair tracks around vias.
3. **Length & Skew Compensation**:
   - Apply serpentine or accordion length tuning as close as possible to the source of mismatch.
   - Maximum allowable intra-pair skew $\le 0.15\,\text{mm}$ ($\approx 1\,\text{ps}$) for high-speed protocols.
