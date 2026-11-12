# UPS_1000 rev A — Component selection (Gate B)

Method: docs/00b_COMPONENT_SELECTION.md filters F1–F7. Every selected MPN resolved by `tools/resolve.py` against the live EasyEDA/LCSC library (exact name match) and its pin map probed by `tools/pins.py` (`library/pins/<MPN>.json`). Datasheet facts: `live-test/ups-1000/requirements/DATASHEET_FACTS.md` (manufacturer PDFs; mirrors flagged).
**Stock and price are NOT stated anywhere in this package**: DESK has no live stock/price feed in this run and none are invented (F5/F6 are recorded as "LCSC part exists in the EasyEDA library", not as stock).

Legend: ✔ pass · ✘ fails the filter · ? not assessed (no evidence in this run).

## 1. Half-bridge MOSFET (Q1, Q2)
Need: VDS ≥ 1.25 × 58.4 V → ≥ 73 V → 100 V class; ID ≫ 10 A pk; logic for 12 V drive; SMD power package with exposed drain.

| Candidate | F1 | F2 | F3 | F4 | F5 | F6 | F7 | Note |
|---|---|---|---|---|---|---|---|---|
| **Infineon BSC070N10NS3 G** (C501502) | ✔ | ✔ 100 V | ✔ 7 mΩ max @10 V, 55 nC max | ✔ TDSON-8 5×6 | ✔ in library | ? | ✔ full datasheet Rev 2.2 | **chosen** |
| TI CSD19534Q5A (C114200) | ✔ | ✔ 100 V | ✔ 12.6 mΩ class | ✔ VSON 5×6 | ✔ in library | ? | ✔ | fallback, same footprint class (not drop-in pad-compatible: verify) |
Why: lowest RDS(on) of the resolved candidates, RthJA 50 K/W on 6 cm² documented, Tj 150 °C.

## 2. Gate driver (U7)
| Candidate | F1 | F2 | F3 | F4 | F5 | F6 | F7 | Note |
|---|---|---|---|---|---|---|---|---|
| **TI UCC21520DWR** (C601651) | ✔ dual isolated, HS/LS, DT pin, DIS | ✔ VDD 9.2–25 V @12 V | ✔ 4 A/6 A | ✔ SOIC-16W | ✔ | ? | ✔ Rev F 2024 | **chosen**: same driver scales to the 380 V stage (VIOTM 8 kV, CPG >8 mm) |
| Non-isolated bootstrap driver (e.g. UCC27211) | ✔ | ✔ | ✔ | ✔ | ? | ? | ✔ | rejected F1 for this client: spec asks for an *isolated* gate-driver test interface |
Note: UCC21520 (8 V UVLO) vs UCC21520A (5 V UVLO): 8 V UVLO protects 10 V-rated gate drive; chosen.

## 3. Current sense (U8 + R24)
| Candidate | F1 | F2 | F3 | F7 | Note |
|---|---|---|---|---|---|
| **TI INA240A1PWR** + 5 mΩ 2512 | ✔ bidirectional, PWM rejection | ✔ CM −4…80 V | ✔ ±16 A FS at gain 20 | ✔ | **chosen**: phase-leg sensing tolerates the SW node swing |
| INA181 low-side | ✘ F1: low-side only, no PWM CM rejection | | | | rejected |

## 4. Aux 12 V buck (U1)
| Candidate | F1 | F2 | F3 | F4 | F5 | F7 | Note |
|---|---|---|---|---|---|---|---|
| **TI LM5164DDAR** | ✔ | ✔ VIN 6–100 V vs 58.4 V (TVS clamp 96.8 V) | ✔ 1 A vs 0.34 A | ✔ SO-8 PP | ✔ | ✔ Rev D 2026 | **chosen** |
| TPS54360 (60 V) | ✔ | ✘ F2: 60 V abs vs 58.4 V operating + transients, no margin | | | | | rejected |

