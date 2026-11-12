# UPS_1000 — Requirements (Gate R: frozen before part selection)

Client: UPS-1000 Industrial Power Electronics Development Board (Captain's client spec + supplemental execution directive, 2026-11-12)
Confirmed by: builder (Claude Opus 5.5) under the Captain's written autonomous-execution authorisation. **Final release remains subject to Captain review.**
Method: docs/00_REQUIREMENTS.md. Tags: **CONFIRMED** (client-stated) · **PROVISIONAL** (builder engineering decision, documented, reversible) · **TBD** (missing; blocks whatever depends on it).

## 0. Scope split (the most important decision on this page)

| Scope | What | Status |
|---|---|---|
| **SYSTEM** (UPS-1000) | 1 kVA / 800 W online double-conversion UPS, 230 V AC 50 Hz out, 380 V DC link, PFC, full-bridge inverter 20 kHz + LC filter, 16S LiFePO4 battery, isolated CC/CV charger | **Architecture study only.** Not designed to manufacturing level in this run. HV/mains release **BLOCKED** (see §11). |
| **PROTOTYPE** (this PCB, rev A) | Low-voltage (SELV ≤ 60 V DC) controller + half-bridge development board fed from a current-limited lab supply | Designed, laid out, verified in this run. |

Nothing on the prototype PCB is connected to mains, the 380 V DC link or a 230 V output. No mains connector, no HV footprint is placed (directive §4 / §12).

## 1. Use case & operating modes (prototype)
Bench bring-up of inverter control firmware, gate-drive, current/voltage sensing and hardware protection on a safe bus voltage, before the separately reviewed HV power stage.

| Mode | Trigger | What is ON | Duration |
|---|---|---|---|
| OFF | lab supply off | nothing | — |
| STANDBY | VBUS ≥ LM5164 EN/UVLO rising threshold (1.5 V × 12 = **18.0 V**, falls at 16.8 V) | 12 V / 5 V / 3.3 V aux, MCU, CAN; gate driver **disabled** (DIS pulled high at reset) | indefinite |
| SWITCHING | firmware drives DIS low + PWM | half-bridge 20 kHz into external LC filter / load | lab sessions |
| FAULT | FAULT_N low (OC±, OT, OV comparator) | AND-gates force both gate inputs low within ns; TIM1 BKIN latches PWM off; FAULT LED on | until firmware clears |

## 2. Requirement table (10 dimensions)
| ID | Dimension | Requirement | Value / limit | Source | Status | Risk if wrong |
|---|---|---|---|---|---|---|
| R-01 | Function | Half-bridge test stage, isolated gate driver, I/V/T sensing, HW OC/OT/OV shutdown, STM32-class MCU | 20 kHz switching target; phase current ±10 A sense range; HW OC trip ±10 A | client §5 + builder calc | CONFIRMED (function) / PROVISIONAL (numbers) | wrong trip level |
| R-02 | Supply | Current-limited lab DC input | bring-up **24 V**; design operating range **20–58.4 V** (covers 16S LiFePO4 full charge); absolute design max 60 V (SELV); lab current limit ≤ 6 A | client §5 (24–48 V), directive §4 (24 V), builder extension to 58.4 V | PROVISIONAL | parts under-rated if >60 V applied |
| R-03 | Budget | Load current of the half-bridge test output | **5 A RMS continuous, 10 A peak** (HW trip) | builder decision (client gave none) | PROVISIONAL | conductor/thermal sizing |
| R-04 | Interfaces | UART, CAN, optional RS485, SWD, scope/instrument header, fan | UART 3-pin header, CAN (SN65HVD230, 120 Ω fixed termination), RS485 **not populated rev A**, SWD 5-pin, 8-pin instrument header, 12 V fan | client §5 | CONFIRMED / RS485 deferred | — |
| R-05 | Mechanical | Board envelope | 160 × 120 mm, 2.0 mm, 4 × M4 (Ø4.3 mm NPTH, 5 mm from edges), 4 layers, 2 oz outer / 1 oz inner | client §3 | CONFIRMED (stackup subject to fab check, §9) | — |
| R-06 | Environmental | Ambient | lab, **0–40 °C** ambient, forced air optional; indoor, non-condensing | builder assumption (client: "industrial", no number) | PROVISIONAL / **TBD for product** | derating basis |
| R-07 | Regulatory | Prototype: none claimed. System: IEC 62040-1 (safety), IEC 62040-2 (EMC), IEC 62040-3 (performance), IEC 60664-1 (insulation coordination) | — | client §7 | TBD (editions, see §11) | — |
| R-08 | Manufacturing | Qty / assembler | qty TBD; JLCPCB-class 4-layer process, top-side SMT assembly + hand-fit THT terminals | builder assumption | PROVISIONAL | — |
| R-09 | Cost & supply | BOM target | TBD (client gave none) | — | TBD | — |
| R-10 | Lifecycle | Firmware via SWD; rev B = HV power-stage split board | — | builder | PROVISIONAL | — |

## 3. Power budget (prototype, worst case, sources in BOM_SELECTION / block qa[])
| Load | Rail | Typ mA | Max mA | Note |
|---|---|---|---|---|
| UCC21520 VDDA+VDDB (Qg·f·2 + quiescent) | 12 V | 10 | 20 | Qg 64 nC max (BSC070N10NS3G) × 20 kHz × 2 = 2.6 mA + 2 × 2.5 mA |
| Fan | 12 V | 100 | 250 | client "forced air"; fan not specified → declared limit 250 mA |
| PWR LED | 12 V | 2 | 2.5 | |
| TPS54202 input (5 V branch at 85 %) | 12 V | 40 | 70 | |
| **12 V total** | **12 V** | **152** | **343** | LM5164 rated 1 A → 34 % |
| LM339 (moved to the **12 V** rail for input common-mode range) | 12 V | 1 | 2 | |
| AP2112K input (3.3 V loads) | 5 V | 70 | 130 | |
| STM32G431 (170 MHz, peripherals) | 3.3 V | 40 | 80 | |
| SN65HVD230 (dominant) | 3.3 V | 10 | 17 | |
| INA240, 74LVC2G08, UCC21520 VCCI, refs, LEDs | 3.3 V | 10 | 25 | |
| **3.3 V total** | **3.3 V** | **60** | **122** | AP2112K rated 600 mA → 20 % |
| Half-bridge load | VBUS | 5 A RMS | 10 A pk | external load via J7 |

## 4. Voltage tree (declared; DESK `voltage_rails` / `current_limits_A`)
| Rail | Source | Min | Typ | Max | Current limit (design) | Loads |
|---|---|---|---|---|---|---|
| VIN_RAW | J1 lab supply | 20 V | 24 V | 58.4 V (60 V abs) | 6 A (lab CL), fuse F1 | F1 |
| VBUS | F1 out, TVS D1 | 20 V | 24 V | 58.4 V | **10 A** (peak, HW trip) | half-bridge, LM5164 |
| PHASE / SW | half-bridge mid | 0 | — | VBUS | 10 A | shunt, J7 |
| 12V | LM5164 | 11.5 | 12.1 | 12.6 | 0.5 A | gate driver, fan, TPS54202 |
| 5V | TPS54202 | 4.8 | 5.0 | 5.2 | 0.3 A | LM339, AP2112K |
| 3V3 | AP2112K-3.3 | 3.2 | 3.3 | 3.4 | 0.3 A | MCU, CAN, INA240, logic |
| GND | single reference (see §10) | — | 0 | — | 10 A return | all |

## 5. Mechanical envelope
160 × 120 × 2.0 mm, 4 × M4 NPTH at (5, 5), (155, 5), (5, 115), (155, 115) mm with 9 mm keep-out circles (M4 washer Ø9). Power terminals (J1 input, J7 output) on the **left** short edge; comms (CAN, UART, SWD, instrument header) on the **right**/top edge; fan connector near the half-bridge. Heatsink: not required at 5 A (see §6); half-bridge FETs placed so a clip-on heatsink / airflow from a 40 mm fan can be added. Max height top: 20 mm (electrolytic caps / terminals).

## 6. Thermal check (calculated, at 5 A RMS, VBUS 58.4 V worst case, Ta 40 °C) — CALCULATED, not measured
| Part | Dissipation W | θJA used | Tj est. | Limit | Derivation |
|---|---|---|---|---|---|
| Q1/Q2 BSC070N10NS3G each | conduction I²·R·k = 25 × 7 mΩ × 1.5 (Tj 100 °C factor) × 0.5 duty = 0.13 W; switching ½·V·I·(tr+tf)·f = ½ × 58.4 × 10 × 40 ns × 20 kHz = 0.23 W (peak current used, conservative) → **≤ 0.36 W** | 50 K/W (4-layer 2 oz, ~6 cm² copper; datasheet RthJA 50 K/W on 6 cm²) | 40 + 18 = **58 °C** | 150 °C | qa in block 07 |
| R23 shunt 5 mΩ 2512 | 25 × 0.005 = 0.125 W (10 A pk 0.5 W transient) | — | — | 2 W rating → 6 % | |
| LM5164 | Pout 4 W at 85 % → 0.7 W total, IC share ~0.4 W | 40 K/W (DDA w/ pad) | 56 °C | 150 °C | |
| AP2112K | (5 − 3.3) × 0.122 = 0.21 W | 250 K/W (SOT-23-5) | 92 °C | 125 °C | margin OK at 40 °C ambient |
| F1, J1, J7 | I²R small | — | — | ratings §8 | |
Forced air: **not required** for the rev-A 5 A rating; fan header provided for the system-level thermal study. THERM-TJ-050 is **UNSUPPORTED** in DESK → these are hand calculations, recorded, not engine-verified.

## 7. External interface table
| Connector.pin | Net | Dir | Level | Current | ESD exposure |
|---|---|---|---|---|---|
| J1.1 / J1.2 | VIN_RAW / GND | in | 20–58.4 V | 6 A (10 A pk) | lab leads; TVS D1 |
| J7.1 | PHASE (via shunt) | out | 0–VBUS | 5 A RMS / 10 A pk | external LC filter / load |
| J7.2 / J7.3 | VBUS / GND | out | VBUS | 10 A | load return / split-cap |
| J7.4 | VOUT_EXT | in | ≤ 60 V | <1 mA | filtered output sense (divider 100k/5.1k) |
| J6.1/2/3 | CANH / CANL / GND | bidir | CAN | — | ESD D5 (NUP2105L) |
| J4.1/2/3 | UART_TX / UART_RX / GND | bidir | 3.3 V | — | lab only (EMI-ESD-062 advisory) |
| J3 SWD | 3V3/SWCLK/SWDIO/NRST/GND | — | 3.3 V | — | lab only |
| J9 instrument header | GND, PWMH_S, PWML_S, FAULT_N, ISENSE, VBUS_SNS, NTC_SNS, VOUT_SNS | out | 3.3 V | probe | lab only |
| J8 fan | 12V / FAN_N | out | 12 V | 0.25 A | — |

## 8. GPIO / pin budget (STM32G431CBT6, LQFP48) — final pins from library/pins/STM32G431CBT6.json + datasheet table
| Function | Pin | Constraint |
|---|---|---|
| PWM_H / PWM_L | PA8 TIM1_CH1 / PA7 TIM1_CH1N (AF6) | complementary, HW dead time |
| FAULT_N → TIM1_BKIN | PA6 (TIM1_BKIN AF6) | active-low |
| DRV_DIS | PB7 | pulled high externally (driver disabled at reset) |
| ISENSE / VBUS_SNS / VOUT_SNS / NTC_SNS | PA0 ADC12_IN1 / PA1 ADC12_IN2 / PB0 ADC1_IN15 / PB1 ADC1_IN12 | |
| CAN TX/RX | PA12 / PA11 (FDCAN1) | |
| UART TX/RX | PA2 / PA3 (USART2 AF7) | |
| FAN_PWM / FAULT_LED | PB6 / PB5 | |
| SWD | PA13 / PA14 | |
| BOOT0 | PB8-BOOT0 | 10 k pull-down |
(final mapping is in blocks/04_MCU.json, generated from the verified pin file — this table is the plan)

## 9. Stackup (client proposal — to be checked against the fab, not accepted blindly)
L1 signal/power (2 oz) · L2 GND (1 oz) · L3 power distribution (1 oz) · L4 signal/aux (2 oz), 2.0 mm total, FR-4 high-Tg (Tg ≥ 170 °C). Dielectric thicknesses: **TBD — fabricator stackup required** (e.g. JLCPCB 4-layer 2.0 mm with 2 oz outer is an orderable option but the exact prepreg/core build must be taken from the fab's quote). No controlled-impedance requirement on rev A (CAN 1 Mb/s, UART, SWD are electrically short) → impedance verification **N/A** and stated as such.

## 10. Ground and isolation (prototype)
* Single ground net **GND** (SELV ≤ 60 V everywhere). Power and control are separated by **placement** (power zone left, control right). L2 and L3 are GND planes, continuous except for the copper keep-out under the UCC21520 between its pad rows (the only intentional plane cut, 6.4 × 10.4 mm); the half-bridge hot loop closes on L1/L2 locally; the shunt is Kelvin-sensed by the INA240 (differential, so plane noise is common-mode).
* **The prototype has NO safety (galvanic) isolation.** The UCC21520's isolation barrier is preserved in copper (keep-out under the package between the input-side and output-side pin rows on all layers) so the same footprint/rules carry into the HV board, but both sides are referenced to GND on this board. This is functional, not protective, insulation; no isolation claim is made.

## 11. Missing / inconsistent requirements (reported to the Captain — none silently invented)
| # | Item | Finding | Impact | Status |
|---|---|---|---|---|
| M-01 | Battery voltage | "48 V nominal, 16S LiFePO4" is inconsistent: 16S × 3.2 V = **51.2 V nominal**, 58.4 V full (3.65 V/cell), ~40 V empty (2.5 V/cell). 15S = 48 V. | charger, DC-DC ratio, prototype rating | **TBD — client must confirm 15S or 16S**; prototype rated to 58.4 V to cover 16S |
| M-02 | Mains input range | single-phase, voltage range (230 V only? 100–240 V?), frequency (50/60), input current, inrush, PF target | PFC design, fuse, EMI filter | TBD |
| M-03 | Insulation coordination | working voltages per barrier, overvoltage category (II assumed typical for UPS but **not given**), pollution degree, material group/CTI, altitude (≤2000 m?), basic vs reinforced per barrier, earthing class (I/II) | creepage/clearance (IEC 60664-1), PCB slots | **TBD — blocks HV release** |
| M-04 | Standard editions | IEC 62040-1 edition (2017+A1:2021?), 62040-2 (2016?), 62040-3 (2021?), IEC 60664-1 (2020 ed. 3) | rule tables | TBD — editions must be confirmed by the client/compliance engineer; DESK tables marked UNVERIFIED |
| M-05 | Output spec | THD limit, load PF range (0.8?), crest factor, transient response, overload profile (e.g. 125 %/1 min), transfer time (0 for online) | inverter/filter design | TBD |
| M-06 | Battery runtime / charger current | 20 Ah given, but charge current (C/5 = 4 A?), runtime at 800 W (51.2 V × 20 Ah × 0.9 ≈ 920 Wh → ~1 h at 800 W) not specified | charger power | TBD |
| M-07 | DC-DC battery ↔ 380 V link | topology (isolated? bidirectional DAB?) not specified; required if battery is not on the DC link | block 6 | TBD |
| M-08 | Ambient / altitude / IP / cooling airflow | "industrial", "forced air" with no °C, CFM or fan spec | derating, heatsink | TBD (prototype assumes 0–40 °C lab) |
| M-09 | Prototype load current | not given | conductor sizing | builder PROVISIONAL 5 A RMS / 10 A pk |
| M-10 | Prototype half-bridge vs full-bridge | client §5 says half-bridge test interface (kept); system is full bridge | firmware portability | CONFIRMED half-bridge |
| M-11 | EMC test plan, surge levels (IEC 61000-4-x) | not given | input filter | TBD |
| M-12 | Quantity, assembler, cost | not given | DFM | TBD |
| M-13 | Stackup dielectric thicknesses | not given; client asked for verification | creepage through PCB, thermal | TBD (fab data) |

## 12. Gate R decision
Gate R is **PASSED for the low-voltage prototype only** with the PROVISIONAL values above (each is a documented, reversible builder decision under the Captain's authorisation). Gate R is **NOT PASSED for the system / HV design**: M-01..M-08 and M-11 are open, so no HV schematic block, HV footprint or HV spacing rule is produced in this run.

## 13. Design risks found during the run (open, not waived)
| # | Risk | Evidence | Rev-A handling | Rev-B action |
|---|---|---|---|---|
| RK-01 | **Reverse polarity is NOT safely protected.** With the lab current limit (≤ 6 A) below the 7 A fuse, a reversed supply forward-biases the SMBJ60A at the current limit; the fuse may never open and the TVS dissipates ~VF × I (several W) until it fails (possibly short). | examiner interim review; fuse 7 A vs CL 6 A | Bring-up procedure: first power-up with the lab current limit ≤ 0.5 A and polarity checked; the claim "fuse opens" in block 01 qa is withdrawn | series P-MOSFET or ideal-diode controller |
| RK-02 | TVS clamp 96.8 V (at IPP) exceeds INA240 CM ROC 80 V and leaves 3 % to the 100 V FET/LM5164 ratings | DATASHEET_FACTS SMBJ60A, INA240 | lab supply only, no field surges | lower-voltage TVS or 150 V parts for battery-connected use |
| RK-03 | OV comparator trip 60.0 V nominal (≈ 57.7–62.2 V with tolerances) can nuisance-trip at 16S full charge 58.4 V; no hysteresis | examiner recompute | irrelevant at the 24 V bring-up | move trip to ≥ 62 V with hysteresis |
| RK-04 | Comparators have no hysteresis / hardware latch: fault is cycle-by-cycle, the latch is firmware-configured TIM1 BKIN | block 08 qa | documented; firmware must enable BKIN before PWM | hardware latch (SR flip-flop) |
| RK-05 | Shoot-through current flows Q1→Q2 without passing the phase shunt R24, so OC comparators do not see it | topology | dead time 200 ns HW + TIM1 dead time | add a DC-link (low-side return) shunt |
