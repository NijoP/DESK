# WATCH — Component selection (gate B)   Method: docs/00b_COMPONENT_SELECTION.md

## 1. Key part decisions (one section per IC / module / sensor / connector)

### Main MCU Module — requirement IDs: R-01, R-14
Derived need: Dual-core 240MHz Xtensa LX7, Wi-Fi 4 + BLE 5, 8MB Flash, 8MB Octal PSRAM, USB-OTG/CDC native, Compact PCB footprint.

| Filter | ESP32-S3-WROOM-1-N8R8 | ESP32-S3-MINI-1 | ESP32-WROOM-32E |
|---|---|---|---|
| MPN / LCSC | ESP32-S3-WROOM-1-N8R8 / C2934560 | ESP32-S3-MINI-1-N8 / C2913204 | ESP32-WROOM-32E / C701341 |
| F1 function | Dual core, AI vector ext, 8M PSRAM | Dual core, 4M/8M Flash, no PSRAM | Dual core, no vector ext, 4M flash |
| F2 operating range | 3.0 to 3.6 V, -40 to +85 °C | 3.0 to 3.6 V, -40 to +85 °C | 3.0 to 3.6 V, -40 to +85 °C |
| F3 key numbers | 8MB Flash + 8MB PSRAM for audio DSP | Flash only (no PSRAM for neural models)| No PSRAM, older architecture |
| F4 package / height | 18.0 × 25.5 × 3.2 mm | 13.2 × 16.6 × 2.4 mm | 18.0 × 25.5 × 3.1 mm |
| F5 stock / lifecycle| Active, abundant stock | Active | Active |
| F6 unit cost @ qty | .85 @ 1k | .60 @ 1k | .10 @ 1k |
| F7 ref design / EDA | ✅ In library / verified footprint | ✅ In library | ✅ In library |
| **Verdict** | ✅ chosen | ❌ insufficient PSRAM | ❌ no PSRAM / AI vector |

Reason: Mandatory requirement in Client DOCX §3: ESP32-S3-WROOM-1-N8R8 with 8MB Flash and 8MB PSRAM.

---

### Digital MEMS Microphones — requirement IDs: R-02
Derived need: Digital MEMS with PDM or I2S output, ultra-compact package, high SNR >= 64 dBA, bottom-port or top-port acoustic opening, low power consumption (< 1mA).

| Filter | ICS-43434 | INMP441 | MSM261S4030H0R |
|---|---|---|---|
| MPN / LCSC | ICS-43434 / C5656610 | INMP441 / C268260 | MSM261S4030H0R / C289069 |
| F1 function | Digital I2S MEMS microphone | Digital I2S MEMS microphone | Digital I2S MEMS microphone |
| F2 operating range | 1.62 to 3.63 V, -40 to +85 °C | 1.62 to 3.63 V, -40 to +85 °C | 1.6 to 3.6 V, -40 to +85 °C |
| F3 key numbers | 65 dBA SNR, 120 dB SPL AOP, 490 µA | 61 dBA SNR, 120 dB SPL, 1.4 mA | 65 dBA SNR, 120 dB SPL, 600 µA |
| F4 package / height | LGA-6, 3.50 × 2.65 × 0.98 mm | LGA-6, 4.72 × 3.76 × 1.00 mm | LGA-6, 4.00 × 3.00 × 1.00 mm |
| F5 stock / lifecycle| Active, proven production part | Legacy / declining | Active |
| F6 unit cost @ qty | .85 @ 1k | .95 @ 1k | .55 @ 1k |
| F7 ref design / EDA | ✅ In library (uuid: 6f70cd15431bcb83)| Needs symbol | Needs symbol |
| **Verdict** | ✅ chosen | ❌ higher current, larger package | ❌ lower market availability |

Reason: Verified DESK library device (ICS-43434_C5656610), industry standard 65 dBA SNR, proven I2S interface, compact 3.5×2.65mm package.

---

### Stereo Class-D Audio Amplifier — requirement IDs: R-03
Derived need: Stereo bridge-tied load (BTL) Class-D amplifier, delivering >= 2.0 W per channel into 4 Ω loads at <= 10% THD+N, high efficiency (>85%), shutdown mode < 1 µA.

