---
name: quality-gate-supervision
description: Procedural workflow for evaluating M6 quality hard gates, fail-closed evidence validation, and sign-off.
triggers:
  - "gate"
  - "quality"
  - "pass"
  - "fail"
  - "evidence"
  - "audit"
  - "sign-off"
inputs:
  evidence_records: list
  gate_thresholds: dict
outputs:
  gate_status: dict
  overall_passed: boolean
  blocking_gates: list
authoritative_pipeline: M6
replay_safety: SAFE_READ
---

# Quality Gate Supervision Skill

## Purpose
Supervises the fail-closed evaluation of all engineering hard gates before granting manufacturing or release sign-off.

## Procedural Execution Checklist

1. **5-State Evaluation**:
   - Inspect every registered gate (`schematic_integrity`, `clearance_drc`, `thermal_derating`, `copper_continuity`, `mfg_capabilities`).
   - Confirm status is strictly `PASS`.
   - Any gate with status `FAIL`, `UNKNOWN`, `NOT_RUN`, or `STALE` immediately blocks sign-off.
2. **Missing Evidence Rule**:
   - Absence of evidence log MUST be treated as fail-closed failure. Never infer a pass.
3. **Ledger Immutability**:
   - Record signed evaluation with timestamp, profile revision hash, and geometry fingerprint.
   - Forward formal sign-off report to Captain for review.
