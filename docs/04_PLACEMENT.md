# 04 — Component placement mental model

> **Placement decides 80 % of routing quality, EMC, thermal behaviour and assembly yield.**
> Routing can only connect what placement made connectable. Place with reasons, check with numbers.

Placement is **data with reasons**: `projects/<P>/placement.json`, one line per part `[ref, x_mm, y_mm, rot, "T"|"B", "reason"]`
(no reason → not placed). Applied with `tools/pcb_place.py`; every rule below marked **[checked]** is enforced by
`tools/pcb_check.py` (`desk/placement.py`) with the numbers in the `rules` section of placement.json.

---

## 1. The order of placement (never change the order)

```
1 MECHANICS      outline, holes, slots, enclosure features, keep-outs, height zones          (fixed by others)
2 FIXED PARTS    connectors, buttons, LEDs/light pipes, displays, sensors with ports, antenna (fixed by the product)
3 CRITICAL LOOPS switching regulators, RF feed, crystals, USB/high-speed pairs               (fixed by physics)
4 ICs            in signal-flow order, rotated so pins face the neighbour they talk to
5 PASSIVES       snapped to the pin they serve                                                (fixed by the ICs)
6 THE REST       pull-ups, test points, fiducials, logos — in the space that is left
7 BALANCE        density, free space, thermal spread, assembly side — then review
```
Each step constrains the next. Moving a connector after passives are placed means redoing steps 3–7.

## 2. Zones before parts — partition the board

Before placing a single IC, draw (mentally or as `zones` in placement.json) the functional regions:
**power entry → power conversion → digital core → interfaces → analog/sensors → RF**.
- Keep **noisy** (switchers, motor drivers, clocks) and **sensitive** (analog front ends, sensors, RF, crystals) zones apart,
  with the digital core in between.
- Signal flow should be a short line, not a loop: input connector on one side, output on the other.
- One ground plane under everything (no split); zones are for *placement*, not for cutting ground.

## 3. Connectors  **[checked: edge distance, front keep-out, board containment]**
- On the **board edge**, body flush with or slightly overhanging the outline per the mechanical drawing
  (`connector_edge_mm`, default 1.0 mm from edge to body).
- **Mating side faces outward**; nothing in the **front keep-out** (cable bend, plug body, fingers):
  `connector_front_keepout_mm` (default 3 mm) — no parts between connector and edge.
- Group connectors by function; same-side connectors share a mechanical datum.
- **ESD / TVS directly behind the connector pins**, before any other part on that net (≤ 3 mm,
  `esd_max_mm`); then series resistors / common-mode chokes; then the IC.
- Through-hole or mid-mount connectors need mechanical anchoring (shell tabs, screws); keep SMD parts ≥ 1 mm from
  shell tabs (`connector_clearance_mm`) — rework and mating forces crack nearby MLCCs.
- Board-to-board / FPC connectors: check mating height and pin-1 orientation against the mating board (mirror!).

## 4. Sensors  **[checked: distance from heat sources, edge/port position if declared]**
- **Temperature / humidity**: away from every heat source (`sensor_heat_mm`, default 7 mm from regulators,
  inductors, MCU, chargers, LEDs, power resistors), near the board edge / enclosure vent; thermal slot around it if
  the board is small. No copper pour under the sensor if the datasheet says so; no vias under it.
- **Gas / pressure / microphone**: aligned with the enclosure port (port position is mechanical = fixed part);
  sealed port gasket area free of parts.
- **Light / proximity**: aligned with the window; no tall parts within the field of view cone.
- **Analog sensor front ends**: short traces from sensor to ADC/AFE, away from switching nodes and clocks; reference
  and its decoupling right at the ADC.
- **Magnetic / current sensors**: away from inductors and high-current loops (or deliberately over the conductor).

## 5. RF and antennas  **[checked: keep-out zones on all layers, antenna at edge]**
- Module / chip antenna **at the board edge or corner**, antenna end overhanging or flush per the module datasheet.
- Respect the **antenna keep-out** on **every layer**: no copper, no parts, no traces, no ground pour
  (declare it in `keepouts` → any part body inside is an error).
- No metal (batteries, connectors, shields, screws) in the antenna near field — typically ≥ 10–15 mm.
- RF matching network (π-network) directly at the RF pin, in line, 50 Ω feed as short as possible.
- Solid ground under the module body with stitching vias; GND via fence along RF feed.
- Crystals: next to the MCU pins (≤ 3 mm), load caps between crystal and pins, no signals underneath, ground guard.

## 6. Power and thermal  **[checked: heat-source spacing, sensor distance]**
- Switching regulator loop first: **input cap → IC → inductor → output cap** on one side, smallest loop area;
  the hot loop (Cin + switch) is the tightest.
- Feedback divider at the FB pin, on the quiet side, away from SW node and inductor.
- **Spread heat sources** (`heat_spacing_mm`, default 3 mm between hot parts); don't stack them in one corner; give
  exposed pads thermal vias to inner planes; keep heat away from electrolytics, crystals, sensors, battery.
- High-current path: connector → protection → regulator in a straight line, wide copper, few layer changes.

