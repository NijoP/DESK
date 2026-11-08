# Engineering Evidence Model & Provenance Ledger

## 1. Core Philosophy: Fail-Closed Evidence

In the DESK engineering platform, **verification cannot be assumed**. A test, DRC check, or manufacturing rule that was not executed—or whose execution produced incomplete or ambiguous logs—does not pass.

Under the 5-state gate lifecycle implemented in `desk/quality.py`:
- `PASS`: Valid, reproducible evidence collected and verified against physics/manufacturing rules.
- `FAIL`: Verifiable violation detected (e.g., short circuit, clearance breach, thermal overload).
- `UNKNOWN`: Missing, corrupted, or unparsable validation evidence. Treated as **FAIL-CLOSED** (blocks manufacturing release).
- `NOT_RUN`: Verification check has not yet been executed in the active pipeline stage.
- `STALE`: Upstream design profile, netlist, or physical geometry changed after verification was performed.

---

## 2. Structure of an Evidence Ledger Entry

Every engineering verification check produces an immutable, machine-readable evidence record:

```json
{
  "evidence_id": "ev_20261108_2200_drc_clr_001",
  "gate_id": "drc_clearance_verification",
  "pipeline_stage": "M5",
  "status": "PASS",
  "timestamp": 1794157200.123,
  "profile_revision": "rev_b4a8e29",
  "geometry_fingerprint": {
    "geometry_rev": "f7d832a1",
    "connectivity_rev": "c89b1420",
    "copper_rev": "90e311b5",
    "rules_rev": "12aa5678"
  },
  "metrics": {
    "min_measured_clearance_mm": 0.254,
    "required_clearance_mm": 0.200,
    "total_checks_evaluated": 1420,
    "violations_count": 0
  },
  "provenance": {
    "engine": "desk.rules.clearance_engine",
    "spatial_index_bin_mm": 5.0,
    "executor_pid": 14820,
    "host_tier": "MEDIUM"
  }
}
```

---

## 3. Evidence Invalidation & Multi-Domain Fingerprinting

Evidence is invalidated automatically if any relevant domain fingerprint in `desk/snapshot.py` changes:
- `geometry_rev`: Position, orientation, or bounding box of any track, via, pad, or outline modified.
- `connectivity_rev`: Net assignments, pin-to-net mappings, or schematic netlist modified.
- `copper_rev`: Polygon vertices, island voids, thermal spokes, or pour status modified.
- `rules_rev`: Track width, clearance, or current limit in `DesignProfile` modified.

If `rules_rev` changes, all DRC and manufacturing gates immediately transition to `STALE`.

---

## 4. Manufacturing Sign-Off Thresholds

A board design can only achieve manufacturing readiness approval if and only if:
1. All M6 quality gates are in state `PASS`.
2. Zero gates are in `FAIL`, `UNKNOWN`, `NOT_RUN`, or `STALE`.
3. The Captain has explicitly provided cryptographic or digital ledger approval.
