# DESK Ecosystem Architecture Audit: AI-Native Electronics Platform

**Author:** Principal Software Architect & Electronics Automation Lead  
**Scope:** Integration of EDA, Supplier Catalogues, PCBA Manufacturing, and Hardware-Adaptive Security Infrastructure  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Reference

---

## 1. Executive Summary

DESK is evolving from a local electronics engineering CLI into an **AI-native electronics engineering execution ecosystem**. Inspired by unified software-hardware workflows, DESK seamlessly connects four foundational domains:
1. **Domain A — EDA Integration**: EasyEDA Pro (via official CLI `easyeda-pro` and native IPC bridge) alongside KiCad design interchange.
2. **Domain B — Component Intelligence & Sourcing**: LCSC catalog intelligence, expanded through an extensible provider framework to Mouser, DigiKey, element14, and Robu.
3. **Domain C — Manufacturing Integration**: JLCPCB PCB fabrication, SMT assembly validation, DFM checks, quotation engines, and fail-safe order preparation.
4. **Domain D — Authentication & Security Infrastructure**: Cross-platform, zero-external-dependency OS-native credential storage (Windows Credential Manager, macOS Keychain, Linux Secret Service), paired with a restricted Credential Broker that enforces a strict security perimeter against agent prompt leakage.

This document establishes the audit of existing subsystems, identifies interface boundaries, specifies security isolation contracts, and details the unified ecosystem roadmap.

---

## 2. Domain Inventory & Current Capability Matrix

| Domain | Subsystem | Current State | Target Ecosystem Capability |
| :--- | :--- | :--- | :--- |
| **Domain A: EDA** | EasyEDA Pro Bridge | Socket/IPC bridge in `desk/bridge.py` | Official CLI discovery (`easyeda-pro doctor/session/invoke`), project session binding, fail-safe mutation gates, netlist & layout readback. |
| **Domain A: EDA** | KiCad Interop | File parser & local symbols in `desk/component_intelligence/eda/` | Bi-directional schematic/footprint interchange, netlist synchronization. |
| **Domain B: Sourcing** | LCSC Integration | Canonical database, REST client, part mapper, parametric specification parsing | Multi-supplier provider abstraction (`desk/component_intelligence/suppliers/`), cached pricing/stock, lifecycle monitoring. |
| **Domain B: Sourcing** | Secondary Distributors | Provider interface defined (`BaseSupplierProvider`) | Mouser, DigiKey, element14, and Robu adapters with unified part resolution. |
| **Domain C: Manufacturing** | JLCPCB PCB | DFM rule engine in `desk/quality.py`, `desk/drc_engine.py` | Automated Gerber inspection, stackup compliance, real-time board quotation. |
| **Domain C: Manufacturing** | JLCPCB PCBA | BOM generator in `desk/component_intelligence/procurement/` | Basic vs. Extended parts classification, rotation offset correction, CPL/Centroid generation, assembly feasibility audit. |
| **Domain C: Manufacturing** | Order Safety | Manual review policy | Hard barrier: Zero unapproved live orders, interactive Captain confirmation token required for all external submissions. |
| **Domain D: Auth & Security** | Credential Storage | Environment variables / placeholder | OS-native credential storage (`Advapi32.dll` on Windows, Keychain on macOS, Secret Service on Linux) with zero pip dependencies. |
| **Domain D: Auth & Security** | Credential Broker | None (raw keys accessible in memory) | Agent isolation boundary: LLMs receive no raw secrets; broker mints scoped, signed requests internally. |

---

## 3. Detailed Domain Analysis

### 3.1 Domain A: EasyEDA Pro CLI & Local IPC
EasyEDA Pro provides both an official command-line interface (`easyeda-pro`) and an internal local WebSocket/HTTP IPC bridge.
- **Discovery**: DESK dynamically scans standard installation paths (`%LOCALAPPDATA%\EasyEDAPro`, `/Applications/EasyEDAPro.app`, `/usr/bin/easyeda-pro`) and system `PATH`.
- **Session Introspection**: `easyeda-pro session list` yields active design sessions without mutating state.
- **Safety Boundary**: All non-destructive read operations (netlist extraction, DRC status, geometry queries) execute synchronously with short timeouts. Any mutating operation (placement injection, trace modification, copper repour) mandates:
  1. Target project UUID verification.
  2. Rollback snapshot creation (`desk/snapshot.py`).
  3. Stale lock prevention (`desk/ops.py`).
  4. Explicit Captain approval if outside disposable testing projects.

### 3.2 Domain B: Component Intelligence & Multi-Supplier Sourcing
The component intelligence subsystem separates canonical component identity from supplier-specific offers:
- **Canonical Part Identity**: MPN, Manufacturer, Normalized Package, Parametric Specifications (voltage, capacitance, resistance, tolerance, power rating).
- **Supplier Offer**: Supplier Part Number (e.g. LCSC `Cxxxxx`), Stock level, Tiered Unit Pricing, Packaging Type (Tape & Reel, Cut Tape, Tube), Lead Time.
- **Parametric Search & Alternatives**: Pin-compatible and electrically equivalent alternatives evaluated through normalized physical and electrical tolerances.

