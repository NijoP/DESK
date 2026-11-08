---
name: drc-validation
description: 8 fail-closed quality acceptance gates, connectivity verification, and copper plane audits.
triggers:
  - "drc"
  - "quality gate"
  - "connectivity"
  - "short circuit"
  - "clearance violation"
  - "unconnected"
inputs:
  netlist: dict
  routed_board: dict
  fabricator_profile: dict
outputs:
  gate_status: dict
  release_eligible: boolean
authoritative_pipeline: M6
replay_safety: READ_ONLY
---

# DRC and Verification Skill

## Purpose
Enforces fail-closed quality gates, netlist connectivity audits, and fabricator DRC rules before releasing board artifacts.

## When to Use
- Running post-routing verification on completed board designs.
- Auditing design rule checks (DRC) for clearances, annular rings, and solder mask bridges.
- Authorizing manufacturing release packages (Gerber, BOM, pick-and-place).

## Required Inputs
- Authoritative project netlist.
- Placed and routed board state.
- Fabricator capability definition (min trace/space, min drill, annular ring).

## Relevant DESK Modules
- `desk/quality.py`: Fail-closed 8-gate acceptance verification engine.
- `tools/verify.py`: CLI verification runner.

## Required Engineering Constraints
- Fail-Closed Gate Invariant: Never weaken quality gates or substitute AI confidence for deterministic tool passes.
- 8 Hard Gates (Zero Exceptions):
  1. Zero unintended short circuits.
  2. Zero unconnected populated pads.
  3. Zero hard clearance violations.
  4. All critical nets 100% connected.
  5. Valid physical layer stackup configuration.
  6. Verified copper-zone and ground plane continuity.
  7. Electrical constraints satisfied.
  8. Manufacturing capability thresholds respected.

## Recommended Workflow
1. Execute netlist connectivity audit: `python tools/verify.py projects/<P> netlist`.
2. Inspect copper zone fills and detect unpoured islands.
3. Run comprehensive DRC check: `python tools/verify.py projects/<P> drc`.
4. Check quality scoring: Evaluate weighted design score ($0–100$).
5. Confirm all 8 hard gates report `PASS`.

## Validation Steps
- Execute test suite: `python -m unittest tests/test_quality.py`.
- Ensure output strictly displays `VERIFIED` or `PASS`.

## Failure Conditions & Recovery
- Hard gate failure: Release strictly blocked. Identify failing net/coordinate and route or displace tracks to clear violation.
- Dangling track / antenna: Trim track back to pad center.

## Expected Output
- Comprehensive verification report certifying all 8 hard gates passed with zero violations.

## Documentation References
- [Verification Guide](file:///docs/verification/00_VERIFICATION_SPEC.md)
