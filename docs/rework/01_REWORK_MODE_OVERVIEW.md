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

---

## 5. Rework Mode Technical Documentation Series

| Document | Title & Focus |
|---|---|
| [**00 Architecture Audit**](00_ARCHITECTURE_AUDIT.md) | Pre-implementation codebase analysis, gap discovery, and invariant mapping. |
| [**01 Overview**](01_REWORK_MODE_OVERVIEW.md) | High-level system architecture, principles, and policy descriptions. |
| [**02 Activation & Session**](02_ACTIVATION_AND_SESSION.md) | Natural-language intent recognition, session creation, and lifecycle states. |
| [**03 EasyEDA Connection**](03_EASYEDA_CONNECTION.md) | Active window discovery, port probing, and project binding validation. |
| [**04 Baseline & Identity**](04_BASELINE_AND_PROJECT_IDENTITY.md) | Multi-domain hashing, coordinate capture, and revision change detection. |
| [**05 Engineering Audit**](05_ENGINEERING_AUDIT.md) | 8-domain defect inspection (clearances, return paths, unconnected pins). |
| [**06 Issue Inventory**](06_ISSUE_INVENTORY.md) | Defect cataloging, severity tiers (`CRITICAL`, `ERROR`, `WARNING`), and IDs (`RW-0001..`). |
| [**07 Repair Planning**](07_REPAIR_PLANNING.md) | Surgical minimal-change planning, dependency DAGs, and protected objects. |
| [**08 Approval & Safety**](08_APPROVAL_AND_SAFETY.md) | Human-in-the-loop authorization tokens (`RW-APR-XXXX`) and safety fences. |
| [**09 Repair Execution**](09_REPAIR_EXECUTION.md) | Single-writer serialized CAD mutations and timeout protection. |
| [**10 Readback & Verification**](10_READBACK_AND_VERIFICATION.md) | Post-repair ECAD canvas readback, delta inspection, and evidence recording. |
| [**11 Recovery & Restart**](11_RECOVERY_AND_RESTART.md) | Session reconciliation, crash recovery, and interrupted state handling. |
| [**12 Mission Control**](12_MISSION_CONTROL.md) | Local telemetry cockpit integration, REST routes, and real-time SSE stream. |
| [**13 Manufacturing Readiness**](13_MANUFACTURING_READINESS.md) | 8 fail-closed hard release gates and 100-point engineering scorecard. |
| [**14 Troubleshooting**](14_TROUBLESHOOTING.md) | Common errors, port conflicts, window mismatches, and recovery procedures. |
| [**15 Testing & Validation**](15_TESTING_AND_VALIDATION.md) | Comprehensive automated test matrix across all rework subsystems. |
