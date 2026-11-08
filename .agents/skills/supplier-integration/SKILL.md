---
name: supplier-integration
description: Supplier provider interfaces, LCSC integration, stock snapshots, pricing tiers, and procurement provenance.
triggers:
  - "supplier"
  - "lcsc"
  - "stock"
  - "pricing"
  - "procurement"
  - "bom cost"
inputs:
  mpn: string
  supplier_id: string
outputs:
  supplier_part: dict
  stock_available: integer
  unit_price: float
authoritative_pipeline: M1
replay_safety: SAFE_IDEMPOTENT
---

# Supplier Integration Skill

## Purpose
Manages supplier provider interfaces (LCSC, Mouser, DigiKey), queries real-time stock snapshots, verifies volume pricing tiers, and tracks procurement provenance.

## When to Use
- Validating component availability and lead times during Gate B (BOM Selection).
- Resolving LCSC part numbers (C-codes) for JLCPCB manufacturing compatibility.
- Auditing bill-of-materials cost curves across production volumes ($1, 10, 100, 1000\text{ units}$).

## Required Inputs
- Manufacturer part number (MPN) or supplier part number (e.g. LCSC `C12345`).
- Target production volume.

## Relevant DESK Modules
- `desk/component_intelligence/supplier.py` (or supplier adapters).
- `tools/bom.py`: Bill of materials generator and cost validator.

## Required Engineering Constraints
- Provenance Invariant: Every component in `BOM_SELECTION.md` must carry verifiable supplier provenance (supplier name, SKU, price, timestamp).
- Stock Threshold: Critical ICs must have verified in-stock quantities exceeding minimum batch thresholds before gate acceptance.
- Rate Limiting: Respect API rate limits and backoff policies when querying supplier endpoints.

## Recommended Workflow
1. Query supplier adapter for target part: `supplier.get_part_data(mpn)`.
2. Inspect lifecycle status (Active vs. Not Recommended for New Designs / EOL).
3. Validate minimum order quantity (MOQ) and price breaks.
4. Record verified LCSC part code and footprint package in `blocks/NN_ID.json`.
5. Run BOM validation: `python tools/bom.py projects/<P>`.

## Validation Steps
- Execute supplier adapter unit tests: `python -m unittest discover -s tests -p "test_supplier*.py"`.
- Run BOM audit: `python tools/bom.py projects/<P> --audit`.

## Failure Conditions & Recovery
- Supplier API timeout: Use cached local snapshots if valid; fallback to alternative approved vendor.
- Zero stock detected: Trigger component alternative search via `component-intelligence` skill.

## Expected Output
- Verified procurement record with in-stock confirmation, pricing tiers, and JLCPCB assembly tags.

## Documentation References
- [Component Selection Guide](file:///docs/00b_COMPONENT_SELECTION.md)
