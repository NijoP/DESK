# DESK Rework Mode: Surgical Repair Planning

**Document ID:** `docs/rework/07_REPAIR_PLANNING.md`  

---

## 1. Minimal-Change Philosophy

Rework Mode enforces **surgical repair**:
- Add only the missing connection without touching accepted routing.
- Nudge only the component that violates mechanical edge clearances.
- Reassign only the pad net that differs from schematic truth.
- Repour only the affected copper zone.

---

## 2. Geometry Protection Classification

Every primitive on the board is classified:
- **`PROTECTED`**: Locked connector anchors, approved high-speed differential pairs, mounting holes.
- **`ACCEPTED`**: Completed, verified routes that must not be ripped up.
- **`MODIFIABLE`**: Target track or component authorized for repair.
- **`INVALID`**: Defective tracks causing shorts or DRC errors, designated for rip-up.
- **`UNKNOWN`**: Unverified intent requiring human consultation.

---

## 3. Dependency Analysis

Repairs are ordered strictly by engineering dependency:
```text
1. Schematic & Netlist Discrepancies (RW-0002)
   |
2. Component & Footprint Invariants (RW-0005)
   |
3. Mechanical Placement & Edge Clearances (RW-0006)
   |
4. Power Rail Trace Width Adjustments (RW-0010)
   |
5. Critical Net Routing (RW-0011)
   |
6. General Signal Routing (RW-0020)
   |
7. Copper Ground Plane Repour (RW-0066)
   |
8. DRC & Manufacturing Release Verification
```

Downstream tasks are blocked until upstream dependencies succeed.
