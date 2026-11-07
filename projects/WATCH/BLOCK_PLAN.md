# WATCH — Block plan

Order rule: decision-independent blocks first; power subsystems first, then MCU core, then input/output peripherals.

| # | Block ID | Title (frame text) | Main ICs | Ports (nets leaving the block) | Depends on | Status |
|---|---|---|---|---|---|---|
| 01 | 01_PWR_IN | USB-C INPUT AND ROLE DETECTION | TYPE-C-31-M-12, TPD2E2U06 | VBUS, USB_DP, USB_DM, USB_CC1, USB_CC2, GND | R-09 | draft |
| 02 | 02_BAT_CHG | BATTERY CHARGING AND POWER PATH | BQ24074RGTR | VBUS, VBAT, VSYS, CHG_STAT, CHG_EN, GND | 01, R-10 | draft |
| 03 | 03_PWR_3V3 | 3.3V POWER REGULATOR | TPS63802DLAR | VSYS, +3V3, GND | 02, R-11 | draft |
| 04 | 04_PWR_BOOST | 5V BOOST POWER OUTPUT | TPS61023DRLR | VBAT, VBUS, VBUS_BOOST_EN, GND | 01, 02, R-12 | draft |
| 05 | 05_MCU_CORE | ESP32-S3 MCU CORE | ESP32-S3-WROOM-1-N8R8 | +3V3, MCU_EN, MCU_BOOT, all peripheral GPIOs, GND | 03, R-01 | draft |
| 06 | 06_USB_PROG | USB PROGRAMMING AND DEBUG | ESD protection, Auto-Reset | USB_DP, USB_DM, MCU_EN, MCU_BOOT, VBUS_SENSE, GND | 01, 05, R-19 | draft |
| 07 | 07_AUDIO_IN | THREE-MICROPHONE AUDIO INPUT | 3x ICS-43434 MEMS Microphones | +3V3, I2S_MIC_CLK, I2S_MIC_WS, I2S_MIC_SD1, I2S_MIC_SD2, GND | 03, 05, R-02 | draft |
| 08 | 08_AUDIO_OUT | STEREO CLASS-D AUDIO OUTPUT | 2x MAX98357A Amplifiers, Headers | VSYS, I2S_SPK_BCLK, I2S_SPK_WS, I2S_SPK_DOUT, AMP_SD_MODE, GND | 02, 05, R-03 | draft |
| 09 | 09_IMU_MOTION | IMU AND MOTION DETECTION | ICM-42670-P | +3V3, I2C_SDA, I2C_SCL, IMU_INT1, GND | 03, 05, R-04 | draft |
| 10 | 10_STORAGE | MICROSD STORAGE | TF-01A-SMD | +3V3, SD_SPI_MOSI, SD_SPI_MISO, SD_SPI_CLK, SD_CS, SD_DET, GND | 03, 05, R-07 | draft |
| 11 | 11_LCD_DISP | WAVESHARE LCD INTERFACE | S8B-PH-SM4-TB (PH2.0 8-pin) | +3V3, LCD_SCL, LCD_SDA, LCD_RST, LCD_DC, LCD_CS, LCD_BL, GND | 03, 05, R-08 | draft |
| 12 | 12_BUTTONS | FIVE PHYSICAL BUTTONS | 5x TS-1187A Tactile Switches | MCU_EN, MCU_BOOT, BTN_VOICE, BTN_USER1, BTN_USER2, GND | 05, R-05 | draft |
| 13 | 13_STATUS_LEDS| TWO STATUS LEDs | 2x 0603 LEDs (Red, Blue) | +3V3, LED_PWR, LED_STAT, GND | 05, R-06 | draft |
| 14 | 14_CONNECTORS | CONNECTORS AND TEST POINTS | Speaker Headers, Battery Pads, TPs | VBAT, VSYS, +3V3, GND, SPK_L_P/N, SPK_R_P/N | All | draft |

Status flow: draft -> qa -> linted -> built -> verified -> accepted (one block at a time).

