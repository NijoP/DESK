# DESK Rework Mode: Manufacturing Readiness & Release Assessment

**Document ID:** `docs/rework/13_MANUFACTURING_READINESS.md`  

---

## 1. Fail-Closed Verification

A repaired PCB is only ready when physical engineering laws prove it is ready.
A high weighted quality score (e.g. 98/100) **can never override a failed hard acceptance gate**.

---

## 2. The 8 Non-Negotiable Hard Quality Gates

1. **Gate 1 (Zero Shorts):** DRC polygon/segment intersection checks must prove 0 shorts.
2. **Gate 2 (Zero Unconnected Pads):** Full connectivity graph traversal must prove 0 open airwires.
3. **Gate 3 (Clearance Compliance):** IPC-2221 voltage clearance matrix verified.
4. **Gate 4 (Critical Net Integrity):** High-speed, RF, and power rails 100% connected.
5. **Gate 5 (Stackup Integrity):** Symmetrical copper/dielectric stackup verified.
6. **Gate 6 (Return-Path Continuity):** 2D ray casting confirms no split-plane crossings.
7. **Gate 7 (IPC-2152 Ampacity):** Power trace widths verified against maximum current.
8. **Gate 8 (Manufacturing DFM):** Minimum drill, annular ring, and solder mask rules verified.

---

## 3. Canonical Outcome States

- **`READY_FOR_MANUFACTURING`**: All 8 hard gates PASS with valid evidence on the final revision.
- **`CONDITIONALLY_READY`**: All hard gates PASS, but non-blocking review items or approved exceptions remain.
- **`NOT_READY`**: At least one hard gate failed, remains unknown, or has stale evidence.
- **`INCOMPLETE`**: Outstanding repairs remain unresolved.
