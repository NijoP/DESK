# WATCH — Power Tree Architecture & Budget

## 4. Voltage tree
| Rail | Source | Min | Typ | Max | Max Current | Loads |
|---|---|---|---|---|---|---|
| VBUS | USB-C connector / 5V Boost | 4.4 V | 5.0 V | 5.5 V | 2.0 A (in) / 0.5 A (out) | BQ24074 Charger IN / External USB device |
| VBAT | 1S LiPo Battery (3.7V nom) | 3.0 V | 3.7 V | 4.2 V | 2.5 A peak | Battery Protection, BQ24074 BAT, Boost IN |
| VSYS | BQ24074 Power-Path OUT | 3.3 V | 3.8 V | 4.4 V | 2.0 A peak | TPS63802 Buck-Boost IN, Class-D Amp PVDD |
| +3V3 | TPS63802 Buck-Boost OUT | 3.25 V | 3.30 V | 3.35 V | 1.5 A peak | ESP32-S3, LCD, MicroSD, IMU, Mics, LEDs |
| +5V0_BOOST | TPS61023 Boost OUT | 4.90 V | 5.05 V | 5.25 V | 1.0 A peak | Switched to VBUS in Mode B (Power Output) |



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