## Global net names (one table for the whole product — reuse, never invent a synonym)
| Net | Meaning | Driven by | Used by |
|---|---|---|---|
| GND | Single continuous ground system | System ground plane | All blocks |
| VBUS | USB-C 5V bus (input or boost output) | 01_PWR_IN / 04_PWR_BOOST | 02_BAT_CHG, 06_USB_PROG |
| VBAT | Battery positive terminal (3.0V–4.2V) | 1S LiPo Battery | 02_BAT_CHG, 04_PWR_BOOST, 14_CONN |
| VSYS | System power-path output rail (3.3V–4.4V)| 02_BAT_CHG | 03_PWR_3V3, 08_AUDIO_OUT |
| +3V3 | Regulated digital and analog 3.3V rail | 03_PWR_3V3 | 05, 07, 09, 10, 11, 13 |
| USB_DP | USB Full-Speed Data Positive | 01_PWR_IN | 05_MCU_CORE, 06_USB_PROG |
| USB_DM | USB Full-Speed Data Negative | 01_PWR_IN | 05_MCU_CORE, 06_USB_PROG |
| MCU_EN | MCU Enable and Reset line | 05_MCU_CORE, 12_BUTTONS | 06_USB_PROG |
| MCU_BOOT | MCU Firmware Boot Select line | 05_MCU_CORE, 12_BUTTONS | 06_USB_PROG |
| I2S_MIC_CLK | Common Bit Clock for 3 MEMS Microphones| 05_MCU_CORE | 07_AUDIO_IN |
| I2S_MIC_WS | Left Mics L/R Word Select | 05_MCU_CORE | 07_AUDIO_IN |
| I2S_MIC_SD1 | Left Microphones multiplexed Data Line | 07_AUDIO_IN | 05_MCU_CORE |
| I2S_MIC_SD2 | Right Microphone Data Line | 07_AUDIO_IN | 05_MCU_CORE |
| I2S_SPK_BCLK| Stereo Speaker Class-D Bit Clock | 05_MCU_CORE | 08_AUDIO_OUT |
| I2S_SPK_WS | Stereo Speaker Word Select | 05_MCU_CORE | 08_AUDIO_OUT |
| I2S_SPK_DOUT| Stereo Speaker Serial Audio Data | 05_MCU_CORE | 08_AUDIO_OUT |
| AMP_SD_MODE | Audio Amplifier Shutdown and Mode Select| 05_MCU_CORE | 08_AUDIO_OUT |
| I2C_SDA | Sensor I2C Serial Data line | 05_MCU_CORE, 09_IMU_MOTION | Pull-up 4.7k |
| I2C_SCL | Sensor I2C Serial Clock line | 05_MCU_CORE, 09_IMU_MOTION | Pull-up 4.7k |
| IMU_INT1 | Motion Alert / Wake-on-shake Interrupt | 09_IMU_MOTION | 05_MCU_CORE |
| SD_SPI_MOSI | MicroSD Master Out Slave In | 05_MCU_CORE | 10_STORAGE |
| SD_SPI_MISO | MicroSD Master In Slave Out | 10_STORAGE | 05_MCU_CORE |
| SD_SPI_CLK | MicroSD Serial Clock | 05_MCU_CORE | 10_STORAGE |
| SD_CS | MicroSD Dedicated Chip Select | 05_MCU_CORE | 10_STORAGE |
| SD_DET | MicroSD Mechanical Card Detect switch | 10_STORAGE | 05_MCU_CORE |
| LCD_SCL | Waveshare LCD SPI Clock | 05_MCU_CORE | 11_LCD_DISP |
| LCD_SDA | Waveshare LCD SPI MOSI | 05_MCU_CORE | 11_LCD_DISP |
| LCD_RST | Waveshare LCD Hardware Reset | 05_MCU_CORE | 11_LCD_DISP |
| LCD_DC | Waveshare LCD Data / Command Control | 05_MCU_CORE | 11_LCD_DISP |
| LCD_CS | Waveshare LCD Dedicated Chip Select | 05_MCU_CORE | 11_LCD_DISP |
| LCD_BL | Waveshare LCD Backlight PWM Dimming | 05_MCU_CORE | 11_LCD_DISP |
| BTN_VOICE | User Button 3 (Press & Hold Voice Capture)| 12_BUTTONS | 05_MCU_CORE |
| BTN_USER1 | User Button 4 (Configurable Interaction 1)| 12_BUTTONS | 05_MCU_CORE |
| BTN_USER2 | User Button 5 (Configurable Interaction 2)| 12_BUTTONS | 05_MCU_CORE |
| LED_PWR | Power / Charging Status LED indicator | 05_MCU_CORE | 13_STATUS_LEDS |
| LED_STAT | Bluetooth / DSP Processing Status LED | 05_MCU_CORE | 13_STATUS_LEDS |
| VBUS_BOOST_EN| 5V Boost Enable for OTG Output | 05_MCU_CORE | 04_PWR_BOOST |
| VBUS_SENSE | VBUS Voltage Divider Sense Input | 06_USB_PROG | 05_MCU_CORE |
| CHG_STAT | Battery Charge State Output | 02_BAT_CHG | 05_MCU_CORE |
| CHG_EN | Battery Charger Enable / Current Select | 05_MCU_CORE | 02_BAT_CHG |
