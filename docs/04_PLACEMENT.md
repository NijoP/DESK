# 04 — Component placement mental model

Placement is also **data with reasons**: `projects/<P>/placement.json`, one line per part,
`[ref, x_mm, y_mm, rot, "T"|"B", "reason"]`. No reason → the part is not placed.
Applied with `tools/pcb_place.py`, checked with `tools/pcb_check.py`.

## Order (always this order)

1. **Board outline + mechanics** — size, mounting holes, slots, keep-outs, enclosure features.
2. **Fixed parts** — connectors, buttons, LEDs that face a window, sensors that need airflow/ports, antennas.
   Their position comes from the mechanics, never from routing convenience.
3. **ICs, hand-placed** — in **signal-flow order**, the same left→right order as the schematic blocks
   (power in → regulators → MCU → interfaces → outputs). Rotate each IC so the pins that talk to a
   neighbour **face** that neighbour.
4. **Passives, snapped to the pin they serve** (`passives` list: `[ref, anchor_ic, pin, why]`).
   The cap/resistor sits just outside the IC body, on the escape side of that pin, axis along the escape direction.
5. **Everything else** fills remaining space near the parts it shares nets with.

## Rules of thumb

| Topic | Rule |
|---|---|
| Decoupling | smallest cap closest to the pin; ≤ 2 mm (`decap_max_mm`), same side as the IC, GND via at the cap |
| Switching regulators | input cap → IC → inductor → output cap as one tight loop on one side; feedback divider near FB pin, away from SW node |
| Heat & sensors | temperature/humidity sensors ≥ 7 mm from regulators, MCU, chargers; thermal slots if needed |
| RF | MCU antenna at board edge, no copper/parts in keep-out area on any layer |
| Connectors | ESD diode directly behind the connector pins, before anything else |
| Crystals | next to the MCU pins, short symmetric traces, no signals under |
| Sides | big/tall parts on top; bottom for small passives only if assembly cost allows |
| Grid | 0.05 mm grid; uniform rotations (0/90/180/270) within a row of passives |
| Spacing | ≥ 0.25–0.4 mm body-to-body for 0402/0201 (assembler DFM), more around tall parts |
| Silkscreen | designators hidden or tidy; keep board labels and polarity marks |

## Loop

```
pcb_dump.py  ->  edit placement.json  ->  pcb_place.py --dry (review numbers)  ->  pcb_place.py
             ->  pcb_dump.py  ->  pcb_check.py  ->  EasyEDA DRC (placement clearance)  ->  screenshot top/bottom -> commit
```
