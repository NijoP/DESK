# DESK Rework Mode: Baseline Snapshot & Change Detection

**Document ID:** `docs/rework/04_BASELINE_AND_PROJECT_IDENTITY.md`  

---

## 1. Immutable Baseline Capture

Before diagnosing defects or proposing modifications, DESK establishes an immutable baseline:
- Components & footprint packages.
- Pads & net assignments.
- Tracks, widths, and layers.
- Vias and hole dimensions.
- Copper zones and repour state.
- Stackup thickness and dielectric constants.
- Design rules and clearances.

Saved to: `projects/<P>/state/rework/<SESSION_ID>/baseline.json`.

---

## 2. Multi-Domain Revision Fingerprints

Rework Mode tracks 5 distinct physical domains:
1. `geometry_rev`: Component $(X, Y, \theta)$, track endpoints, via locations.
2. `connectivity_rev`: Pad-to-net, track-to-net, via-to-net topology.
3. `stackup_rev`: Layer names, copper weights, core thicknesses.
4. `copper_rev`: Zone outlines, net assignments, priority orders.
5. `rules_rev`: Track clearances, minimum drill sizes, annular rings.
6. `composite_fingerprint`: Cryptographic SHA-1 digest combining all domains.

---

## 3. Detecting External Modifications

If another engineer opens the project in EasyEDA Pro and moves a component or reroutes a trace while DESK is running:
- `BaselineCaptureEngine.detect_external_modifications()` detects the fingerprint divergence.
- Pending approval tokens and repair plans are invalidated (`SUPERSEDED`).
- DESK alerts the engineer: *"External modifications detected in geometry/connectivity. Baseline out of sync. Re-audit required."*
