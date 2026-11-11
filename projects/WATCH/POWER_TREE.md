# WATCH — Power Tree Architecture & Budget

## 4. Voltage tree
| Rail | Source | Min | Typ | Max | Max Current | Loads |
|---|---|---|---|---|---|---|
| VBUS | USB-C connector / 5V Boost | 4.4 V | 5.0 V | 5.5 V | 2.0 A (in) / 0.5 A (out) | BQ24074 Charger IN / External USB device |
| VBAT | 1S LiPo 300 mAh (3.7V nom, rev B) | 3.0 V | 3.7 V | 4.2 V | 1.5 A peak (5 C; cell protection limit per client cell datasheet TBC) | Battery Protection, BQ24074 BAT, Boost IN |
| VSYS | BQ24074 Power-Path OUT | 3.3 V | 3.8 V | 4.4 V | 2.0 A peak | TPS63802 Buck-Boost IN, TPS61023 Boost IN |
| +3V3 | TPS63802 Buck-Boost OUT | 3.25 V | 3.30 V | 3.35 V | 1.5 A peak | ESP32-S3, LCD, IMU, Mics, 6 LEDs |
| +5V0_BOOST (VBUS_BOOST) | TPS61023 Boost OUT | 4.90 V | 5.05 V | 5.25 V | 1.0 A peak | Mono MAX98357A PVDD (0.71 A at 3 W); Mode B 5 V OTG output |



## Power Architecture Breakdown
`
[USB-C 5V VBUS] ───► [TPD2E2U06 TVS] ───► [BQ24074RGTR Charger] ───► [VSYS: 3.3V - 4.4V]
                                                    │                             │
                                             [1S LiPo Battery]                    ├──► [TPS63802DLAR Buck-Boost] ──► [+3V3 System Rail]
                                                    │                             │                                       │
                                                    ▼                             └──► [Stereo Class-D Amp PVDD]          ├──► ESP32-S3-WROOM-1
                                          [TPS61023DRLR Boost]                                                            ├──► Waveshare 1.47 LCD
                                                    │                                                                     ├──► MicroSD Card (SPI)
                                                    └──► [5V OTG to VBUS]                                                 ├──► 3x ICS-43434 Mics
                                                                                                                          └──► ICM-42670-P IMU
`

## Power Operating Modes:
1. **Mode A (Charging & Power-Path)**: USB-C 5V in charges the battery and supplies VSYS simultaneously.
2. **Mode B (OTG 5V Boost Output)**: Battery supplies TPS61023 boost to drive 5V out to external USB device.
3. **Mode C (Battery Wearable Active)**: Battery powers VSYS through internal BQ24074 low-RDSon power-path FET.


## Rev B battery recheck (300 mAh, 2026-11-11)
| Item | Value | Basis |
|---|---|---|
| Charge current | 157 mA (0.52 C), R_ISET = 5.1 k | BQ24074 K_ISET 800 A*Ohm; 0.5-1 C window for small pouch cells |
| Termination | 15.7 mA (10 %) | R_ITERM = 2 k |
| Safety timer | 6.25 h vs ~2.3 h needed | R_TMR = 47 k |
| Runtime, 35.4 mA average profile | 300 * 0.8 / 35.4 = 6.8 h | Same duty profile as REQUIREMENTS §3 (R-13 was 8-12 h with 500 mAh): client-accepted deviation |
| Peak discharge | 3 W playback: 0.71 A at 5 V -> ~1.3 A from VBAT at 3.0 V (4.3 C) | Cell must allow >= 5 C pulse or firmware limits volume; confirm cell datasheet |
| Protection | External BMS in the cell pack (IEC 62133 / UN38.3, R-16) + BQ24074 OVP/OCP | Unchanged |
