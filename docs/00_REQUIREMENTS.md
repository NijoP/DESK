# 00 — Understanding the client requirement (before any part is chosen)

> **You cannot select a component until you can state, in numbers, what it must survive, fit into and do.**
> A requirement is only usable when it has a **value, a limit, a source and a status**.

## The mental model: translate words → numbers → constraints → decisions

```
Client words            "small battery sensor, lasts a year, works outdoors, cheap"
   ↓ ask / clarify
Numbers                 40x30 mm max, 1x CR2032 or 1S LiPo?, 365 days, -20..+60 °C, IP54, < $8 BOM @1k
   ↓ derive
Engineering constraints average current < 25 uA, no part taller than 3 mm, all parts rated -20..+60 °C,
                        sealed enclosure -> no airflow -> sensor self-heating matters
   ↓ decide
Architecture            sleep-capable MCU, nano-power LDO/buck, load switches on sensors, no LEDs always-on
   ↓
Block plan + BOM        (docs/00b_COMPONENT_SELECTION.md)
```

Never skip from "client words" to "parts". The middle two lines are the real engineering.

## The 10 requirement dimensions (fill every one — "unknown" is allowed, blank is not)

| # | Dimension | Questions to answer | Typical derived constraint |
|---|---|---|---|
| 1 | **Function** | What must it measure / control / display / communicate? Accuracy? Update rate? | sensor class & accuracy grade, MCU peripherals, ADC bits |
| 2 | **Electrical — supply** | Power source (USB, battery chem/size, adapter, PoE, solar)? Voltage range incl. worst case? Hot-plug? Reverse polarity possible? | input protection, regulator topology, min/max VIN of every part |
| 3 | **Electrical — budget** | Peak current, average current, sleep current, battery life target? | regulator Iq, load switches, cap sizes, battery capacity |
| 4 | **Interfaces** | Connectors to user/other boards, protocols, cable length, pinouts fixed by someone else? | connector family, ESD level, drivers, series R, pull-ups |
| 5 | **Mechanical** | Board outline, max height top/bottom, mounting holes, enclosure, connector positions, buttons/LED windows, weight | package sizes (0402/0201), low-profile inductors, connector orientation, keep-outs |
| 6 | **Environmental** | Temperature range (operating/storage), humidity, condensation, dust/water (IP), vibration, UV | temperature grade, conformal coat, sealed parts, capacitor dielectric (X7R vs X5R) |
| 7 | **Regulatory / safety** | Market (CE/FCC/UKCA), radio certification, battery transport (UN38.3), touch-safe voltages, medical/automotive? | pre-certified radio module, fuses/PTC, creepage, AEC-Q parts |
| 8 | **Manufacturing** | Quantity (proto / 1k / 100k), assembler (e.g. JLC PCBA), one- or two-sided assembly, test/programming method | basic/preferred parts, package limits, test pads, programming header |
| 9 | **Cost & supply** | Target BOM cost at volume, lifetime, second sources, stock risk | stock ≥ 10× build qty, avoid single-source/EOL, cheaper equivalents |
| 10 | **Lifecycle & firmware** | OTA updates? Field service? Variants? Future expansion? | flash size, spare GPIOs, DNI options, expansion header |

## How to interview the client (and what to do with missing answers)

1. Ask for **use-case stories**: "Walk me through one day of the product." Extract operating modes (off, sleep, active, charging, fault).
2. Ask for **limits, not wishes**: "What is the largest size that still works for you?" "What temperature does it really see?"
3. Ask what is **already fixed** by someone else: enclosure, connector, cable, display, existing firmware.
4. For every unanswered item, write a **working assumption** with status `PROVISIONAL` and the risk if wrong.
   Design so the assumption can change cheaply (DNI footprint, jumper, larger pad).
5. Play the requirements back as a table and get **written confirmation** (status `CONFIRMED`). Blocks that depend on a TBD item wait.

## Derivations you must write down (in REQUIREMENTS.md)

- **Power budget per mode**: list every load × current × duty → average current → battery life (with 20–30 % margin, battery derating at cold).
- **Voltage tree**: source → each rail, with min/max of every rail and which parts hang on it.
- **Worst-case input**: max VIN incl. transients (USB ≈ 5.5 V, plug-in spikes, battery charger at 4.2 V +), min VIN at end of battery life.
- **Mechanical envelope**: outline drawing with keep-outs, max component height per zone, connector positions with tolerances.
- **Thermal**: max dissipation per part (linear regulators: (Vin−Vout)·I), ambient max → junction temperature check.
- **Interface table**: every external pin: signal, direction, voltage level, current, ESD exposure.
- **GPIO / pin budget**: every MCU pin assigned or spare; boot/strap constraints; level at reset.

## Exit criteria (gate R) — only then start part selection

- [ ] All 10 dimensions filled (value or PROVISIONAL assumption with risk).
- [ ] Power budget, voltage tree, mechanical envelope, interface table written.
- [ ] Operating modes listed, including what must be OFF at reset and in fault.
- [ ] Client confirmed the table (date + name in REQUIREMENTS.md).
