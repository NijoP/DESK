# WATCH — Requirements (gate R: frozen before part selection)

Client: Voice-Interactive Wearable Audio Device Requirements DOCX  Confirmed by: Engineering Review / Antigravity Lead  Date: 2026-11-06   Method: docs/00_REQUIREMENTS.md
Status tags: **CONFIRMED** · **PROVISIONAL** (assumption, risk noted) · **TBD** (blocks depending on it wait)

## 1. Use case & operating modes
A compact, wearable voice-interactive watch worn throughout the day with local offline audio playback, continuous or push-to-talk voice acquisition, Bluetooth synchronization, motion gesture detection, microSD storage, and a vibrant 1.47-inch LCD interface.

| Mode | Trigger | What is ON | Duration / duty |
|---|---|---|---|
| OFF / ship | Battery disconnected / Deep sleep | Power path / BMS only | Months |
| SLEEP | Inactivity timeout | ESP32 RTC / ULP, IMU motion interrupt wake, PMIC | 85 % duty |
| ACTIVE_IDLE | Screen ON / UI active | ESP32 core, LCD backlight, IMU, MicroSD standby | 5 % duty |
| VOICE_CAPTURE | Button 3 held / PTT / Wake word | 3x MEMS Microphones, ESP32 DSP, BLE audio stream | 5 % duty |
| AUDIO_PLAYBACK | Voice response / audio playback | Stereo Class-D Amp, 2x Ole Wolff speakers, MicroSD read | 5 % duty |
| CHARGING | USB-C 5V plugged in | BQ24074 charger, Power-path VSYS, Battery charge | As needed |
| 5V_BOOST_OUT | OTG accessory connected | TPS61023 boost (5V out to USB-C VBUS) | On demand |
| FAULT | Overcurrent / thermal fault | Charger / Boost / Amp shutdown, loads OFF | Safety cutoff |

## 2. Requirement table (all 10 dimensions)
| ID | Dimension | Requirement | Value / limit | Source | Status | Risk if wrong |
|---|---|---|---|---|---|---|
| R-01 | Function | Core processing MCU | ESP32-S3-WROOM-1-N8R8 (8MB Flash, 8MB PSRAM, Wi-Fi/BLE) | DOCX §3 | CONFIRMED | Insufficient RAM/Flash for offline models |
| R-02 | Function | Audio capture system | 3x Digital MEMS Microphones (2 Left, 1 Right), synchronous clocking | DOCX §4 | CONFIRMED | Acoustic phase mismatch or clock routing skew |
| R-03 | Function | Audio output system | Stereo Class-D amplifier driving 2x independent 4Ω 2W Ole Wolff speakers | DOCX §5 | CONFIRMED | Excessive distortion, brownout, or amplifier clipping |
| R-04 | Function | Motion detection IMU | 6-axis Accelerometer + Gyroscope (ICM-series / I2C) | DOCX §6 | CONFIRMED | Gesture detection failure or false triggers |
| R-05 | Function | Physical user controls | 5 physical push buttons (Reset, Boot, PTT/Voice, Config1, Config2) | DOCX §7 | CONFIRMED | Debounce noise or accidental reset during wear |
| R-06 | Function | Visual indicators | 2 independent LEDs (Power/Charging, Status/BT/DSP) | DOCX §8 | CONFIRMED | Unclear user status feedback |
| R-07 | Function | Local mass storage | Removable MicroSD card socket over 3.3V SPI interface with card detect | DOCX §9 | CONFIRMED | SPI bus contention with LCD or signal corruption |
| R-08 | Function | Visual display | Waveshare 1.47-inch LCD (172x320 ST7789V3, 4-wire SPI, PH2.0 8-pin connector) | Client update / DOCX §10 | CONFIRMED | Display timing issues or SPI clock conflict |
| R-09 | Supply | Dual-role USB-C & Battery | Single USB-C port: Mode A (5V in charge), Mode B (5V out boost), Mode C (USB data/debug) | DOCX §11 | CONFIRMED | Backfeeding VBUS into boost converter |
| R-10 | Supply | Battery management | 1S LiPo rechargeable, integrated linear/buck charger with power-path management | DOCX §11 | CONFIRMED | Device resets when USB is plugged/unplugged |
| R-11 | Supply | System 3.3V power | Low-noise buck-boost / buck regulator delivering 3.3V >= 1.0A for MCU & peripherals | DOCX §11 | CONFIRMED | ESP32 Wi-Fi TX brownout (peak current >500mA) |
| R-12 | Supply | 5V Boost output | Boost converter delivering 5.0V >= 500mA to USB-C VBUS from battery | DOCX §11 | CONFIRMED | Battery overload or high inductor saturation |
| R-13 | Budget | Battery capacity & runtime | Target runtime >= 8-12 hours active wearable use (recommended battery >= 450-600 mAh) | DOCX §15 | PROVISIONAL | Premature battery drain during speaker playback |
| R-14 | Mechanical | Board envelope & layers | 4-layer PCB, approx 35 x 35 mm (excluding antenna extension) | DOCX §12 | CONFIRMED | Routing congestion or component placement collision |
| R-15 | Environmental | Wearable operating temp | 0 to +50 °C operating range, skin-contact thermal safety (< 42 °C exterior) | Wearable standard | PROVISIONAL | Skin irritation from amplifier/charger heating |
| R-16 | Regulatory | RF & Battery safety | Pre-certified module (ESP32-S3-WROOM-1), IEC 62133 / UN38.3 battery protection | Regulatory standard | PROVISIONAL | Redesign required for commercial market launch |
| R-17 | Manufacturing | Standard PCBA process | Double-sided SMT assembly, standard JLCPCB / PCBWay 4-layer stackup | DOCX §12 | CONFIRMED | Assembly yield loss on tight 0402/WLCSP |
| R-18 | Cost & supply | Production BOM availability | High-availability active parts with direct second sources | Engineering best practice | CONFIRMED | Supply chain disruption |
| R-19 | Lifecycle | USB firmware update | Native ESP32-S3 USB CDC/JTAG + auto-reset circuitry on USB-C D+/D- | DOCX §11 | CONFIRMED | Device unbrickable if firmware faults |
| R-20 | Interfaces | Ole Wolff speaker connector | 2x JST SH 1.0mm 2-pin / spring contacts for Ole Wolff OWS-142550TA-4 | DOCX §5 | CONFIRMED | Incorrect connector pitch or mechanical stress |

