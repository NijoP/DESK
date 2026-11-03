# 00b — Component selection mental model (BOM before schematic)

> **Every part on the BOM must be able to answer: which requirement needs me, which number proves I am
> adequate, and why I beat the alternatives.** If a part cannot answer, it does not go on the board.

## Selection order (big decisions constrain small ones)

```
1. Architecture parts      MCU / radio module, main sensors, display, battery  -> decide pins, rails, size
2. Power parts             protection, charger, regulators, load switches      -> decide rails & currents
3. Interface parts         connectors, ESD, level shifters, drivers            -> decide mechanics & robustness
4. Support ICs             RTC, muxes, logic, comparators, reset supervisors
5. Passives                derived from the datasheets of 1-4 (never chosen first)
6. Mechanical / misc       test pads, mounting, labels, DNI options
```

## The filter funnel (apply in this order, cheapest filter first)

| Step | Filter | Kill the candidate if… |
|---|---|---|
| F1 | **Function** | it does not do the job (protocol, range, accuracy, channels) |
| F2 | **Absolute maximum & operating range** | worst-case VIN/VIO/temperature is outside the **recommended operating** range (not abs-max) |
| F3 | **Performance with margin** | current, accuracy, speed, Iq do not meet the derived number with ≥ 20–50 % margin |
| F4 | **Size / height / package** | does not fit the mechanical envelope, or the assembler cannot place/inspect it (e.g. BGA on a 2-layer budget board) |
| F5 | **Availability** | stock < 10× build quantity, single source with no fallback, NRND/EOL, not in the assembler's library |
| F6 | **Cost** | breaks the BOM target at volume, or needs expensive extras (extra layers, special process) |
| F7 | **Ecosystem** | no reference design, poor datasheet, needs exotic firmware, no EasyEDA/LCSC symbol & footprint |

Keep **2–3 candidates** after F7 and fill the comparison matrix (`templates/BOM_SELECTION.md`). Choose, and write *why* in one line.

## Category rules of thumb

| Category | Key parameters to compare | Traps |
|---|---|---|
| MCU / radio module | cores, flash/PSRAM, GPIO count incl. spares, peripherals, sleep current, **pre-certified module** | strap pins, antenna keep-out, PSRAM eating GPIOs, 3.3 V-only IO |
| Linear regulator (LDO) | Vin max, dropout at I, Iq, PSRR, stability with ceramic caps | dissipation (Vin−Vout)·I, minimum Cout ESR |
| Switching regulator | Vin range, Iout, efficiency **at your load** (incl. light load), Iq, fsw, package thermal | Inductor Isat, layout loop, EN level, PG behaviour |
| Charger | chemistry, charge current, input current limit, power-path, NTC, timer | thermal at max charge current, status pins open-drain |
| Load switch / eFuse | Ron, current limit range, EN polarity (“-1/-2” variants!), reverse blocking | default state at reset |
| Sensor | accuracy over **your** range, self-heating, interface, supply range, sleep current | placement near heat, package openings, calibration |
| Connector | pitch, current per pin, mating cycles, locking, height, orientation, mating part MPN | mirror pinout on cable, SMT vs THT strength |
| ESD / TVS | working voltage ≥ signal max, clamping, capacitance (USB HS < 1 pF) | breakdown below signal level |
| Logic / mux | supply range, VIH/VIL vs driver, Ron, package | 5 V tolerance, floating inputs |
| Crystal | frequency, load capacitance CL, ESR vs MCU spec, tolerance | load cap formula |

## Passive selection — derived, never guessed

**Every passive comes from a formula or a datasheet recommendation, written in the block `qa`.**

### Resistors
- Value from the formula (divider, current set, LED, pull-up). Pick the nearest **E96 (1 %)** value, recompute the result with the chosen value.
- Tolerance: 1 % default; 0.1 % only where the formula's accuracy needs it (reference dividers, ID ladders).
- Power: P = I²R or V²/R; choose package with ≥ 2× margin (0402 ≈ 62.5 mW, 0603 ≈ 100 mW, 0805 ≈ 125 mW).
- Voltage rating for high-voltage nodes; pulse rating for inrush/surge resistors.
- Pull-ups: speed vs current (I²C: 2.2–10 k by bus capacitance and speed; GPIO default pull 10–100 k).
- Feedback dividers: keep divider current ≥ 100× FB pin leakage, but large enough for battery life.

### Capacitors (MLCC)
- **Dielectric**: X7R/X5R for decoupling/bulk, C0G/NP0 for timing, filters, crystals. Never Y5V/Z5U.
- **Voltage rating**: ≥ 1.5–2× the working voltage (DC-bias derating: a 10 µF 6.3 V 0402 at 5 V may be ~3 µF).
  Check the **effective capacitance at bias** from the manufacturer curve when the datasheet sets a minimum.
- Value: what the IC datasheet requires as **effective** capacitance; decoupling 100 nF per supply pin + bulk per rail.
- Package: smallest that still meets effective C and the assembler; keep one or two sizes across the board.
- Temperature: X7R for > 85 °C or outdoor.

### Inductors
- L from the regulator datasheet formula / table at your Vin, Vout, fsw.
- **Isat ≥ peak inductor current (Iout + ΔI/2) × 1.2–1.3**; Irms ≥ Iout; DCR for efficiency.
- Shielded for anything near sensors/RF; height vs mechanical envelope.

### Ferrites, fuses, diodes
- Ferrite: impedance at the noise frequency, DC current rating, DCR drop.
- Fuse/PTC: hold ≥ 1.25× normal current, trip below what the trace/connector/battery can survive.
- Schottky: Vr ≥ 1.5× max reverse, If with margin, leakage matters for battery products.

## Standardise the passive set (cost + assembly)

- Build a **preferred-value list** per product (e.g. 0R, 1k, 4.7k, 10k, 47k, 100k; 100 nF, 1 µF, 10 µF, 22 µF).
  Reuse it whenever the formula allows; new values need a reason.
- Prefer the assembler's **basic parts** (JLC basic = no extra feeder fee). Note LCSC codes in the spec (`lcsc`).
- One package family per board where possible (all 0402, power parts 0603/0805).

## What goes into the block spec (so the schematic and BOM are the same thing)

Each part in `blocks/NN_ID.json` carries: `mpn`, `lcsc`, `value`, `rating` (e.g. `"16V X5R"`, `"1% 62.5mW"`, `"Isat 2.6A"`),
`package`, `role` (what it serves, "at pin N"), and the `qa` entries prove the numbers.
`python tools/bom.py projects/<P>` then builds the BOM and flags any passive missing value/rating/package.

## Exit criteria (gate B) — only then start schematic blocks

- [ ] `BOM_SELECTION.md` has a comparison matrix and a one-line reason for every IC, connector, module, sensor.
- [ ] Every passive has formula/datasheet origin in its block `qa` or `role`.
- [ ] All parts resolve in EasyEDA (`tools/resolve.py`), stock checked, no EOL/NRND.
- [ ] `tools/bom.py` prints no warnings; BOM cost within target.
