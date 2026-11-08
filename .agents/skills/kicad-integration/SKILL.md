---
name: kicad-integration
description: KiCad schematic and PCB import/export adapters, netlist conversion, and CLI validation.
triggers:
  - "kicad"
  - "kicad_pcb"
  - "netlist conversion"
  - "specctra"
  - "dsn export"
inputs:
  kicad_file_path: string
  target_format: string
outputs:
  conversion_status: boolean
  exported_artifact: string
authoritative_pipeline: INFRA
replay_safety: SAFE_IDEMPOTENT
---

# KiCad Integration Skill

## Purpose
Manages cross-platform bidirectional conversion between DESK internal models, KiCad sexpr schematics/PCBs, and Specctra DSN routing netlists.

## When to Use
- Importing an existing KiCad project into DESK.
- Exporting a DESK routed design to `.kicad_pcb` format for 3D raytracing or manufacturing.
- Translating board geometry to Specctra `.dsn` format for external autorouting engines.

## Required Inputs
- Path to source `.kicad_pcb` or `.kicad_sch` file.
- Layer stackup mapping between KiCad and DESK `DesignProfile`.

## Relevant DESK Modules
- `desk/adapters/kicad_adapter.py` (or KiCad translation bridges).
- `SpecctraStructure.class` / DSN generator.

## Required Engineering Constraints
- Netlist Consistency: Intersystem netlist translation must preserve 100% of net and pin associations without renaming.
- Footprint Geometry Invariance: Component pad coordinates, drill diameters, and copper geometries must match down to $0.001\,\text{mm}$.
- Cross-Platform File Paths: Handle Windows vs. Linux path separators transparently without escaping errors.

## Recommended Workflow
1. Parse source KiCad sexpr AST.
2. Validate layer mappings against `DesignProfile`.
3. Extract footprint definitions and translate coordinates to DESK internal board model.
4. Run DRC verification on imported geometry.
5. Export verified updates back to `.kicad_pcb` or `.dsn`.

## Validation Steps
- Execute KiCad adapter tests: `python -m unittest discover -s tests -p "test_*kicad*.py"`.
- Verify sexpr grammar compliance: `kicad-cli pcb check` (if available on PATH).

## Failure Conditions & Recovery
- Sexpr parsing syntax error: Roll back to last valid revision; inspect unsupported KiCad token version.
- Unmatched footprint pad: Abort translation and log missing library footprint to `LEDGER.md`.

## Expected Output
- Bit-exact, compliant `.kicad_pcb` or `.dsn` netlist artifact matching DESK engineering rules.

## Documentation References
- [Architecture Guide](file:///docs/architecture/00_SYSTEM_ARCHITECTURE.md)
