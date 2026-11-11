# Hardware Compatibility Matrix

Per category, seven criteria: **Input** (can the requirement be expressed in DESK's data model), **Model** (verified electrical model), **Constraints** (design constraints derived), **Execution** (tool that applies them), **Verification** (independent check), **Example** (realistic project or template in the repo), **Tests** (regression). Status per the capability-matrix legend. Evidence in `HARDWARE_AND_PCB_ENGINEERING_ASSESSMENT.md`.

## A. Power electronics

| Topology | Input | Model | Constraints | Execution | Verification | Example | Tests | Overall |
|---|---|---|---|---|---|---|---|---|
| Buck | block JSON + qa formulas | no switching-loop, Isat or SW-node area model | width/thermal-relief heuristics | EasyEDA + Freerouting | live DRC only | none (02_PWR_3V3 is an LDO placeholder) | none | PARTIALLY_IMPLEMENTED |
| Boost | same | same | same | same | same | none | none | PARTIALLY_IMPLEMENTED |
| Buck-boost, forward, flyback, full-bridge, dual-active-bridge | no isolation barrier, transformer or HV net-pair voltage input | none | clearance tops out at 24 mil above 50 V; no creepage | — | — | projects/LIGHT (230 V AC) carries ≥ 3 mm spacing as free text | none | MISSING (unsafe to claim) |
| Motor drivers / high-current stages | "MOTOR" regex → UNKNOWN → 1 A | none | no via or pour ampacity | — | — | none | none | MISSING |

## B. Embedded systems

| Item | Input | Model | Constraints | Execution | Verification | Example | Tests | Overall |
|---|---|---|---|---|---|---|---|---|
| ESP32 | pin caches, fine-pitch escape | escape analysis | fine-pitch width/clearance | route.py | SES connectivity | Project One / WATCH | `test_routing_e2e_project_one.py` | PARTIALLY_IMPLEMENTED (no strap-pin or antenna-keepout model) |
| STM32 | no pin cache | — | — | — | — | none | none | MISSING |
| USB (FS/HS) | diff pair in pcb_rules.json | no 90 Ω or skew model | EasyEDA rule object | EasyEDA | none in DESK | WATCH USB_DP/DM | none | PARTIALLY_IMPLEMENTED, NEEDS_HARDWARE_VALIDATION |
| I2C / SPI / UART | regex stage-4 scheduling | pull-up guidance in docs | none | route.py | none | WATCH | none | IMPLEMENTED_UNVERIFIED |
| CAN / Ethernet | regex "TX|RX" only | no 120/100 Ω, no magnetics keep-out | none | — | — | none | none | MISSING |

## C. RF engineering

| Item | Status | Note |
|---|---|---|
| Antenna interface | PARTIALLY_IMPLEMENTED | `rf_edge_mm` 0.5 mm and keep-out rectangles only; no copper clearance under antenna |
| RF transmission lines, controlled impedance | MISSING | stackup εr/thickness stored, never consumed |
| Ground clearance / stitching | PARTIALLY_IMPLEMENTED | fixed 2.54 mm stitching grid, not λ-based |
| Shielding constraints, matching networks | MISSING | no model |

## D. High-speed digital

| Item | Status | Note |
|---|---|---|
| Differential pairs | PARTIALLY_IMPLEMENTED | detection and EasyEDA rule only |
| Impedance constraints | MISSING | |
| Length matching / skew | MISSING | `DiffPairVerification` never instantiated |
| Return-path continuity | PARTIALLY_IMPLEMENTED | 5-point sample against zone outline, ignores real copper |
| Via stubs / back-drill | MISSING | |

## E. Analog and mixed-signal

| Item | Status | Note |
|---|---|---|
| ADC/DAC, precision analog | PARTIALLY_IMPLEMENTED | sensor-vs-heat distance rule; `current_sense` role tag |
| Kelvin connections, guard rings | MISSING | |
| AGND/DGND partition check | MISSING | |
| Low-noise supplies | PARTIALLY_IMPLEMENTED | supply-cap presence ERC only |

## F. Mechanical and manufacturing

| Item | Status | Note |
|---|---|---|
| Board dimensions | PARTIALLY_IMPLEMENTED | rectangle only; outline lost in DSN |
| Mounting holes | PARTIALLY_IMPLEMENTED | auto corner placement, keep-out box; no annular clearance |
| Connector positioning | VERIFIED (offline) | edge + front keep-out rules |
| Slots, cut-outs | MISSING | |
| Fabricator presets (JLCPCB, PCBWay) | PARTIALLY_IMPLEMENTED | min width/clearance/drill stored; annular ring and aspect ratio never checked against actual vias |
| Assembly (PnP, BOM, CPL) | VERIFIED (offline) | `component_intelligence`, release exports untested live |
| Panelisation | MISSING | |

## Claims DESK must not make today

- Universal topology support. Isolated and mains-referenced converters are outside the clearance model.
- "IPC-2152" widths. The formula is IPC-2221.
- Verified differential-pair or RF design. Only EasyEDA's own rule engine enforces anything.
- Manufacturing readiness beyond "DRC clean and all nets routed".

## Priority to reach "professional" coverage

1. H-01 clearance/creepage model (unlocks isolated and mains topologies safely).
2. H-02 unknown-current fail-closed and H-03 profile-driven widths (unlocks high-current work).
3. H-04 diff-pair verification and H-05 impedance calculator (unlocks USB, RF, high-speed).
4. H-06 via ampacity and thermal vias (motor drivers, power stages).
5. H-08 real outline and slots to the router (mechanical).
6. Example projects per category with regression tests (QA-01).
