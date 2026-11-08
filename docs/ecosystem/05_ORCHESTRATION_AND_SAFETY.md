# Domain E: End-to-End Orchestration & Ecosystem Safety Invariants

**Author:** Principal Software Architect & Systems Automation Lead  
**Scope:** Unified Lifecycle Orchestration, Operation Registry Contracts, and Multi-Tier Safety Gates  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Reference

---

## 1. Unified Electronics Engineering Lifecycle

DESK coordinates the complete hardware design and manufacturing journey:

```
[1. User Intent / Requirement]
        │
        ▼
[2. Multi-Supplier Part Discovery] ──► (LCSC, Mouser API via CredentialBroker)
        │
        ▼
[3. Fail-Closed Part Verification] ──► (Identity, Electrical, Physical, Procurement V1-V4)
        │
        ▼
[4. EDA Layout & Routing Inspection] ──► (EasyEDA Pro CLI / IPC Bridge, KiCad Interop)
        │
        ▼
[5. Procurement BOM Optimization] ──► (Tiered volume pricing, stock aggregation)
        │
        ▼
[6. Manufacturing File Generation] ──► (JLCPCB PCBA BOM, CPL Centroid with Rotation Alignment)
        │
        ▼
[7. DFM Analysis & Live Quotation] ──► (Min trace/drill compliance, PCB + PCBA pricing)
        │
        ▼
[8. Absolute Order Guard] ──► (Human Captain Approval Token Required)
        │
        ▼
[9. Manufacturing Handoff] ──► (Manual dashboard payment, Zero autonomous spending)
```

---

## 2. Operation Registry Declarations

Four new authoritative ecosystem operations are registered in `desk.operation_registry`:

| Operation ID | Pipeline Stage | Replay Policy | Resource Class | Description |
| :--- | :--- | :--- | :--- | :--- |
| `supplier_search` | M1 | `SAFE_READ` | `LIGHT` | Queries registered distributor catalogs (LCSC, Mouser) for component availability. |
| `build_procurement_bom`| M1 | `SAFE_READ` | `MEDIUM` | Optimizes BOM volume pricing, stock availability, and distributor splits. |
| `eda_inspect_project` | M2 | `SAFE_READ` | `LIGHT` | Non-destructive offline inspection of EDA files and safety protection status. |
| `manufacturing_quote` | M6 | `SAFE_READ` | `LIGHT` | Validates DFM constraints and computes PCB fabrication + PCBA assembly costs. |

---

## 3. Four Pillars of Ecosystem Safety

### 3.1 Credential & Prompt Safety (Domain D)
- **Zero Raw Secrets**: API keys reside in native OS vaults (Windows Credential Manager via `Advapi32.dll`, macOS Keychain, POSIX `0600` stores).
- **Leak Scrubbing**: The `CredentialBroker` scrubs known secrets and high-entropy bearer tokens from all logs, exceptions, and agent outputs.
- **Fail-Closed Auth**: Missing credentials abort immediately with copyable CLI remediation commands (`python tools/desk.py auth configure <provider>`).

### 3.2 Design Mutation Safety (Domain A)
- **Customer Protection**: Projects matching patterns such as `WATCH` or `BEEBOX` are locked into read-only mode.
- **Rollback Snapshot Requirement**: Mutations mandate an existing `.snapshot/` record prior to writing.
- **Captain Gate**: Live writes outside disposable testing environments require explicit interactive authorization.

### 3.3 Sourcing & Inventory Safety (Domain B)
- **Canonical Separation**: Intrinsic part definitions never mutate when external distributor pricing or availability changes.
- **Shortage Flagging**: Any shortage or unverified component raises explicit warnings in the procurement BOM.

### 3.4 Purchasing & Financial Safety (Domain C)
- **Zero Autonomous Spending**: AI agents and automated scripts are blocked from completing financial transactions or executing unapproved orders.
- **Ephemeral Captain Tokens**: Orders require a 5-minute single-use token (`CAPTAIN-APPROVE-XXXX`) confirmed interactively by the human Captain.
- **Single-Use Consumption**: Tokens are consumed upon validation to prevent replay attacks.
