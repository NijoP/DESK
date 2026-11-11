# EasyEDA Ecosystem Integration

**Inventory date:** 2026-11-12. **Primary ECAD:** EasyEDA Pro 3.2.149 with the API Gateway bridge (`easyeda-bridge`, HTTP on 127.0.0.1:49620, endpoints `/health`, `/eda-windows`, `/execute`). DESK adds intelligence, planning, verification and orchestration around EasyEDA's native capabilities; it does not replace them.

## Integration surfaces that exist

| Surface | File | Verified? |
|---|---|---|
| Gateway bridge (JS execution in the editor) | `desk/bridge.py` (`ex`, session cache, port discovery, `BridgeMutationTimeout`) | read-only getters live-verified 2026-11-11 (13 calls); mutations never live-verified |
| Library search (device → uuid, footprint, LCSC id) | `tools/resolve.py` via `eda.lib_Device.search` | used in practice (real uuids cached), no recorded verification |
| Symbol pin map extraction | `tools/pins.py` (places a symbol off-sheet, reads pins, deletes it) | used in practice; mutating |
| Schematic build / verify / clear | `tools/build.py`, `verify.py`, `clear_block.py` | workflow in incidents; no recorded transcript |
| PCB readback | `desk/adapters/easyeda_pcb_adapter.py` `build_batch_readback_script` (contains `openDocument` → not read-only), `tools/pcb_dump.py` | offline-tested |
| Placement apply | `tools/pcb_place.py` | mutating, unverified |
| Routing | `tools/route.py` (DSN export `pcb_ManufactureData.getDsnFile`, SES import `importAutoRouteSesFile`, widening, repour, readback) | one real run observed (no SES produced by the engine) |
| ERC/DRC | `tools/erc.py`, `tools/drc.py` (`pcb_Drc.check`), `pcb_Drc.getCurrentRuleConfiguration` (read live) | rules readable; checks unverified |
| Copper | adapter `build_create_zone_script`, `build_modify_zone_script`, `build_repour_all_script` | NOT_LIVE_VERIFIED |
| Exports | `tools/release.py` (Gerber, BOM, PnP, IPC-D-356A, netlist, PDF via `pcb_ManufactureData.*`) | unverified |
| CLI manager | `desk/eda/easyeda_pro.py` (doctor, protected projects WATCH/BEEBOX) | offline-tested; CLI not installed here |
| Component properties | `pcb_PrimitiveComponent.getAllPropertyNames` exposes `LCSC Part Name`, `Supplier Footprint`, `JLCPCB Part Class`, `Datasheet`, `Value`, `Voltage Rating` … | names read live; per-part values not retrieved yet |

## Workflow mapping (engineering intent → verified execution)

| Step | Native EasyEDA capability used | DESK contribution |
|---|---|---|
| 1 Requirements | — | `REQUIREMENTS.md` gates (validator planned PX-02) |
| 2 Components | library search, LCSC-linked devices | selection matrix, verification V1-V4, canonical records (LCSC architecture) |
| 3 Datasheets/pins | symbol pin numbers | provenance record; datasheet cross-check (LC-03/04) |
| 4 Libraries | device/footprint uuids | duplicate detection, versioning, footprint verification (COMPONENT_INTELLIGENCE_SPECIFICATION.md) |
| 5 Schematic | drawing via `build.py` chunks, save, revisions | block specs, lint, offline ERC |
| 6 Netlist | `netcheck.compare` against live sheet | spec-vs-live verification |
| 7 Placement | `pcb_place.py` | placement rules, dense-board analysis, authorised refinement |
| 8 Routing | DSN export, Freerouting, SES import | congestion intelligence, engine supervision, continuity |
| 9 Copper | pours and repour | power distribution plan, zone checks |
| 10 ERC/DRC | native engines | parsing, classification, recovery planning |
| 11 Manufacturing outputs | native exports | preflight, readiness report, approval gate |

## Rules of engagement

- Read before write; every mutation under `ops.write_op`; customer projects protected; disposable projects for live tests.
- While another terminal owns a project, DESK is read-only (procedure in `LIVE_EASYEDA_OBSERVATION_01.md`).
- `build_batch_readback_script` must gain a `read_only=True` mode that never calls `openDocument` (EE-01).
- Known gotchas from `learning/` are now indexed by the context engine; `importChanges` requires a saved schematic and a human Apply; rule tables are not writable through the API (per-net binding is).

## Work packages

| ID | Package | Owner | Cx |
|---|---|---|---|
| EE-01 | Read-only readback mode in the adapter (no `openDocument`), used by observation and verification | PCB | S |
| EE-02 | Per-component property readback (LCSC Part Name, Supplier Footprint, JLCPCB Part Class, Datasheet) through the documented getter | PCB + LCSC | S |
| EE-03 | Poured-copper geometry readback getter and `ZoneCheck` on real copper | PCB | M |
| EE-04 | Live verification transcripts for build/verify/erc/drc/export on a disposable project (QA-05) | QA | L |
| EE-05 | Library management: duplicate detection across `devices.json` / `canonical.db`, footprint pad-number verification against symbol pins | LCSC + PCB | M |