| Filter | MAX98357A (x2) | PAM8403 | TPA2012D2 |
|---|---|---|---|
| MPN / LCSC | MAX98357AETE+T (Dual) / C268262 | PAM8403 / C21308 | TPA2012D2RTJR / C29188 |
| F1 function | Digital I2S input Class-D Amp | Analog stereo Class-D Amp | Analog differential stereo Class-D |
| F2 operating range | 2.5 to 5.5 V, -40 to +85 °C | 2.8 to 5.5 V, -40 to +85 °C | 2.5 to 5.5 V, -40 to +85 °C |
| F3 key numbers | 3.2 W into 4Ω (5V), 1.7W into 4Ω (3.7V)| 3.0 W into 4Ω (5V), high THD | 2.1 W into 4Ω (5V), 1.4W into 4Ω (3.7V)|
| F4 package / height | WLP / TQFN-16, 3.0 × 3.0 × 0.75 mm | SOP-16, 9.9 × 3.9 mm (huge) | QFN-20, 4.0 × 4.0 × 0.75 mm |
| F5 stock / lifecycle| High volume, industry standard | Low cost | Active |
| F6 unit cost @ qty | .78 @ 1k (each) | .18 @ 1k | .92 @ 1k |
| F7 ref design / EDA | ✅ Standard I2S DAC+Amp architecture | ❌ Requires external DAC | ❌ Requires external stereo DAC |
| **Verdict** | ✅ chosen (Dual MAX98357A) | ❌ No built-in DAC, bulky SOP16 | ❌ Requires separate stereo DAC IC |

Reason: Dual MAX98357A integrates DAC + Class-D stage into tiny 3×3mm package with single-wire I2S input; Left channel configured via GAIN/L-R pins, Right channel via separate select, perfectly driving Ole Wolff 4Ω 2W speakers.

---

### 6-Axis Motion Sensor (IMU) — requirement IDs: R-04
Derived need: 6-axis Accel + Gyro, ultra-low power (< 1mA active), I2C interface, motion interrupt pin for wake-on-shake, compact LGA package.

| Filter | ICM-42670-P | ICM-20600 | MPU-6050 |
|---|---|---|---|
| MPN / LCSC | ICM-42670-P / C2924151 | ICM-20600 / C111756 | MPU-6050 / C24112 |
| F1 function | Premium 6-axis IMU + APEX DSP | Standard 6-axis IMU | Legacy 6-axis IMU |
| F2 operating range | 1.71 to 3.6 V, -40 to +85 °C | 1.71 to 3.45 V, -40 to +85 °C | 2.375 to 3.46 V, -40 to +85 °C |
| F3 key numbers | 0.73 mA 6-axis, ultra-low noise | 2.5 mA 6-axis | 3.9 mA 6-axis |
| F4 package / height | LGA-14, 2.5 × 3.0 × 0.76 mm | LGA-14, 2.5 × 3.0 × 0.91 mm | QFN-24, 4.0 × 4.0 × 0.90 mm |
| F5 stock / lifecycle| Current generation, active | NRND | EOL / Obsolete |
| F6 unit cost @ qty | .25 @ 1k | .40 @ 1k | .10 @ 1k |
| F7 ref design / EDA | ✅ Modern TDK InvenSense standard | Standard | Legacy |
| **Verdict** | ✅ chosen | ❌ older, higher current | ❌ EOL legacy part |

Reason: TDK InvenSense ICM-42670-P provides industry-leading ultra-low noise, on-chip APEX step/gesture engine, low 0.73 mA power, and 2.5×3.0mm footprint.

---

### Battery Charging & Power-Path Controller — requirement IDs: R-09, R-10
Derived need: 1S LiPo linear charger with automatic dynamic power-path management (NVDC / VSYS output), programmable charge current (500mA), VBUS withstand >= 18V.

| Filter | BQ24074RGTR | BQ25170DSGR | TP4056 |
|---|---|---|---|
| MPN / LCSC | BQ24074RGTR / C43224 | BQ25170DSGR / C2837330 | TP4056 / C16581 |
| F1 function | Autonomous Power-Path + Charger | Linear standalone charger | Basic standalone charger |
| F2 operating range | 4.35 to 28 V (OVP 10.5V), -40..+85°C| 3.0 to 30 V, -40..+85°C | 4.5 to 5.5 V, -40..+85°C |
| F3 key numbers | 1.5A Sys, 1.0A Chg, NVDC Power-Path | 800mA Chg, NO power-path | 1.0A Chg, NO power-path, no OVP |
| F4 package / height | VQFN-16, 3.0 × 3.0 × 0.90 mm | WSON-8, 2.0 × 2.0 × 0.75 mm | SOP-8, 4.9 × 3.9 mm |
| F5 stock / lifecycle| High volume production | Active | Active |
| F6 unit cost @ qty | .15 @ 1k | .55 @ 1k | .15 @ 1k |
| F7 ref design / EDA | ✅ In library / proven on BeeBox V2 | ✅ In library | ❌ Resets device on USB unplug |
| **Verdict** | ✅ chosen | ❌ Lacks power-path management | ❌ No power path, unsafe OVP |

