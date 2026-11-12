# Design Parameters - ESP32-S3 Development Board

## PCB Parameters
- **Layers**: 2-layer (cost optimized) or 4-layer (signal integrity)
- **Dimensions**: ~60mm x 40mm (target, adjustable based on layout)
- **Thickness**: 1.6mm standard
- **Copper weight**: 1oz (35µm) outer, 1oz inner if 4-layer
- **Min trace/space**: 0.127mm (5mil) / 0.127mm (5mil) - JLCPCB standard
- **Min via**: 0.3mm (12mil) drill, 0.45mm (18mil) annular - JLCPCB standard
- **Min hole**: 0.2mm (8mil) - JLCPCB standard

## Power Tree
- **Input**: USB-C VBUS (5V, up to 500mA default, negotiable to 1.5A/3A)
- **Regulation**: 5V → 3.3V LDO (AP2112K-3.3 or equivalent, 600mA+) or buck converter
- **ESP32-S3 VDD**: 3.3V ±10% (3.0V - 3.6V)
- **ESP32-S3 VDD_SPI**: 3.3V or 1.8V (tied to 3.3V for simplicity)
- **USB PHY**: 3.3V (internal to ESP32-S3)
- **Decoupling**: 10µF + 1µF + 100nF per power domain per datasheet

## ESP32-S3 Module Selection Criteria
- **Variant**: ESP32-S3-WROOM-1 (PCB antenna) or ESP32-S3-WROOM-1U (U.FL connector)
- **Flash**: 4MB, 8MB, or 16MB (prefer 8MB+ for development)
- **PSRAM**: 2MB or 8MB (prefer 8MB for development)
- **Temperature**: -40°C to +85°C industrial grade
- **LCSC Availability**: Must be in stock at LCSC
- **Footprint**: 18×25.5mm castellated module, 38 pins (0.5mm pitch)

## USB-C Interface
- **Connector**: USB-C receptacle, 16-pin or 24-pin (through-hole or SMT)
- **Data lines**: D+/D- direct to ESP32-S3 GPIO19/GPIO20 (USB PHY)
- **CC pins**: CC1/CC2 with 5.1kΩ pulldown resistors (USB 2.0)
- **VBUS**: Direct to 5V rail with protection
- **ESD Protection**: 4-channel TVS diode array (e.g., ESD1254, TPD4E001)
- **Common Mode Choke**: Optional for EMI (e.g., DLW21SN900HQ2)

## Reset Circuit
- **EN Pin**: Active-high enable, pulled up to 3.3V
- **Reset Button**: Pulls EN low when pressed
- **RC Delay**: 10kΩ + 1µF for power-on reset delay
- **USB Serial DTR/RTS**: Optional auto-reset for programming (if using USB-UART bridge)

## Boot/Strapping Circuit
- **GPIO0 (BOOT)**: Pulled up, button to GND for bootloader entry
- **GPIO45**: Pulled down (strapping)
- **GPIO46**: Pulled down (strapping) 
- **GPIO3 (RX0)**: Pulled up (strapping)
- **GPIO4 (TX0)**: Pulled up (strapping)
- **GPIO5**: Pulled up (strapping)
- **GPIO6**: Pulled up (strapping)
- **GPIO7**: Pulled up (strapping)
- **GPIO15**: Pulled up (strapping)
- **GPIO16**: Pulled up (strapping)
- **GPIO17**: Pulled up (strapping)

## GPIO Headers
- **Pitch**: 2.54mm (0.1") standard
- **Pin count**: 2×20 or 2×13 + 2×7 (all usable GPIOs)
- **Power pins**: 3V3, 5V, GND distributed
- **Labels**: GPIO numbers, special functions (ADC, DAC, SPI, I2C, UART, PWM)

## Indicators
- **Power LED**: Green, on 3.3V rail (with current limiting resistor)
- **Status LED**: Blue/Red, on GPIO48 (built-in WS2812 on some modules) or dedicated GPIO
- **USB Activity**: Optional, on USB suspend/enumeration status

## Protection
- **USB ESD**: 4-line TVS on D+/D-/CC1/CC2
- **GPIO ESD**: Optional TVS on exposed headers
- **Reverse polarity**: Schottky diode or P-MOSFET on VBUS input
- **Overcurrent**: Polyfuse or eFuse on VBUS (500mA-1A)

## Mechanical
- **Mounting holes**: 4× M3 (3mm) or M2.5, 3mm clearance
- **Board outline**: Rectangular with rounded corners
- **USB-C placement**: Centered on short edge
- **Button placement**: Accessible at board edge
- **Header placement**: Long edges for breadboard compatibility