### 3.3 Domain C: JLCPCB Manufacturing & PCBA SMT Preparation
JLCPCB integration requires a sharp distinction between general catalogue distribution (LCSC) and assembly line availability (JLCPCB SMT):
- **Library Separation**: JLCPCB SMT components are classified into **Basic Parts** (mounted without feeder setup fees), **Preferred Parts**, and **Extended Parts** (incurring feeder changeover fees).
- **Rotation Offset Handling**: PCB CAD footprint pin-1 orientations frequently diverge from SMT tape-and-reel standard angles. DESK maintains a deterministic rotation offset dictionary per footprint family (e.g. SOT-23, SOIC-8, QFN, SOD-123).
- **Manufacturing Outputs**: Deterministic generation of:
  1. Standard Gerber / Drill packages.
  2. JLCPCB-formatted Bill of Materials (`Designator, Footprint, LCSC Part Number, Value`).
  3. JLCPCB-formatted Pick and Place / CPL (`Designator, Val, Package, Mid X, Mid Y, Rotation, Layer`).
- **Absolute Order Guard**: DESK is strictly forbidden from placing live commercial orders or transferring funds automatically. Quotations, DFM checks, and file pre-validations are fully automated; purchase execution halts for interactive user confirmation.

### 3.4 Domain D: Secure Credential Management & Agent Isolation
AI agents operating in autonomous coding environments must never be granted direct access to raw API secrets:
- **Threat Model**: An LLM agent prompted with arbitrary instructions could inadvertently echo secrets into conversation logs, scratch files, or git commits.
- **Solution — Credential Broker**:
  - Credentials reside exclusively in the OS-native credential store (Windows Credential Manager via `ctypes` calling `Advapi32.dll`, macOS Keychain via `security`, Linux via Secret Service or `0600` master-encrypted storage).
  - The CLI provides interactive configuration via `getpass.getpass()`.
  - Operations registered in `desk/operation_registry.py` (e.g., `supplier.search`, `manufacturing.quote`) communicate with `desk.auth.broker.CredentialBroker`, which attaches tokens internally to outbound network sessions and strictly returns scrubbed business data.

---

## 4. Gap Analysis & Implementation Roadmap

```
[Phase 0: Audit & Architecture Documentation] (Completed)
                  │
                  ▼
[Phase 1: Domain D — OS-Native Credential Storage & Security Broker]
  ├── desk/auth/storage.py (Windows Advapi32 / macOS Keychain / Linux Secret Service)
  ├── desk/auth/broker.py (Secret scrub, permission broker, token minting)
  ├── desk/auth/cli.py (Interactive 'desk auth configure/status/test/remove')
  └── tests/test_auth_system.py
                  │
                  ▼
[Phase 2: Domain A — EasyEDA Pro CLI & Bridge Harness]
  ├── desk/eda/easyeda_pro.py (CLI discovery, session monitor, read/write safety)
  └── tests/test_easyeda_pro_integration.py
                  │
                  ▼
[Phase 3: Domain C — JLCPCB Manufacturing & PCBA SMT Engine]
  ├── desk/manufacturing/jlcpcb/client.py (API client with rate limiting & mock mode)
  ├── desk/manufacturing/jlcpcb/pcba_catalog.py (Basic/Extended classification, rotation)
  ├── desk/manufacturing/jlcpcb/quote.py (PCB & PCBA quotation model, DFM rules)
  ├── desk/manufacturing/jlcpcb/order_guard.py (Absolute fail-closed purchase guard)
  └── tests/test_jlcpcb_integration.py
                  │
                  ▼
[Phase 4: Domain B & BOM Intelligence — Multi-Supplier Sourcing]
  ├── desk/component_intelligence/procurement/bom_export.py (JLCPCB & LCSC exports)
  ├── desk/component_intelligence/suppliers/providers/mouser/ (Extensible provider)
  └── tests/test_ci_procurement_exports.py
                  │
                  ▼
[Phase 5: Unified Client Experience & CLI Settings]
  ├── desk/ui/settings.py (Status dashboard, connection probes, health checks)
  └── tools/desk.py (Subcommand integration: 'auth', 'settings')
                  │
                  ▼
[Phase 6: End-to-End Orchestration & Operation Registry]
  ├── desk/operation_registry.py (Registration of ecosystem operations)
  └── tests/test_ecosystem_e2e.py (Full flow: Intent -> Spec -> Sourcing -> DFM -> BOM)
                  │
                  ▼
[Phase 7: Full Verification, Benchmarks & Final Execution Report]
```