Reason: BQ24074 provides true seamless power-path management: powers the watch from USB-C immediately while charging, without battery depletion or glitches when USB-C is connected/disconnected.

---

### 3.3V System Voltage Regulator — requirement IDs: R-11
Derived need: Buck-boost or high-efficiency buck converter delivering 3.30V >= 1.0A from VSYS (3.3V–4.4V), ultra-low Iq, compact 0402 passives.

| Filter | TPS63802DLAR | TPS62840DLCR | TLV75733PDBVR |
|---|---|---|---|
| MPN / LCSC | TPS63802DLAR / C43225 | TPS62840DLCR / C478330 | TLV75733PDBVR / C397441 |
| F1 function | High-efficiency 2A Buck-Boost | 750mA Ultra-low Iq Buck | 1.0A Low-dropout Linear (LDO) |
| F2 operating range | 1.3 to 5.5 V, -40 to +125 °C | 1.8 to 6.5 V, -40 to +125 °C | 1.45 to 5.5 V, -40 to +125 °C |
| F3 key numbers | 2.0 A output, 11 µA Iq, 95% eff | 750 mA output, 60 nA Iq | 1.0 A output, burns (VBAT-3.3)*I |
| F4 package / height | VSON-10, 2.0 × 3.0 × 0.75 mm | VSON-8, 1.5 × 2.0 × 0.75 mm | SOT-23-5, 2.9 × 1.6 mm |
| F5 stock / lifecycle| Production standard | Active | Active |
| F6 unit cost @ qty | .85 @ 1k | .95 @ 1k | .22 @ 1k |
| F7 ref design / EDA | ✅ In library / proven on BeeBox V2 | ✅ In library | High heat dissipation in watch |
| **Verdict** | ✅ chosen | ❌ Buck only (cannot regulate at 3.0V)| ❌ Excessive heat & battery loss |

Reason: TPS63802 maintains rock-solid 3.30V rail even when the 1S LiPo discharges down to 3.0V under high-current Wi-Fi/DSP transmission loads.

---

### 5V Boost Output Converter — requirement IDs: R-09, R-12
Derived need: Synchronous boost converter providing 5.05V >= 500mA to USB-C VBUS for OTG accessories, true load disconnect in shutdown, compact package.

| Filter | TPS61023DRLR | MT3608 | TPS61099YFFR |
|---|---|---|---|
| MPN / LCSC | TPS61023DRLR / C391807 | MT3608 / C84817 | TPS61099YFFR / C189283 |
| F1 function | 3.7A switch Synchronous Boost | Asynchronous Boost (ext diode) | Ultra-low power Boost |
| F2 operating range | 0.5 to 5.5 V, -40 to +125 °C | 2.0 to 24 V, -40 to +85 °C | 0.7 to 5.5 V, -40 to +85 °C |
| F3 key numbers | 5V @ 1.5A from LiPo, true disconnect| 5V @ 500mA, high diode drop | 5V @ 100mA max (insufficient) |
| F4 package / height | SOT-563, 1.6 × 1.6 × 0.60 mm | SOT-23-6, 2.9 × 1.6 mm + diode | DSBGA-6, 0.8 × 1.2 mm |
| F5 stock / lifecycle| Active | High volume | Active |
| F6 unit cost @ qty | .48 @ 1k | .15 @ 1k | .65 @ 1k |
| F7 ref design / EDA | ✅ In library / proven on BeeBox V2 | ❌ Requires bulky external diode | ❌ Output current too small |
| **Verdict** | ✅ chosen | ❌ Bulky diode, non-synchronous | ❌ Max current only 100mA |

Reason: TPS61023 provides 5V output at >90% efficiency with internal true load disconnect (isolating VBUS when boost is disabled) in a tiny 1.6×1.6mm package.

---

### MicroSD Socket — requirement IDs: R-07
Derived need: Push-push or hinge-type compact MicroSD socket, 3.3V SPI interface, integrated card-detect switch, robust PCB retention.