## 3. Power budget
| Load | Rail | Active mA | Sleep µA | Duty | Average mA | Notes |
|---|---|---|---|---|---|---|
| ESP32-S3 MCU | +3V3 | 120 mA | 25 µA | 10 % | 12.0 mA | Includes BLE/DSP activity peaks |
| LCD Display & Backlight | +3V3 | 35 mA | 5 µA | 5 % | 1.75 mA | Waveshare 1.47-in backlight at 50% |
| MicroSD Card | +3V3 | 50 mA | 150 µA | 5 % | 2.50 mA | Peak during audio streaming write/read |
| 3x MEMS Microphones | +3V3 | 2.5 mA | 30 µA | 5 % | 0.13 mA | ~800 µA each in high-performance mode |
| ICM 6-axis IMU | +3V3 | 1.2 mA | 10 µA | 100 % | 1.20 mA | Low-power 6-axis motion tracking |
| Stereo Class-D Amp | VBAT / VSYS | 350 mA | 1 µA | 5 % | 17.50 mA | 2W output into 4Ω speakers at 5% duty |
| Status LEDs (2x) | +3V3 | 6 mA | 0 µA | 5 % | 0.30 mA | 3 mA per LED with current limiters |
| Regulators Iq | VBAT | 0.05 mA | 35 µA | 100 % | 0.05 mA | Quiescent currents of buck/charger |
| **Total Average** | | | | | **35.43 mA** | **Expected battery life: 500 mAh * 0.8 / 35.4 mA ≈ 11.3 Hours** |

## 4. Voltage tree
| Rail | Source | Min | Typ | Max | Max Current | Loads |
|---|---|---|---|---|---|---|
| VBUS | USB-C connector / 5V Boost | 4.4 V | 5.0 V | 5.5 V | 2.0 A (in) / 0.5 A (out) | BQ24074 Charger IN / External USB device |
| VBAT | 1S LiPo Battery (3.7V nom) | 3.0 V | 3.7 V | 4.2 V | 2.5 A peak | Battery Protection, BQ24074 BAT, Boost IN |
| VSYS | BQ24074 Power-Path OUT | 3.3 V | 3.8 V | 4.4 V | 2.0 A peak | TPS63802 Buck-Boost IN, Class-D Amp PVDD |
| +3V3 | TPS63802 Buck-Boost OUT | 3.25 V | 3.30 V | 3.35 V | 1.5 A peak | ESP32-S3, LCD, MicroSD, IMU, Mics, LEDs |
| +5V0_BOOST | TPS61023 Boost OUT | 4.90 V | 5.05 V | 5.25 V | 1.0 A peak | Switched to VBUS in Mode B (Power Output) |

