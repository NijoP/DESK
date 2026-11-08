---
name: pcb-engineering
description: Electrical correctness rules, IPC-2152 trace sizing, layer stackups, and copper weights.
triggers:
  - "stackup"
  - "trace width"
  - "ipc-2152"
  - "copper thickness"
  - "impedance"
inputs:
  net_current: float
  layer_type: string
  delta_t: float
outputs:
  trace_width_mm: float
  copper_weight_oz: float
authoritative_pipeline: M1/M5
replay_safety: READ_ONLY
---

# PCB Engineering Skill

## Purpose
Enforces electrical correctness, board geometry constraints, copper layer stackups, and physical IPC trace derivations before geometry synthesis.

## When to Use
- Determining track widths, via drill sizes, and clearances for power or high-speed nets.
- Defining or modifying a `DesignProfile` layer stackup.
- Sizing copper pours or thermal spokes based on net current capacity.

## Required Inputs
- Layer stackup parameters (layer count, dielectric thickness, copper ounce rating).
- Net electrical parameters (operating current, voltage rating, allowed temperature rise $\Delta T$).

## Relevant DESK Modules
- `desk/profile.py`: Stackup definition and IPC-2152 track width calculation engine.
- `desk/copper.py`: Offline copper plane and power polygon synthesizer.

## Required Engineering Constraints
- Do not silently modify electrical calculation constants or formula derivations.
- Internal signal and plane layers must adhere strictly to specified dielectric thickness.
- Trace width must never fall below fabricator minimums ($0.127\,\text{mm}$ standard).

## Recommended Workflow
1. Load project profile: `DesignProfile.load("projects/<P>/profile.json")`.
2. Compute trace width: Call `profile.trace_width(net_name, layer, current_a)`.
3. Verify return paths against reference plane stackup (`L2` solid GND for `L1` microstrips).
4. Derive thermal spoke geometry for high-current pads to balance soldering and thermal dissipation.

## Validation Steps
- Execute electrical rule calculations: `python -m unittest tests/test_profile.py`.
- Run electrical sanity checks across netlist current ratings.

## Failure Conditions & Recovery
- Trace width under-sizing: Recalculate with $\Delta T = 10^\circ\text{C}$ ceiling; report unroutable widths to Captain.
- Stackup mismatch: Reconcile fabricator capability definitions.

## Expected Output
- Mathematically verified trace width, clearance, and stackup constraints recorded in project profile.

## Documentation References
- [Requirements Guide](file:///docs/00_REQUIREMENTS.md)
- [BOM Selection Guide](file:///docs/00b_COMPONENT_SELECTION.md)