## 5. Aux 5 V buck (U2) / 3V3 LDO (U3)
| Candidate | Result | Note |
|---|---|---|
| **TI TPS54202DDCR** | ✔ F1–F4, F7 (VIN 4.5–28 V from 12 V, 2 A vs 0.13 A) | chosen |
| **Diodes AP2112K-3.3TRG1** | ✔ 600 mA vs 0.122 A, Pd 0.21 W | chosen (already in DESK library, used before) |

## 6. MCU (U4)
| Candidate | F1 | F3 | F7 | Note |
|---|---|---|---|---|
| **ST STM32G431CBT6** | ✔ TIM1 complementary PWM + dead time + BKIN, 2 × 12-bit ADC, FDCAN, comparators/DAC | ✔ 170 MHz | ✔ (DS12589 Rev 2 mirror — later revision must be checked) | **chosen**: G4 is ST's power-conversion line |
| STM32F103C8 | ✘ F1: bxCAN only, no HRTIM/comparators, weaker ADC | | | rejected |

## 7. Protection comparator (U9), logic gate (U6), CAN (U5)
| Part | Result |
|---|---|
| **TI LM339DR** | ✔ quad, open collector (wired-OR), supply 2–30 V; supplied from 12 V so the CM range (0…VCC−2 V) covers all 3.3 V inputs |
| **TI SN74LVC2G08DCUR** | ✔ dual AND, 3.3 V, gates PWM with FAULT_N in hardware |
| **TI SN65HVD230DR** | ✔ 3.3 V CAN, high-speed mode |

## 8. Protection / passives (derivations are in each block's `qa[]`)
| Part | Selection basis |
|---|---|
| SMBJ60A TVS | VRWM 60 V ≥ 58.4 V; VC 96.8 V ≤ 100 V rating of FET / LM5164 (3 % margin, surge only) |
| 0451007.MRL fuse | 7 A fast ≥ 1.25 × 5 A; opens on reverse polarity (TVS forward). **Fuse datasheet not retrieved (littelfuse.com 403): rating, I²t and voltage rating TO VERIFY** |
| Vishay MAL214099812E3 100 µF 100 V | V derating 58 %; **ripple-current rating TO VERIFY** (2.5 A RMS bus ripple shared with 3 × 2.2 µF MLCC) |
| Samsung CL32B225KCJSNNE 2.2 µF 100 V 1210 | hot-loop MLCC, 58 % V derating; DC-bias capacitance loss accepted |
| PA2512FKF7W0R005E 5 mΩ 2 W | 0.125 W at 5 A RMS (6 %) |
| NCP18XH103F03RB NTC | 10 k, B 3380 K (XH series — datasheet TO VERIFY) |
| STPS1H100A bootstrap diode | 100 V ≥ 70.4 V (70 %); datasheet used = STPS1H100-Y automotive variant (commercial A TO VERIFY) |
| 0603 resistors | 75 V element rating ≥ 58.4 V on R1/R3/R27 (VBUS/VOUT dividers) |
| Terminal blocks WJ128V-5.0 (2P/4P) | **current/voltage rating TO VERIFY** from the KANGNEX datasheet (needs ≥ 10 A) |
| Headers HDR-M 2.54 (1×2/3/5/8) | generic EasyEDA headers: **no LCSC code** in the library → supplier part TO ASSIGN |
| Crystal X322512MSB4SI 12 MHz | load capacitance assumed 20 pF from the part code → **TO VERIFY**; 30 pF load caps derived |

## 9. Open verification items (block release; none hidden)
V-01 fuse datasheet · V-02 electrolytic ripple rating · V-03 terminal block rating · V-04 crystal CL · V-05 NTC B value · V-06 commercial STPS1H100A datasheet · V-07 STM32G431 current datasheet revision · V-08 header LCSC parts · V-09 electrolytic polarity mark vs pad 1 on footprint · V-10 inductor Isat (SWPA6045S470MT ≥ 1.5 A, SWPA4030S100MT).
