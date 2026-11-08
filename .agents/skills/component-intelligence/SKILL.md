---
name: component-intelligence
description: Canonical component identity, manufacturer part numbers (MPNs), pin mapping, and footprint verification.
triggers:
  - "component intelligence"
  - "mpn"
  - "datasheet"
  - "pinout"
  - "footprint mapping"
  - "part resolution"
inputs:
  mpn: string
  specifications: dict
outputs:
  canonical_part: dict
  pins_resolved: boolean
authoritative_pipeline: M1
replay_safety: SAFE_IDEMPOTENT
---

# Component Intelligence Skill

## Purpose
Establishes canonical component identities, resolves manufacturer part numbers (MPNs), verifies datasheet pin functions, and validates footprint dimensions.

## When to Use
- Selecting and verifying integrated circuits, microcontrollers, and active components.
- Resolving part pins into `library/pins/<MPN>.json` via `tools/pins.py`.
- Finding qualified component alternatives based on voltage ratings, package, and thermal characteristics.

## Required Inputs
- Target MPN (Manufacturer Part Number) or electrical parameters (e.g. Buck regulator $5\text{V} \to 3.3\text{V}$, $2\text{A}$).
- Manufacturer datasheet specifications.

## Relevant DESK Modules
- `desk/component_intelligence/`: Canonical component models and attribute matching.
- `tools/resolve.py`: Resolves MPN to local component library.
- `tools/pins.py`: Extracts and formats verified pin mappings.

## Required Engineering Constraints
- No Guessing Pins: Never guess pin numbers or assignments. Use authoritative `library/pins/<MPN>.json`.
- No Invented Parts: Every MPN must resolve via `tools/resolve.py`.
- No Silent Replacement: Never substitute a component with an unverified alternative without explicit Captain sign-off.
- Pin Mapping Invariant: Every physical pin on the package must be mapped to a net or explicitly designated `nc` (No Connect).

## Recommended Workflow
1. Query component library: `python tools/resolve.py projects/<P> <MPN>`.
2. Generate/verify pinout specification: `python tools/pins.py projects/<P> <MPN>`.
3. Verify electrical ratings against `REQUIREMENTS.md` (voltage ceiling, current headroom, thermal derating).
4. Inspect physical footprint pad dimensions against IPC-7351 guidelines.
5. Record component justification row in `BOM_SELECTION.md`.

## Validation Steps
- Run component intelligence test suite: `python -m unittest discover -s tests -p "test_component*.py"`.
- Run pin verification audit: `python tools/verify.py projects/<P> pins`.

## Failure Conditions & Recovery
- Unresolved MPN: Check supplier aggregators or query Captain for approved equivalent part.
- Pinout mismatch: Halt block build immediately; verify against official manufacturer PDF datasheet.

## Expected Output
- Canonical component specification with verified pin mapping, footprint, and electrical parameters.

## Documentation References
- [Component Intelligence Architecture](file:///docs/component_intelligence/00_ARCHITECTURE.md)
- [BOM Selection Criteria](file:///docs/00b_COMPONENT_SELECTION.md)
