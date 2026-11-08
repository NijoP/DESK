# Component Verification Engine (V1–V4)

## 1. Multi-Dimensional Fail-Closed Verification

A single boolean flag (such as "is_valid") is inadequate for hardware engineering. A part may have genuine manufacturer authenticity (V1) but be out of stock (V4), or have verified physical footprint (V3) but violate electrical DC bias derating (V2).

DESK evaluates four distinct dimensions:

### V1 — Identity Verification
- Checks manufacturer authorization and naming normalization.
- Validates MPN formatting and canonical DESK ID hash.

### V2 — Electrical Verification
- Verifies maximum operating voltage, current, and power against the active circuit net.
- Enforces capacitor $1.5\times$ voltage derating rule:
  $$V_{\text{rating}} \ge 1.5 \times V_{\text{rail}}$$
- Fails closed (`UNKNOWN`) if electrical specifications are missing.

### V3 — Physical Verification
- Validates footprint package designation.
- Compares CAD footprint pin counts and pinout against manufacturer package declarations.

### V4 — Procurement Verification
- Checks supplier SKU existence.
- Verifies stock quantity $\ge$ required BOM batch quantity.
- Enforces quote freshness: quotes $>7$ days old transition to `STALE`.

---

## 2. The 5-State Gate Lifecycle

- `PASS`: Valid, reproducible evidence collected and verified.
- `FAIL`: Verifiable violation detected (e.g. stock = 0, voltage exceeded).
- `UNKNOWN`: Missing, corrupted, or inconclusive evidence (fail-closed).
- `NOT_RUN`: Check was not performed.
- `STALE`: Upstream data changed or quote timestamp expired.
