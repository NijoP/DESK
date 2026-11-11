# ESP32 IoT C2/C3 Performance Specification

**Programme:** 225-minute design-to-manufacturing-readiness for an average ESP32 IoT board. **Owner:** Product Manager. **Technical authority:** Principal Hardware Architect. **Status:** benchmark definitions proposed here for freeze; measurement framework defined; no end-to-end timed run has been performed yet (see `ESP32_BENCHMARK_BASELINE.md`).

## 1. Time matrix (mandatory targets, frozen benchmark workload)

| Stage | Acceptance gate | Target |
|---|---|---:|
| 1 Schematic and electrical validation | schematic built, ERC and engineering checks complete, component identities and pin maps validated, critical issues resolved or documented | 45 min |
| 2 Component placement | mechanical and electrical placement checks pass; predicted routing difficulty inside the envelope | 45 min |
| 3 Routing and connectivity | 100 % populated-net connectivity physically verified, zero unintended shorts, no new critical DRC, diff-pair constraints verified, power traces meet calculated widths | 90 min |
| 4 Copper pouring and zones | correct nets/layers, no shorts, no unresolved islands, ground continuity, power distribution verified, thermal connections reviewed | 30 min |
| 5 Manufacturing preflight | all applicable checks pass, files generated and validated, no critical blockers; human approval before any order | 15 min |
| **Total** | senior hardware engineer accepts the design | **225 min** |

Timers never reset after a failure; retries count. A stage is complete only when its gate passes. Missing client inputs, supplier outages and mandatory external reviews are recorded separately, not hidden.

## 2. Benchmark workload profiles (to be frozen by the Hardware Architect)

Complexity is defined by electrical, mechanical, thermal, routing and manufacturing requirements, not by component count alone.

### ESP32 IoT C2 — Standard

| Requirement | Specification |
|---|---|
| MCU | ESP32-WROOM-32E or ESP32-S3-WROOM-1 module, castellated, antenna keep-out at one board edge |
| Power input | USB-C 5 V (CC pull-downs) **or** single-cell Li-ion with JST connector; selectable at freeze |
| Regulation | 3.3 V LDO or buck ≥ 600 mA; declared currents for 5 V, 3.3 V |
| Protection | input TVS, reverse-polarity or ideal-diode where battery is used, ESD on exposed interfaces |
| Sensors | one I²C environmental sensor, one SPI or I²C IMU |
| Interfaces | UART debug header, I²C header, 2 × user buttons, reset, boot |
| Indicators | 2 × LEDs with series resistors |
| Programming | USB-serial bridge **or** direct USB (S3), auto-reset circuit |
| Passives | decoupling per datasheet, pull-ups, strapping resistors |
| Board | 2 layers, ≤ 50 × 50 mm, 4 × M2.5 mounting holes, JLCPCB standard 2-layer profile |
| Routing | USB differential pair (if direct USB), I²C/SPI, power trunks ≥ 1 A |
| Thermal | regulator dissipation budget declared; copper area per watt reviewed |

### ESP32 IoT C3 — Advanced

C2 plus:

| Requirement | Specification |
|---|---|
| Power | USB-C and battery with charger + power-path (e.g. BQ25895 class), 3.3 V buck, 1.8 V LDO, boost 5 V rail; four declared rails |
| Sensors | three or more: IMU, environmental, ambient light or microphone (I²S) |
| Audio/analogue | I²S DAC + Class-D amplifier or ADC front-end with its own analogue ground region (no split by default; isolation by placement) |
| Interfaces | USB (direct), UART, I²C, SPI display connector (FPC), SD card |
| Connectors | USB-C, battery, FPC, header, 2 × JST sensor ports |
| Board | 4 layers (Top / GND plane / 3.3 V plane / Bottom), ≤ 45 × 35 mm, mounting holes, one board-edge slot or cut-out |
| Routing density | ≥ 20 pads/cm², ≥ 2 fine-pitch (≤ 0.5 mm) packages, ≥ 60 nets, ≥ 200 ratsnest crossings at placement acceptance |
| Grounding | continuous GND plane; stitching; return paths for USB and I²S verified |
| Manufacturing | JLCPCB 4-layer profile with impedance-controlled USB pair; PCBA basic/extended part classification in the BOM |

The synthetic fixtures `esp32_4layer` and `mcu_2layer_compact` (`desk/routing/fixtures.py`) are geometry stand-ins for the routing-stage benchmark until the frozen designs exist in EasyEDA. The WATCH project is a real-world reference only.

## 3. Measurement framework

- Stage timers in `desk/runtime/projection.py` already carry 12 canonical stages; the five programme stages map onto them (schematic = stages 1-4, placement = 5-7, routing = 8-10, copper = 11, preflight = 12-13).
- Every tool run is already logged to `.desk_learn/runs.jsonl` (tool, args, return code, duration). The time report aggregates these per stage per run.
- Time accounting categories: DESK active execution, model inference, external API latency, engineering calculation, human intervention, external waiting, rework/recovery, wall clock. Model and API latency come from the router accounting (AI-03); human intervention is logged when a tool prompts for a manual EasyEDA step.
- P50 / P90 over ≥ 3 repeated runs per profile; measured vs estimated values are labelled.

## 4. What cannot be achieved by a faster model

Stage 3 wall clock is dominated by Freerouting passes (6-42 s each on WATCH) and EasyEDA DRC passes (up to 600 s each); Stage 1 by human-in-the-loop EasyEDA dialogs and library resolution; Stage 5 by export and readback. The levers are the ones implemented and planned in `docs/engineering/CONGESTION_OPTIMISATION.md` and `PRODUCT_ROADMAP.md`, not model choice.

## 5. Freeze procedure

The Hardware Architect reviews this specification, selects the C2 power-input option, confirms rail currents, and records the freeze in `projects/BENCH_C2/REQUIREMENTS.md` and `projects/BENCH_C3/REQUIREMENTS.md` (to be created as disposable projects, never a customer project). Benchmarks run only against frozen requirements.
