# UPS_1000 rev A — Block plan (functional architecture)

Source of every block: `design/gen_blocks.py` → `blocks/NN_ID.json`. All 9 blocks: lint PASS, build + verify VERIFIED on the first attempt (S1).

| ID | Title | Main ICs | Ports (interfaces) | Ground / isolation domain | Client block (spec §4) |
|---|---|---|---|---|---|
| 01_PWR_IN | Power input and protection | F1, D1 SMBJ60A, C1/C2 | VBUS, VBUS_SNS, GND | SELV ≤ 60 V, GND | 1 (AC input & protection — **DC lab input on rev A**) |
| 02_AUX_12V | Aux 12 V buck | LM5164 | VBUS, 12V, GND | GND | 10 |
| 03_AUX_5V_3V3 | Aux 5 V buck + 3V3 LDO | TPS54202, AP2112K-3.3 | 12V, 5V, 3V3, GND | GND | 10 |
| 04_MCU | STM32G431 controller | STM32G431CBT6 | 3V3, sense inputs, PWM_H/L, FAULT_N, DRV_DIS, FAN_PWM, CAN_TX/RX | GND (control side) | 11 |
| 05_CAN | CAN transceiver | SN65HVD230 | 3V3, CAN_TX/RX | GND | 11 (RS485 not populated) |
| 06_GATE_DRV | Isolated gate driver + HW gating | UCC21520, 74LVC2G08 | PWM_H/L, FAULT_N, DRV_DIS, GH, GL, SW, 12V | input side GND / output side SW & GND — **functional barrier only** | 8 |
| 07_HALF_BRIDGE | Half-bridge power stage + sensing | 2 × BSC070N10NS3G, INA240A1 | VBUS, SW, PHASE (J5), ISENSE, NTC_SNS, VOUT_SNS | power zone, GND | 7 (half-bridge test stage), 9 (LC filter external via J5) |
| 08_PROTECTION | HW protection comparators | LM339 | ISENSE, NTC_SNS, VBUS_SNS → FAULT_N | GND | 12 |
| 09_FAN_IO | Fan drive + instrument header | AO3400A | FAN_PWM, scope signals | GND | cooling / instrumentation |

Power flow: J1 → F1 → VBUS → {half-bridge → shunt → J5 PHASE ; LM5164 → 12V → {UCC21520 VDD, LM339, fan, TPS54202 → 5V → AP2112K → 3V3}}.
Protection flow: INA240 / NTC / VBUS divider → LM339 (wired-OR) → FAULT_N → {74LVC2G08 gates both driver inputs ; TIM1_BKIN latch}.

Not designed in this run (system level, blocked by missing requirements M-01..M-13): 2 rectification & PFC, 3 380 V DC link, 4 isolated CC/CV charger, 5 battery interface & BMS protection, 6 battery↔DC-link DC-DC, full-bridge inverter at 380 V, 230 V LC output filter, mains EMI filter.
