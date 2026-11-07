# WATCH — ESP32-S3 GPIO Allocation Map

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


## Boot Strapping Pin Constraints & Validation
- **GPIO0**: Boot strapping pin. Pulled HIGH via 10k resistor to +3V3. Connected to SW2 (BOOT button) to pull low during download mode.
- **GPIO45**: VDD_SPI strapping pin. Configured as input with high-impedance voltage divider for VBUS sensing; does not interfere with 3.3V flash/PSRAM voltage strap.
- **GPIO46**: Boot strapping pin (must be pulled LOW during reset for normal boot). Open-drain active-low signals or floating pull-down verified.
- **GPIO3**: Connected to common I2S Mic Clock. Free GPIO, no bootstrapping constraint.
- **GPIO19/GPIO20**: Dedicated native USB Full-Speed D- / D+ peripheral lines connected to USB-C receptacle for firmware flashing and USB CDC communication.