## 5. Mechanical envelope
- PCB Dimensions: Main PCB 35.0 mm × 35.0 mm (excluding RF antenna keepout overhang).
- Layer Count: 4-layer FR4 stackup (SIG - GND - PWR - SIG).
- Top side placement: ESP32-S3 module, 3x digital MEMS microphones, IMU sensor, Class-D audio amplifier, 3x user buttons, 2x status LEDs, LCD connector (PH2.0 8-pin).
- Bottom side placement: MicroSD socket, USB-C connector, Reset button, Boot button, BQ24074 charger, TPS63802 buck-boost, TPS61023 boost, battery connector pads.

## 6. Thermal check
| Part | Dissipation W | θJA (°C/W) | Tj at max ambient (50°C) | Limit (°C) | Status |
|---|---|---|---|---|---|
| BQ24074 Charger (500mA chg) | 0.45 W | 45 °C/W | 70.2 °C | 125 °C | PASS |
| TPS63802 Buck-Boost (1A peak) | 0.18 W | 42 °C/W | 57.6 °C | 125 °C | PASS |
| Stereo Class-D Amp (1W avg play) | 0.25 W | 48 °C/W | 62.0 °C | 150 °C | PASS |
| TPS61023 Boost (500mA 5V out) | 0.32 W | 55 °C/W | 67.6 °C | 125 °C | PASS |

## 7. External interface table
| Connector.pin | Net | Dir | Level | Current | ESD exposure |
|---|---|---|---|---|---|
| USB-C.A4/B9 | VBUS | BI | 5.0 V | 2.0 A | TPD2E2U06 TVS protected |
| USB-C.A6/B6 | USB_DP | BI | 3.3 V | 10 mA | TPD2E2U06 TVS protected |
| USB-C.A7/B7 | USB_DM | BI | 3.3 V | 10 mA | TPD2E2U06 TVS protected |
| USB-C.A5 | USB_CC1 | IN | 0–5 V | 1 mA | 5.1k pull-down (UFP) / Type-C switch |
| USB-C.B5 | USB_CC2 | IN | 0–5 V | 1 mA | 5.1k pull-down (UFP) / Type-C switch |
| LCD_CONN.1 | GND | PWR | 0 V | 50 mA | Internal PH2.0 8-pin |
| LCD_CONN.2 | +3V3 | PWR | 3.3 V | 50 mA | Internal PH2.0 8-pin |
| LCD_CONN.3 | LCD_SCL | OUT | 3.3 V | 5 mA | Internal SPI clock |
| LCD_CONN.4 | LCD_SDA | OUT | 3.3 V | 5 mA | Internal SPI MOSI |
| LCD_CONN.5 | LCD_RST | OUT | 3.3 V | 2 mA | Internal reset signal |
| LCD_CONN.6 | LCD_DC | OUT | 3.3 V | 2 mA | Internal Data/Command signal |
| LCD_CONN.7 | LCD_CS | OUT | 3.3 V | 2 mA | Internal Chip Select signal |
| LCD_CONN.8 | LCD_BL | OUT | 3.3 V | 30 mA | Internal Backlight PWM |
| SPK_LEFT.1/2 | SPK_L_P / SPK_L_N | OUT | Differential | 700 mA | Internal speaker header |
| SPK_RIGHT.1/2| SPK_R_P / SPK_R_N | OUT | Differential | 700 mA | Internal speaker header |
| BAT_PADS.1/2 | VBAT / GND | PWR | 3.0–4.2 V | 2.5 A | Internal 2-pin JST / solder pads |

