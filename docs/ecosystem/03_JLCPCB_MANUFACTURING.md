# Domain C: JLCPCB Manufacturing & SMT Assembly Integration

**Author:** Principal Manufacturing Integration Engineer  
**Scope:** PCB Fabrication Quotation, PCBA SMT Assembly Cost Modeling, DFM Enforcement, and the Absolute Order Guard  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Reference

---

## 1. Architectural Role & Objective

The JLCPCB integration layer bridges CAD design output with physical manufacturing execution. It automates:
1. **DFM Constraints Verification**: Rapid validation of trace width, spacing, drill diameter, and layer count before fabrication handoff.
2. **Deterministic Cost Estimation**: Real-time quotation for both raw PCB fabrication and automated PCBA SMT assembly.
3. **Pick-and-Place (CPL) Rotation Normalization**: Automated angle alignment transforming CAD footprint rotations to JLCPCB feeder specifications.
4. **The Absolute Order Guard**: Strict fail-closed security preventing autonomous software or AI agents from completing financial purchases without human confirmation.

---

## 2. PCBA SMT Assembly Engine

### 2.1 Basic vs. Extended Component Classification
JLCPCB divides SMT assembly components into fee tiers:
- **Basic Parts**: High-turnover passive components (0402, 0603, 0805 resistors/capacitors, standard transistors) pre-loaded on pick-and-place machines. **$0.00 setup/feeder fee**.
- **Preferred Parts**: Readily loaded parts with minimal handling.
- **Extended Parts**: Specialized ICs, connectors, and diodes requiring manual feeder reel loading. **$3.00 feeder setup fee per unique part**.

`JLCPCBPCBACatalog.classify_part(lcsc_pn, package)` classifies parts automatically based on part number databases and prefix heuristics.

### 2.2 Centroid / CPL Rotation Alignment
Different EDA tools define pin 1 and footprint origins inconsistently. To prevent component misorientation during SMT assembly, DESK maintains the `ROTATION_OFFSET_TABLE`:
- `SOT-223`: $+180^\circ$ offset
- `SOD-123`, `SMA`, `SMB`: $+180^\circ$ offset
- `LED_0603`, `LED_0805`: $+180^\circ$ offset
- `SOT-23`, `SOIC-8`, `QFN`: $0^\circ$ standard alignment

Angles are normalized to $[0^\circ, 360^\circ)$ via `JLCPCBPCBACatalog.normalize_rotation(cad_rotation, package)`.

---

## 3. The Absolute Order Guard

```
┌─────────────────────────────────┐
│   Agent / Automation Engine     │
└────────────────┬────────────────┘
                 │ Attempt order placement
                 ▼
┌─────────────────────────────────┐
│   OrderApprovalManager          │
│   (Ephemeral 5-minute Token)    │
└────────────────┬────────────────┘
                 │ Requires Captain Confirmation
                 ▼
┌─────────────────────────────────┐
│   Interactive Human Captain     │
│   "CAPTAIN-APPROVE-A8F2"        │
└────────────────┬────────────────┘
                 │ Validated & Single-Use Consumed
                 ▼
┌─────────────────────────────────┐
│   JLCPCB Manufacturing Handoff  │
│   (Manual payment dashboard)    │
└─────────────────────────────────┘
```

- **Policy Invariant**: No automated monetary spending or autonomous shopping cart checkout is permitted.
- **Execution Flow**:
  1. Engine calls `order_guard.request_approval(quote_summary)`.
  2. An ephemeral token (valid for 300 seconds) is generated: `CAPTAIN-APPROVE-XXXX`.
  3. The Captain reviews the quotation and issues confirmation.
  4. The client executes `submit_order_with_approval(quote, token)`.
  5. The token is verified and immediately consumed (single-use), preventing replay attacks.