## 7. Passives — snapped to the pin they serve  **[checked: decap distance, same side, orientation]**
| Passive | Where | Rule |
|---|---|---|
| Decoupling cap | at the supply pin it decouples | smallest value closest; ≤ 2 mm (`decap_max_mm`); same side as IC; via to GND at the cap, not shared |
| Bulk cap | at the rail entry of the block | ≤ 5 mm from the regulator output / IC cluster |
| Regulator Cin/Cout | at VIN / VOUT pins | part of the hot loop, no via in the loop |
| Feedback divider | at FB pin | short FB trace, divider ground at IC GND pin |
| Pull-up / pull-down | at the receiving pin or the bus end | not critical in distance; group them in a row |
| Series termination R | **at the driver** (source) | ≤ 3 mm from driver pin |
| ESD diode | **at the connector** | before anything else on that net |
| Crystal load caps | between crystal and MCU pins | symmetric |
| Filter / RC | in the signal path order | input → R → C → pin, as drawn in the schematic |
- Align passives in **rows with the same rotation** (0/90 only; 180/270 only for polarised parts), on a common grid
  (0.05 mm, rows on 0.25 mm). Orthogonal rotations only **[checked]**.
- Polarised parts (diodes, LEDs, tantalum, electrolytic) all with the same polarity direction in a group.
- Put passives on the **same side** as their IC unless density forces bottom side; bottom side = smallest parts only.

## 8. Pad-to-pad and body-to-body spacing  **[checked]**
Minimum distance between pads of **different** components (copper to copper), and between component bodies.
Defaults below are conservative for typical PCBA (e.g. JLC standard); **confirm with your assembler's DFM guide** and
set them in `rules`:

| Between | pad-to-pad (mm) | body-to-body (mm) | why |
|---|---|---|---|
| 0201 ↔ 0201 | 0.20 | 0.15 | stencil web, bridging |
| 0402 ↔ 0402 | 0.25 | 0.20 | |
| 0603+ passives | 0.30 | 0.25 | |
| passive ↔ IC (QFN/SOIC/SOT) | 0.30 | 0.25 | |
| IC ↔ IC | 0.40 | 0.30 | inspection angle, rework |
| anything ↔ BGA / fine-pitch QFN (≤ 0.5 mm pitch) | 0.50 | 0.50 | X-ray, rework nozzle |
| anything ↔ connector / tall part (> 3 mm) | 0.50 | 1.00 | AOI shadow, rework, mechanical stress |
| anything ↔ THT pad | 0.50 | — | wave/selective solder |
| copper ↔ board edge | 0.30 (pads) / 0.50 (planes) | — | depaneling (V-score needs ≥ 0.5 mm) |
Rule: the required clearance between two parts is the **larger** of their two class values.

## 9. Density, over-population and free space  **[checked: utilisation, hotspots, empty regions]**
Measure, don't guess. `pcb_check.py` computes per side:
- **Utilisation** = component body area / usable board area. Guide values:
  < 25 % sparse (board could be smaller) · 25–45 % comfortable · 45–60 % dense (needs via-in-pad / 4 layers) ·
  > 60 % over-populated (routing and rework will fail) → `max_utilisation` (default 0.55) **error**.
- **Hotspots**: a grid cell (`density_cell_mm`, default 2.5 mm) ≥ 85 % covered (`hotspot_fill`) with ≥ 4 equally crowded
  neighbours (`hotspot_neighbours`) → local over-population; routing channels blocked.
- **Free space**: the largest empty region. A large empty region on a board that also has hotspots means the layout is
  **unbalanced** → spread the hotspot into it. Empty regions are fine when they are deliberate (antenna keep-out,
  mechanical clearance, future expansion) — declare them as `keepouts`/`reserved` so they are not reported.
- **Pin density** (pins per cm²) is the real routing demand; > ~25 pins/cm² on a 2-layer board or > ~45 on 4-layer
  needs finer rules.
- Leave **routing channels**: between IC rows keep ≥ 1 mm free where many signals must pass.

## 10. DFM / DFT / mechanical  **[checked: board containment, height zones if declared]**
- All parts inside the outline minus edge clearance; no parts on V-score / tab / mouse-bite zones.
- **Height zones** from the enclosure (`height_zones` with `max_mm`, parts' heights in `heights`).
- 3 fiducials per side with components (global), local fiducials for fine-pitch parts; 1 mm copper-free ring.
- Test points for every rail, every programming/debug signal, key signals; ≥ 1.27 mm pitch, one side if possible.
- Tooling holes / panel rails per assembler.
- Silkscreen: polarity, pin 1, connector function labels, board name/revision; never on pads.

## 11. Review checklist (in this order)
1. Mechanics: outline, holes, connectors, height zones match the drawing.
2. `tools/pcb_check.py` → **PLACEMENT OK** (all rules above).
3. Ratsnest: no long crossings between zones; buses straight; power path straight.
4. Hot loop areas small; FB and sensitive nodes on the quiet side.
5. Thermal: heat sources spread, sensors far.
6. RF: keep-out empty on all layers, antenna at edge.
7. EasyEDA DRC (placement clearance) 0 errors; top/bottom screenshots reviewed by a human; commit.

## Loop
```
pcb_dump.py → edit placement.json → pcb_place.py --dry → pcb_place.py → pcb_dump.py → pcb_check.py → DRC → review → commit
```
