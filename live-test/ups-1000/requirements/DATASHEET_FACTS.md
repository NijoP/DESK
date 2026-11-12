# Datasheet Facts — ups-1000 prototype

Retrieved 2026-11-12. Every value below was read from the datasheet named for that part. Page numbers ("p") are PDF page numbers. **NOT FOUND** means the datasheet does not state the fact. Nothing here was estimated.

> **Sourcing caveats**
> - **st.com and littelfuse.com did not respond or refused the request** (time-outs and HTTP 403), so three parts come from mirrors:
>   - STM32G431: LCSC mirror of **DS12589 Rev 2 (Oct 2019)**. ST has published later revisions. Check against the current revision before releasing.
>   - STPS1H100A: the LCSC listing (C165701) links to the **STPS1H100-Y (automotive, AEC-Q101) datasheet**, Doc ID 17935 Rev 1. The SMA part in that document is STPS1H100**AY**, not the commercial STPS1H100A.
>   - SMBJ60A: a Littelfuse-authored PDF (Revised 06/03/20), downloaded from a copy attached to a TI E2E forum post.
> - All TI and Infineon datasheets came directly from the manufacturer.

---

## 1. TI UCC21520 / UCC21520A (DW, SOIC-16 wide)
URL: https://www.ti.com/lit/ds/symlink/ucc21520.pdf — **SLUSCJ9F, Rev F, November 2024**

| Fact | Value | Source |
|---|---|---|
| Pinout | 1 INA, 2 INB, 3 VCCI, 4 GND, 5 DISABLE, 6 DT, 7 NC, 8 VCCI (shorted internally to pin 3), 9 VSSB, 10 OUTB, 11 VDDB, 12 NC, 13 NC, 14 VSSA, 15 OUTA, 16 VDDA | §5, Fig 5-1 / Table 5-1, p4 |
| VCCI range | 3 V to 18 V | §6.3 ROC, p5; §10, p38 |
| VDDA/VDDB range | UCC21520A (5-V UVLO): 6.5 V to 25 V. UCC21520 (8-V UVLO): 9.2 V to 25 V | §6.3 ROC, p5 |
| VDD UVLO, 5-V version (UCC21520A) | Rising 5.7 / 6.0 / 6.3 V; falling 5.4 / 5.7 / 6.0 V; hysteresis 0.3 V (min / typ / max) | §6.8 EC, p8 |
| VDD UVLO, 8-V version (UCC21520) | Rising 7.7 / 8.5 / 8.9 V; falling 7.2 / 7.9 / 8.4 V; hysteresis 0.6 V | §6.8 EC, p8 |
| VCCI UVLO | Rising 2.55 / 2.7 / 2.85 V; falling 2.35 / 2.5 / 2.65 V; hysteresis 0.2 V | §6.8 EC, p8 |
| DIS pin | **Active high**: high disables both outputs; low or open enables them. Pulled low internally. TI recommends tying it to GND if unused, and a 1 nF bypass cap at the pin when it is driven from a distant MCU. Internal pull-downs on the inputs are typically 200 kΩ (block diagram shows 200 kΩ). | Table 5-1 p4; §8.4.1 p23; §8.3 p21; Fig 8 block diagram p18 |
| DT behaviour and formula | t_DT (ns) = 10 × R_DT (kΩ), with R_DT from 2 kΩ to 500 kΩ between DT and GND (Eq. 1). Put 1 nF in parallel with R_DT when R_DT > 5 kΩ. DT pin sits at about 0.8 V. EC check points: R_DT = 10 k gives 80/100/120 ns, 20 k gives 160/200/240 ns, 50 k gives 400/500/600 ns. | Table 5-1 p4; §8.4.2.2 p23; §6.10 p9 |
| DT tied to VCCI | No dead time is inserted and the outputs may overlap; overlap follows INA/INB | §8.4.2.1 p23; p9 |
| DT floating | "It is not recommended to leave the DT pin floating." §7.4 says "leaving the DT pin open … sets a dead-time interval" but gives no value. | Table 5-1 p4; §8.4.2.2 p23; §7.4 p16 |
| VCCI bypass | ≥100 nF minimum (MLCC, 50 V suggested). Add >1 µF tantalum/electrolytic in parallel if the supply is far away. | §10 p38; §9.2.2.7.1 p31 |
| VDD bypass | 10 µF plus 100 nF ceramic between VDDx and VSSx, close to the pins. Example design uses a 1 µF bootstrap cap plus 100 nF X7R. | §10 p38; §9.2.2.7.2 p32 |
| VIOTM | 8000 V_PK | §6.6 Insulation Specs, p7 |
| VIORM | 2121 V_PK (AC bipolar). VIOWM = 1500 V_RMS / 2121 V_DC. | §6.6, p7 |
| Clearance / creepage (DW) | CLR > 8 mm; CPG > 8 mm. DTI > 17 µm. CTI > 600 V. | §6.6, p7 |
| Peak output current | 4 A source, 6 A sink | §1 p1; §6.9, p9 |

