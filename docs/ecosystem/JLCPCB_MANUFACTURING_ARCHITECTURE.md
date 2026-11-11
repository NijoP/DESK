# JLCPCB Manufacturing Architecture

**Inventory date:** 2026-11-12. **Owner:** JLCPCB Manufacturing Team. **Rule:** manufacturing limits are versioned profiles validated against the current official specification before use; DESK flags designs outside the selected capability and never relaxes rules to make a board look manufacturable; no order is ever placed without explicit human approval.

## What exists today (facts)

| Piece | File | State |
|---|---|---|
| Capabilities | `desk/manufacturing/jlcpcb/capabilities.py` `JLCPCBCapabilities` (frozen dataclass, **no version**, 3.5 mil trace/space, 0.2 mm drill, 32 layers, finishes, $3 extended fee, $8 PCBA setup) | hard-coded |
| Versioned profile (separate, inconsistent) | `desk/profile.py` `ManufacturerProfile` (`jlcpcb_standard_2layer` v2026.1: 5 mil / 4.02 mil / 12 mil drill / 5 mil annular / 12 mil edge; 4-layer and PCBWay presets) | EXISTS, versioned, **not linked** to the capabilities module |
| Quote | `quote.py` `JLCPCBQuotingEngine` (`validate_dfm`, `calculate_pcb_quote`, `calculate_pcba_quote`): local estimate with hard-coded prices, no timestamp, not marked ESTIMATED | local estimate |
| Client | `client.py` `JLCPCBClient` with `BASE_URL=https://api.jlcpcb.com/v1` never called; `submit_order_with_approval` returns `MOCK-JLC-8849201` | mock |
| Order guard | `order_guard.py` `OrderApprovalManager`: single-use `CAPTAIN-APPROVE-…` tokens, 300 s lifetime, in-memory; `OrderExecutionBlockedError` | EXISTS, offline-tested |
| PCBA catalogue | `pcba_catalog.py`: 11 hard-coded basic C-numbers + package-prefix heuristic applied to the C-number string; everything else Extended; `is_smt_eligible` always True; two entries contradict the LCSC fixtures (C347222, C2040) | PARTIAL, data errors |
| Release gate | `tools/release.py` + `desk/release.py`: offline gates, live ERC/DRC, native EasyEDA exports (Gerber, BOM, PnP, IPC-D-356A, netlist, PDF), sha256 manifest | EXISTS; no human approval token at release |
| Readiness report | `desk/drc_engine.py` `evaluate_readiness` (fail-closed since M1; lists checks not performed) | EXISTS |

## Target architecture

```
DesignProfile.manufacturing (ManufacturerProfile, versioned) <── jlcpcb/capabilities.py becomes a
   loader of versioned JSON profiles: library/manufacturing/jlcpcb/<profile>@<version>.json
   { source_url, verified_on, verified_by, layers, min_trace, min_space, min_drill, annular, via types,
     finishes, mask colours, edge/slot rules, impedance availability, thickness, copper weights, tolerances }
        │
        ▼
Preflight (desk/manufacturing/preflight.py, new): board outline & dimensions, stackup match,
   trace widths/clearances vs profile AND vs desk.ipc standards tables, drill/annular/aspect vs actual vias,
   mask openings, copper-to-edge, Gerber/drill file presence and layer count, BOM/CPL validation
   (BOM_CPL_VALIDATION_SPECIFICATION.md) ──> ManufacturingReadinessReport (structured, fail-closed)
        │
        ▼
Release gate: human approval token (reuse OrderApprovalManager pattern) before customer files are released;
   fabricator DFM review recorded separately as EXTERNAL_PENDING; order placement never automatic.
```

## Rules

- A profile without `verified_on` and `source_url` is UNVERIFIED and cannot approve a release.
- Quotes are labelled ESTIMATED with the profile version and timestamp until a live quote exists.
- PCBA classification comes from a dated catalogue export or live lookup; the hard-coded list is removed after migration and the two wrong entries are corrected now.
- Rotation and polarity conventions are per footprint, from a maintained offset table with pin-1 quadrant, applied per side.

## Work packages

| ID | Package | Owner | Cx |
|---|---|---|---|
| JL-01 | Versioned JSON fabrication profiles with provenance; `JLCPCBCapabilities` loads them; `ManufacturerProfile.get_preset` reads the same files | JLCPCB + SW | M |
| JL-02 | Preflight engine covering the Stage-5 list; aspect ratio and annular ring checked against actual vias; copper-to-edge against outline | JLCPCB + PCB | M |
| JL-03 | Fix `KNOWN_BASIC_PARTS` errors; classification by package + dated catalogue; `is_smt_eligible` from package and side | JLCPCB | S |
| JL-04 | Quote marked ESTIMATED with timestamp; live quote only through the documented API with credentials | JLCPCB | S |
| JL-05 | Release approval token and `EXTERNAL_DFM_PENDING` status in the readiness report | JLCPCB + QA | S |
| JL-06 | CPL rotation/polarity table per footprint with bottom-side handling | JLCPCB + PCB | M |