| Filter | TF-01A (Push-Push) | MEM2051 (Push-Pull) | MOLEX 472192001 |
|---|---|---|---|
| MPN / LCSC | TF-01A-SMD / C2911296 | MEM2051-00-188-00-A / C712534 | 0472192001 / C153205 |
| F1 function | MicroSD socket with CD switch | Ultra-low profile MicroSD socket | Premium MicroSD socket |
| F2 operating range | -25 to +85 °C | -40 to +85 °C | -40 to +85 °C |
| F3 key numbers | 10,000 cycles, Card Detect pin | 5,000 cycles, no CD switch | 10,000 cycles |
| F4 package / height | 14.0 × 14.5 × 1.85 mm | 11.5 × 11.9 × 1.35 mm | 14.0 × 14.8 × 1.80 mm |
| F5 stock / lifecycle| High volume production | Active | Active |
| F6 unit cost @ qty | .22 @ 1k | .35 @ 1k | .20 @ 1k |
| F7 ref design / EDA | ✅ In library / verified footprint | Standard | Standard |
| **Verdict** | ✅ chosen | ❌ Lacks card-detect switch | ❌ High cost |

Reason: Standard TF-01A provides proven push-push tactile retention and integrated card detect pin at 1.85mm profile.

---

### Display Connector — requirement IDs: R-08
Derived need: PH2.0 8-pin connector matching the Waveshare 1.47-inch LCD interface (GND, VCC, SCL, SDA, RST, DC, CS, BL).

| Filter | S8B-PH-SM4-TB | B8B-PH-K-S | FPC 8-pin 0.5mm |
|---|---|---|---|
| MPN / LCSC | S8B-PH-SM4-TB / C231124 | B8B-PH-K-S / C293415 | FH34SRJ-8S-0.5SH / C28912 |
| F1 function | JST PH 2.0mm 8-pin Right-Angle SMT| JST PH 2.0mm 8-pin Straight TH | 0.5mm pitch FPC socket |
| F2 operating range | -25 to +85 °C, 2.0 A per pin | -25 to +85 °C, 2.0 A per pin | -55 to +85 °C, 0.5 A per pin |
| F3 key numbers | 100% matched to Waveshare cable | Requires through-hole | Requires custom FPC |
| F4 package / height | SMT horizontal 2.0mm pitch | Through-hole vertical | SMT horizontal |
| F5 stock / lifecycle| Standard JST PH series | Standard | Standard |
| F6 unit cost @ qty | .25 @ 1k | .18 @ 1k | .45 @ 1k |
| F7 ref design / EDA | ✅ In library / verified footprint | Standard | Standard |
| **Verdict** | ✅ chosen | ❌ Through-hole pins breach bot layer| ❌ Waveshare module uses PH2.0 cable|

Reason: Exact matching connector specified for the Waveshare 1.47-inch LCD interface cable (PH2.0 8-pin).

---

## 2. Preferred passive set for this product
| Type | Values | Package | Rating | LCSC (basic?) |
|---|---|---|---|---|
| R | 0R, 1k, 4.7k, 10k, 47k, 100k, 562k, 750k | 0402 / 0603 | 1 % 62.5 mW (0402) / 100 mW (0603) | Preferred |
| C | 100 nF, 1 µF, 4.7 µF, 10 µF, 22 µF | 0402 / 0603 | 16 V / 25 V X5R/X7R | Preferred |
| L | 1.0 µH (TPS61023), 2.2 µH (TPS63802) | SMD Power | >= 2.5 A Isat, low DCR | Preferred |
| TVS | TPD2E2U06DRLR, TPD4E05U06DQAR | SOT-553 / USON-10 | 5.5 V ESD protection (IEC 61000-4-2) | Preferred |

## 3. Risks
| Part | Risk | Fallback |
|---|---|---|
| ESP32-S3-WROOM-1-N8R8 | Module width (18mm) on 35x35mm board | Compact layout verified; antenna overhang outside 35x35mm main area |
| Dual MAX98357A Amplifiers | Thermal dissipation during continuous max playback | Thermal vias to Layer 2 GND; software limiter to 1.5W per channel |
| 3x MEMS Microphones | Acoustic cross-talk from Ole Wolff speakers | Gasket sealing + independent mic clock/data routing isolation |
| MicroSD Card SPI Bus | Contention with SPI display | Separate dedicated CS and clock routing; SPI bus arbitration in driver |
