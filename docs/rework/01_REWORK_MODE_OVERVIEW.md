# DESK Rework Mode: Engineering Overview

**Document ID:** `docs/rework/01_REWORK_MODE_OVERVIEW.md`  
**Purpose:** Executive and engineering introduction to DESK Rework Mode.

---

## 1. What is Rework Mode?

In electronics hardware engineering, engineers frequently inherit partially completed, paused, or abandoned PCB projects. The board already contains weeks of careful work:
- Power supply buck converters laid out with tight loop inductance.
- Impedance-controlled RF differential traces matched in length.
- Fixed connector locations aligned to custom mechanical enclosures.
- Sourced, validated BOM components.

Traditional EDA automation and AI coding bots fail on inherited projects because they treat the PCB as an empty canvas—often ripping up working switching converters or regenerating placement from scratch.

**DESK Rework Mode** provides an engineering recovery workflow:
> **Existing design in. Engineering gaps identified. Verified manufacturing-ready design out.**

---

## 2. The Core Principle: Preserve Existing Engineering Intent

Rework Mode enforces five non-negotiable categories:
1. **Accepted & Protected Work:** Geometry, placement, and routing that are verified and must not be modified.
2. **Incomplete Work:** Unrouted airwires, unassigned nets, or missing bypass capacitors.
3. **Incorrect Work:** DRC clearance violations, pad number mismatches, or schematic-to-PCB discrepancies.
4. **Unknown Work:** Unspecified power currents or unverified stackups that require engineer review.
5. **Intentional Design Exceptions:** Approved no-connect pins, test pads, and DNI (Do Not Install) parts that must not be treated as defects.

---

## 3. High-Level Workflow Architecture

```text
1. NATURAL-LANGUAGE ACTIVATION ("Activate Rework Mode")
   |
2. EASYEDA CONNECTION & PROJECT IDENTITY BINDING
   |
3. IMMUTABLE BASELINE CAPTURE (Multi-Domain Fingerprints)
   |
4. 8-DOMAIN ENGINEERING AUDIT (Defect Inventory RW-0001..)
   |
5. DEPENDENCY-AWARE SURGICAL REPAIR PLANNING
   |
6. CAPTAIN APPROVAL TOKENS (RW-APR-XXXX)
   |
7. CONTROLLED MUTATION UNDER SINGLE-WRITER MUTEX
   |
8. MANDATORY PHYSICAL READBACK & VERIFICATION
   |
9. FAIL-CLOSED 8-GATE MANUFACTURING READINESS REPORT
```

---

## 4. Execution Policies

| Policy | Description | Modification Allowed |
|---|---|---|
| **`AUDIT_ONLY`** | Read-only reconnaissance. Discovers issues and produces repair recommendations without writing to the PCB. Default policy. | NO |
| **`GUIDED_REWORK`** | Explicit human approval required for every surgical repair operation (`RW-APR-XXXX`). | YES (Per-repair approval) |
| **`SUPERVISED_REWORK`** | Batch approval of non-conflicting repairs with automated readback verification and rollback on error. | YES (Batch approval) |
