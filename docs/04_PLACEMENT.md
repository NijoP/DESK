# 04 — Component Placement Mental Model & Intelligence Engine

> **Placement decides 80 % of routing quality, EMC, thermal behaviour and assembly yield.**
> Routing can only connect what placement made connectable. Place with reasons, check with numbers.

Placement in DESK follows a strict engineering hierarchy:
```
MECHANICAL INTEGRITY
  ↳ FOOTPRINT INTEGRITY
    ↳ ELECTRICAL INTEGRITY
      ↳ FUNCTIONAL PLACEMENT
        ↳ ROUTABILITY OPTIMISATION
          ↳ BOARD-AREA OPTIMISATION
```
The engine never sacrifices a hard mechanical or electrical requirement merely to obtain better routing efficiency.

---

## 1. The Autonomous Placement Hierarchy

```
1 MECHANICAL ANCHORS  Board outline, mounting holes, standoffs, enclosure keep-outs, height zones
2 CONNECTORS & SCREW   External connectors with mating envelopes; screw terminals with screwdriver access cones
3 CRITICAL ICs         Central controllers, PMICs, sensors placed with pin escape corridors
4 FUNCTIONAL CLUSTERS  Power conversion, main control, sensor acquisition, RF, audio, drivers
5 TOPOLOGICAL PASSIVES Decoupling caps (<2 mm to IC pins), ESD at connectors, crystal loops, RC filters
6 ROUTABILITY GATE     Ratsnest crossings, MST wirelength estimation, escape congestion scoring
7 PLACEMENT FREEZE     Immutable SHA-1 snapshot in state/placement_frozen.json and LEDGER.jsonl
```

---

## 2. Component Intelligence Extraction & Footprint Invariants

Every component placed on the PCB is governed by immutable properties extracted via `ComponentIntelligenceExtractor` and `FootprintIntegrityEngine`:
- **Footprint Invariants**: Pad count, pad numbering, pad relative coordinates, pad pitch, shapes, and drill definitions are strictly validated. Moving or rotating a component never alters its pin-to-net mapping. Mirrored footprints undergo explicit pin-mapping validation.
- **Component Classification**:
  - **Mechanical Anchors**: Connectors, FPC, USB, RJ45, Screw terminals, Mounting holes, Buttons, Displays.
  - **Primary ICs**: MCUs, PMICs, Motor drivers, Regulators, Sensors, Communication ICs.
  - **Supporting Passives**: Decoupling capacitors, pull-ups/downs, series resistors, RC filters, crystals.
  - **Special Electrical**: Current-sense resistors (Kelvin), switching loops, RF, differential pairs.

---

## 3. Mechanical-First Envelopes

### Connector Placement
- Placed flush or along board edge with mating direction facing outward.
- **Front Keep-Out**: Plug insertion envelope and cable exit corridors are protected. No other components may occupy this envelope (`MechanicalEnvelope.get_connector_mating_envelope`).
- **ESD Protection**: Placed immediately behind connector pins before reaching ICs (≤ 3.0 mm).

### Screw-Terminal Placement
- **Screwdriver Access Corridor**: Clear vertical/tool cone corridor above and facing terminal screws (`screwdriver_depth_mm = 12.0 mm`). Prohibits blocking physical operation.
- **Wire Entry Corridor**: Unobstructed corridor for wire insertion, bending, and terminal tightening.

### Mounting Holes & Standoffs
- Protected screw heads, washers, standoffs, and tool clearance margins (`standoff_dia_mm + tool margin`). Prohibits traces, vias, or component bodies within the keepout circle.

---

## 4. Topological Passive Snapping

Passives are snapped according to their electrical circuit topology:
- **Decoupling Capacitors**: Positioned immediately adjacent to IC power supply pins (`decap_max_mm = 2.0 mm`) to minimize high-frequency supply-to-ground loop areas.
- **Crystal Oscillators**: Minimum loop area directly adjacent to MCU oscillator pins, surrounded by ground guards.
- **RC Filters**: Filter resistors and capacitors kept together at the destination pin.
- **Feedback Dividers**: Positioned tight to regulator feedback pins, isolated from noisy switching inductors.

---

## 5. Routability Evaluation & Placement Acceptance Gate

Before routing begins, `tools/pcb_check.py --gate` verifies:
1. **Mechanical Access**: Zero intrusion into screwdriver or connector mating corridors.
2. **Footprint Invariants**: Zero altered pad counts or pitch distortions.
3. **Electrical Clearance**: Decoupling distances, thermal spacing, and keepout compliance.
4. **Routability Metrics**:
   - **Ratsnest Crossings**: Minimization of planar crossings between straight-line connections.
   - **MST Wirelength**: Multi-terminal Minimum Spanning Tree length estimation.
   - **Pin Escape Congestion**: Perimeter escape ratio for fine-pitch QFN/BGA packages.
5. **Freeze Snapshot**: `tools/pcb_check.py --freeze` locks the verified placement into `state/placement_frozen.json` with an immutable SHA-1 hash recorded in `LEDGER.jsonl`.

## Placement-routing co-optimisation (added 2026-11-12)

`desk/placement_refine.py` proposes minimal moves of unlocked passives that reduce predicted
routing congestion while preserving anchors, decoupling proximity, keep-outs and body clearances.
Proposals are written to `placement.json` only when explicitly authorised; see
`docs/engineering/PLACEMENT_ROUTING_COOPTIMISATION.md`.