## 2. TI INA240A1 (PW, TSSOP-8; gain 20 V/V)
URL: https://www.ti.com/lit/ds/symlink/ina240.pdf — **SBOS662C, Rev C, December 2021**

| Fact | Value | Source |
|---|---|---|
| Pinout (PW) | 1 NC, 2 IN+, 3 IN−, 4 GND, 5 VS, 6 REF2, 7 REF1, 8 OUT. IN+ goes to the supply side of the shunt and IN− to the load side. NC may be grounded or left floating. | §6, Fig 6-1 / Table 6-1, p3 |
| Supply (VS) | 2.7 V to 5.5 V | §7.3 ROC, p4 |
| Common-mode range | −4 V to 80 V | §7.3 p4; §7.5 p5 |
| Gain | A1 = 20 V/V | Table 5-1 p3; §7.5 p5 |
| Bidirectional mid-supply | Connect one REF pin to VS and the other to GND. OUT then sits at VS/2 with 0 V input (ratiometric). Alternatively tie REF1 and REF2 together to an external reference. Reference input range is 0 to VS. Reference divider accuracy is 0.02% typ, 0.1% max. | §8.4.3.2 p14; §8.4.3 p13; §7.5 p5 |
| Output swing | To VS: VS − 0.05 V typ, VS − 0.2 V max. To GND: GND + 1 mV typ, GND + 10 mV max (RL = 10 kΩ, −40 to 125 °C). | §7.5 p5–6 |
| Recommended input filter | The datasheet says input filters are **not required and not recommended**. If used, keep each series resistor ≤ 10 Ω (Fig 9-1). A filter cap value is NOT FOUND. TI suggests filtering at the output instead. | §9.1.1 p18 |

## 3. TI LM5164 (DDA, SO-8 PowerPAD)
URL: https://www.ti.com/lit/ds/symlink/lm5164.pdf — **SNVSAU4D, Rev D, February 2026**

