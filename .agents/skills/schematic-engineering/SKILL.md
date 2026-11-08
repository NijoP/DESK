---
name: schematic-engineering
description: Procedural workflow for schematic generation, netlist compilation, and symbol connectivity verification.
triggers:
  - "schematic"
  - "netlist"
  - "symbol"
  - "pinout"
  - "connectivity"
  - "wire"
inputs:
  netlist_data: dict
  profile: DesignProfile
outputs:
  compiled_schematic: dict
  unconnected_pins: list
  net_count: integer
authoritative_pipeline: M1
replay_safety: SAFE_IDEMPOTENT
---

# Schematic Engineering Skill

## Purpose
Governs the creation, verification, and compilation of electrical schematics into typed netlists and design profile rules.

## Procedural Execution Checklist

1. **Intake Pin & Net Declarations**:
   - Parse component reference designators, pin numbers, and pin electrical types (Input, Output, Power, Bidirectional, Passive).
   - Ensure power rails (e.g., `+3V3`, `+5V`, `VIN`, `GND`) have explicit voltage ratings in `DesignProfile`.
2. **Net Connectivity Rules**:
   - Verify that all IC power pins have matching decoupling cap connections.
   - Detect floating or unterminated inputs.
   - Disallow conflicting output-to-output connections without explicit open-drain pullups.
3. **Invoke M1 Schematic Engine**:
   - Execute `desk.schematic.compile_netlist(netlist_data, profile)`.
4. **Evidence Generation**:
   - Produce schematic validation record in `evidence_ledger`.
   - Forward validated netlist to M2 placement engine.