## 8. GPIO / pin budget
| MCU pin | Net | Function | Strap / boot constraint | Level at reset |
|---|---|---|---|---|
| EN (3) | MCU_EN | Chip Enable / Reset | Active HIGH, 10k PU + 1µF Cap | HIGH |
| IO0 (27) | MCU_BOOT | Boot select / Button 2 | Low = download mode | Pull-up 10k (HIGH) |
| IO1 (39) | I2S_MIC_SD1 | Left Mic 1 Data | Free GPIO | Input / Hi-Z |
| IO2 (38) | I2S_MIC_SD2 | Right Mic Data | Free GPIO | Input / Hi-Z |
| IO3 (15) | I2S_MIC_CLK | Common Mic BCLK / CLK | Free GPIO | Output |
| IO4 (4) | I2S_MIC_WS | Left Mics L/R WS Select | Free GPIO | Output |
| IO5 (5) | I2S_SPK_BCLK | Stereo Amp I2S Bit Clock | Free GPIO | Output |
| IO6 (6) | I2S_SPK_WS | Stereo Amp I2S Word Select | Free GPIO | Output |
| IO7 (7) | I2S_SPK_DOUT | Stereo Amp I2S Data Out | Free GPIO | Output |
| IO8 (12) | AMP_SD_MODE | Stereo Amp Enable / Shutdown | Free GPIO | Pull-down 100k (LOW) |
| IO9 (17) | I2C_SDA | IMU Sensor I2C Data | Free GPIO | Pull-up 4.7k (HIGH) |
| IO10 (18) | I2C_SCL | IMU Sensor I2C Clock | Free GPIO | Pull-up 4.7k (HIGH) |
| IO11 (19) | IMU_INT1 | Motion Detection Interrupt | Free GPIO | Input (Pulled low) |
| IO12 (20) | SD_SPI_MOSI | MicroSD MOSI | Free GPIO | Output |
| IO13 (21) | SD_SPI_MISO | MicroSD MISO | Free GPIO | Input (PU 10k) |
| IO14 (22) | SD_SPI_CLK | MicroSD SCLK | Free GPIO | Output |
| IO15 (8) | SD_CS | MicroSD Chip Select | Free GPIO | Output (PU 10k) |
| IO16 (9) | SD_DET | MicroSD Card Detect switch | Free GPIO | Input (PU 10k) |
| IO17 (10) | LCD_SCL | Waveshare LCD SPI Clock | Free GPIO | Output |
| IO18 (11) | LCD_SDA | Waveshare LCD SPI MOSI | Free GPIO | Output |
| IO19 (13) | USB_DM | USB-C Native USB D- | Native USB Peripheral | Hi-Z |
| IO20 (14) | USB_DP | USB-C Native USB D+ | Native USB Peripheral | Hi-Z |
| IO21 (23) | LCD_CS | Waveshare LCD Chip Select | Free GPIO | Output (PU 10k) |
| IO35 (28) | LCD_DC | Waveshare LCD Data/Cmd | Free GPIO | Output |
| IO36 (29) | LCD_RST | Waveshare LCD Reset | Free GPIO | Output (PU 10k) |
| IO37 (30) | LCD_BL | Waveshare LCD Backlight PWM | Free GPIO | Output (PD 100k) |
| IO38 (31) | BTN_VOICE | Button 3 (PTT / Voice capture) | Free GPIO | Input (PU 10k) |
| IO39 (32) | BTN_USER1 | Button 4 (Configurable 1) | Free GPIO | Input (PU 10k) |
| IO40 (33) | BTN_USER2 | Button 5 (Configurable 2) | Free GPIO | Input (PU 10k) |
| IO41 (34) | LED_STAT | Status LED 2 (BLE / System) | Free GPIO | Output (LOW) |
| IO42 (35) | VBUS_BOOST_EN| 5V Boost Enable (Mode B) | Free GPIO | Output (PD 100k) |
| IO45 (26) | VBUS_SENSE | VBUS Presence Sense (Mode A) | VDD_SPI strap (leave default) | Input (voltage div) |
| IO46 (16) | CHG_STAT | BQ24074 Charge Status | Strap pin (must be low at reset)| Input (open drain PU) |
| IO47 (24) | CHG_EN | BQ24074 Charge Enable / Mode | Free GPIO | Output (Pull-down) |
| IO48 (25) | LED_PWR | Power LED 1 (Charging / Power) | Free GPIO | Output (LOW) |


## Rev B client overrides (2026-11-11, Captain verbal; supersede the rows above where they conflict)
| ID | Change | New requirement | Status |
|---|---|---|---|
| R-03 | Audio output | Mono Class-D, 3 W into 4 ohm, MAX98357A on 5 V boost rail; speaker on solder pads SPK+/SPK- | CONFIRMED |
| R-08 | Display | Waveshare 1.47inch LCD Module (ST7789V3) on a soldered 1x8 1.27 mm pin header, no FPC/JST | CONFIRMED |
| R-13 | Battery | 300 mAh 1S LiPo; runtime ~6.8 h at the §3 profile (client-accepted) | CONFIRMED |
| R-14 | Envelope | 30 x 45 mm rounded rectangle, 4 corner mounting holes, USB-C on side, battery over top half, module bottom half | CONFIRMED |
| R-20 | Speaker connector | Solder pads (BAT_WIREPAD_2P footprint), one speaker | CONFIRMED |
| R-21 (new) | Status LEDs | Six LEDs, order 1-6 top-to-bottom on the right edge below the display, each on its own GPIO + 1k | CONFIRMED |
| R-22 (new) | Storage | No microSD (block 09 retired) | CONFIRMED |