| Fact | Value | Source |
|---|---|---|
| Pinout | 1 GND, 2 VIN, 3 EN/UVLO, 4 RON, 5 FB, 6 PGOOD (open drain, 10–100 kΩ pull-up), 7 BST, 8 SW. EP is not connected internally; tie it to GND copper. | §4 Table 4-1, p3 |
| VIN range | 6 V to 100 V | §5.3 ROC, p4 |
| Output current | 1 A (ROC I_LOAD 1 A nom, 1.25 A max). Peak current limit 1.5 A typ; valley 1.2 A typ. | §5.3 p4; §5.5 p6 |
| VREF (FB) | 1.181 / 1.2 / 1.218 V | §5.5 EC, p5 |
| RON / fsw | F_SW (kHz) = V_OUT (V) × 2500 / R_RON (kΩ) (Eq. 1/12). t_ON (µs) = R_RON (kΩ) / (V_IN (V) × 2.5) (Eq. 11). Maximum f_SW is 1 MHz. | §6.3.1 p10; §6.3.5 p12 |
| Min on / off time | Min on-time 50 ns. ROC t_ON range is 50–10000 ns. Min off-time 50 ns typ, forced to 250 ns when t_ON < 300 ns. | §6.1 p9; §5.3 p4; §6.3.7 p13 |
| Ripple injection | Required: ≥ 20 mV ripple at FB, in phase with the inductor current. Type 1 = series R_ESR. Type 2 = R_ESR + C_FF. Type 3 = R_A/C_A from SW plus C_B AC-coupled into FB (the user's "Rr/Cr/Cac"). | §6.3.1 p10; Table 6-1 p11 |
| Type-3 formulas | C_A ≥ 10 / (F_SW × (R_FB1 ∥ R_FB2)) (Eq. 7). R_A·C_A ≤ t_ON@VIN-nom × (V_IN-nom − V_OUT) / 20 mV (Eq. 8). C_B ≥ t_TR-settling / (3 × R_FB1) (Eq. 9). The operator between R_FB1 and R_FB2 in Eq. 7 did not survive text extraction; parallel is assumed. Check the drawn equation. | Table 6-1, p11 |
| BST cap | 2.2 nF, 50 V X7R, required. ABS range is 1.5–2.5 nF; a larger value can damage the device. | Table 4-1 p3; §5.1 p4; §6.3.2 p12 |
| EN/UVLO | Below 1.1 V typ: shutdown, 3 µA. 1.1–1.5 V: standby. Enable rising 1.45 / 1.5 / 1.55 V; falling 1.35 / 1.4 / 1.44 V. Shutdown threshold rising 1.1 V; falling 0.45 V. | Table 4-1 p3; §5.5 p5; §6.3.9 p13 |

## 4. TI TPS54202 (DDC, SOT-23-6)
URL: https://www.ti.com/lit/ds/symlink/tps54202.pdf — **SLVSD26C, Rev C, February 2026**

| Fact | Value | Source |
|---|---|---|
| Pinout | 1 GND, 2 SW, 3 VIN, 4 FB, 5 EN, 6 BOOT | §4 Table 4-1, p3 |
| VIN range | 4.5 V to 28 V (ABS 30 V). VIN UVLO rising 4.2 V typ, falling 3.7 V typ. | §5.3 p4; §5.5 p5 |
| Iout | 2 A continuous | §1 p1 |
| Vref (VFB) | 0.581 / 0.596 / 0.611 V | §5.5 p5 |
| fsw | 500 kHz fixed (390 / 500 / 630 kHz), with spread spectrum. Minimum on-time 110 ns typ. | §5.5 p5; §5.6 p5; §1 p1 |
| L and Cout for 5 V out | Reference design (8–28 V in, 5 V / 2 A): L = 15 µH (L_MIN calculated as 13.7 µH, K_IND = 0.3). C_OUT = 2 × 22 µF 25 V X7R. Feedback R2 = 100 kΩ, R3 = 13.3 kΩ; C6 = 75 pF feed-forward; C_IN = 10 µF + 0.1 µF. | §7.2 Fig 7-1 p13; §7.2.3.5 p15–16 |
| BOOT cap | 0.1 µF ceramic, BOOT to SW | Table 4-1 p3; §7.2.3.2 p14 |
| EN | Internal pull-up current, so a floating EN enables the part. Drive it with open-drain/open-collector logic. Rising threshold 1.21 / 1.28 V, falling 1.1 / 1.19 V. I_EN = 0.7 µA at 1 V; hysteresis current 1.55 µA. ROC is −0.1 to 5.5 V; ABS max 7 V. | Table 4-1 p3; §6.3.5 p9; §5.5 p5; §5.1/5.3 p4 |

## 5. ST STM32G431CBT6 (LQFP48)
URL (mirror): https://datasheet.lcsc.com/datasheet/pdf/3f23d741047d660d2a0e8aabbc953854.pdf?productCode=C529355 — **DS12589 Rev 2, October 2019** (official URL https://www.st.com/resource/en/datasheet/stm32g431cb.pdf did not respond)

| Fact | Value | Source |
|---|---|---|
| Power pins (LQFP48) | VBAT 1; VSSA 19; VREF+ 20; VDDA 21; VSS 23, 35, 47; VDD 24, 36, 48 | §4.4 Fig 8, p45 |
| Decoupling ("Power supply scheme") | VDD: n × 100 nF plus 1 × 4.7 µF. VDDA: 10 nF + 1 µF. VREF+: 100 nF + 1 µF. VBAT: 1.55–3.6 V. Each supply pair must have ceramic decoupling as close as possible to the pins. | §5.1.6 Fig 16, p68 |
| VREF+ rule | If VDDA < 2 V, VREF+ = VDDA. If VDDA ≥ 2 V, VREF+ must be between 2 V and VDDA. VREF− is double-bonded to VSSA. | §3.11.1 p22 |
| BOOT0 / PB8 | Pin 45, PB8-BOOT0. The BOOT0 level comes either from the PB8-BOOT0 pin or from the nBOOT0 option bit, chosen by the nBOOT_SEL option bit. Together with nBOOT1 it selects boot from user Flash, system memory (bootloader: USART/I2C/SPI/USB DFU) or SRAM. Note 5: set PB8 to a non-analog mode after startup if it is left unconnected. | §3.5 Boot modes p19; Table 12 p59 note 5 |
| NRST | Pin 7 (PG10-NRST). Recommended **0.1 µF** external capacitor from NRST to GND, placed close to the device. Internal R_PU is present. | Fig 27 p121; Fig 8 p45 |
| TIM1_CH1 | PA8, pin 30, AF6 | Table 13 p61 |
| TIM1_CH1N | PA7, pin 15, AF6. Also PA11 (pin 33, AF6) and PB13 (pin 27, AF6). | Table 13 p61–62 |
| TIM1_BKIN | PA6, pin 14, AF6. Also PB12 (26, AF6), PA14 (38, AF6), PA15 (39, AF9), PB8 (45, AF12), PB10 (22, AF12). | Table 13 p61–62 |
| FDCAN1_RX / TX | RX: PA11, pin 33, AF9. TX: PA12, pin 34, AF9. Alternative pair: PB8 (45) RX / PB9 (46) TX, AF9. | Table 13 p61–62 |
| USART2 TX / RX | TX: PA2, pin 10, AF7. RX: PA3, pin 11, AF7. Alternatives: PA14 / PB3 for TX and PA15 / PB4 for RX, all AF7. | Table 13 p61–62 |
| SWD | SWDIO: PA13, pin 37, AF0. SWCLK: PA14, pin 38, AF0. | Table 13 p61; Fig 8 p45 |
| HSE | OSC_IN: PF0, pin 5. OSC_OUT: PF1, pin 6. | Fig 8 p45; Table 12 p51 |
| ADC-capable pins | PA0, pin 8: ADC12_IN1. PA1, pin 9: ADC12_IN2. PB0, pin 16: ADC1_IN15. PB1, pin 17: ADC1_IN12. | Table 12 p51–53 |

## 6. TI SN65HVD230 (D, SOIC-8)
URL: https://www.ti.com/lit/ds/symlink/sn65hvd230.pdf — **SLOS346O, Rev O, April 2018**

| Fact | Value | Source |
|---|---|---|
| Pinout | 1 D (TXD), 2 GND, 3 VCC, 4 R (RXD), 5 Vref (VCC/2 output), 6 CANL, 7 CANH, 8 RS | §7 Pin Functions, p5 |
| RS modes | Strong pull-down to GND: high-speed mode. 10–100 kΩ to GND: slope control (10 kΩ ≈ 15 V/µs; 100 kΩ ≈ 2 V/µs). Strong pull-up to VCC (V_RS ≥ 0.75 VCC): low-power standby (listen-only; driver off, receiver on; 370 µA typ). | §7 p5; §5 p4; §8.3 p6; §1 p1 |
| Supply | 3.0 V to 3.6 V (ABS −0.3 to 6 V). Bus common-mode range −2 to 7 V. | §8.3 ROC p6; §8.1 p5 |

## 7. TI LM339 (D, SOIC-14)
URL: https://www.ti.com/lit/ds/symlink/lm339.pdf — **SLCS006Z, Rev Z, May 2025**

| Fact | Value | Source |
|---|---|---|
| Pinout | 1 OUT1, 2 OUT2, 3 VCC, 4 IN2−, 5 IN2+, 6 IN1−, 7 IN1+, 8 IN3−, 9 IN3+, 10 IN4−, 11 IN4+, 12 GND, 13 OUT4, 14 OUT3. The datasheet notes that some vendors swap the names of channels 1 and 2; the pinout is electrically identical. | §5 Table 5-1, p4 |
| Supply range | LM339 (non-B): 2–30 V (ROC). LM339B: 2–36 V. | §6.5 / §6.4, p6 |
| Input CM range | LM339: 0 to VCC − 1.5 V at 25 °C; 0 to VCC − 2 V over the full temperature range. LM339B: (V−) − 0.1 V to (V+) − 2.0 V. Inputs must not go more than 0.3 V below GND. | §6.10 p10 (incl. note 3); §6.4 p6 |
| Output type | Open collector (NPN pull-down). Sinks 6 mA min / 16 mA typ at VOL = 1.5 V. | §7.1 / §7.3 p19; §6.10 p10 |

## 8. Infineon BSC070N10NS3 G (PG-TDSON-8 / SuperSO8, 100 V)
URL: https://www.infineon.com/dgdl/BSC070N10NS3+Rev2+1.pdf — the downloaded content is **Rev 2.2, 2021-12-10** (despite the "Rev2+1" in the URL)

| Fact | Value | Source |
|---|---|---|
| VDS | 100 V. V(BR)DSS ≥ 100 V. | Table 1 p1; Table 4 p4 |
| RDS(on) max at VGS = 10 V | 7 mΩ (6.3 typ) at ID = 50 A. At VGS = 6 V: 14 mΩ max. | Table 4, p4 |
| ID | 92 A at TC = 25 °C; 58 A at TC = 100 °C. Pulsed 368 A. | Table 2, p3 |
| Qg | 42 nC typ, 55 nC max (VDD = 50 V, ID = 25 A, VGS = 0–10 V) | Table 6, p4 |
| RthJC | 1.1 K/W max | Table 3, p3 |
| RthJA | 50 K/W max on 6 cm² copper (40×40×1.5 mm FR4, one layer, 70 µm, vertical, still air). 62 K/W on minimal footprint. | Table 3 + note 3, p3 |
| Tj max | 150 °C (range −55 to 150 °C) | Table 2, p3 |
| Pinout | Source: pins 1–3. Gate: pin 4. Drain: pins 5–8 (plus exposed drain pad). | p1 pin diagram |

## 9. Littelfuse SMBJ60A
URL: copy of the Littelfuse PDF at https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/Littelfuse_5F00_TVS_5F00_Diode_5F00_SMBJ_5F00_Datasheet.pdf_2D00_1108540.pdf — **Littelfuse "SMBJ series", Revised 06/03/20** (littelfuse.com returned 403)

| Fact | Value | Source |
|---|---|---|
| VRWM (VR) | 60.0 V | Electrical Characteristics table, p2 |
| VBR min | 66.70 V (max 73.70 V) at IT = 1 mA | p2 |
| VC at IPP | 96.8 V max | p2 |
| IPP | 6.2 A max (10/1000 µs, 600 W series) | p2; p1 features |

## 10. ST STPS1H100A (SMA, 100 V / 1 A Schottky) — bootstrap diode candidate
URL (mirror): https://datasheet.lcsc.com/datasheet/pdf/89e5559097044ff9bd97fb5866deb846.pdf?productCode=C165701 — **STPS1H100-Y, Doc ID 17935 Rev 1, December 2010**. This is the automotive variant (SMA = STPS1H100AY). The commercial STPS1H100A datasheet at st.com could not be retrieved.

| Fact | Value | Source |
|---|---|---|
| VRRM | 100 V | Table 2, p2 |
| IF(AV) | 1 A (TL = 160 °C, δ = 0.5). IFSM 50 A. | Table 2, p2 |
| VF | 0.77 V max at 1 A, 25 °C. 0.58 typ / 0.62 max at 1 A, 125 °C. 0.86 V max at 2 A, 25 °C. | Table 4, p2 |
| IR | 4 µA max at VRRM, 25 °C. 0.2 typ / 0.5 max mA at 125 °C. | Table 4, p2 |
| trr | NOT FOUND (Schottky; the datasheet gives no trr) | — |
| Tj max | 175 °C | Table 2, p2 |
