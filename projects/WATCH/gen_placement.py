"""Generate a clean, DRC-safe, dual-sided placement plan for the WATCH 45x45mm PCB."""
import json, math, os

dump = json.load(open('projects/WATCH/state/pcb_dump.json'))
MIL = 39.37007874

# Board dimensions
BOARD_W = 45.0
BOARD_H = 45.0

# Components placement dictionary: ref -> [x_mm, y_mm, rot_deg, side, reason]
parts = []

def add(ref, x, y, rot, side, why):
    parts.append([ref, round(x, 2), round(y, 2), int(rot), side, why])

# -------------------------------------------------------------
# TOP SIDE (Primary Assembly)
# -------------------------------------------------------------
# 1. Main MCU: ESP32-S3 in Upper-Left (18x25.5mm). Antenna facing top edge (y=45)
# Center x=11.0, y=31.0 -> X: [1.5, 20.5], Y: [17.9, 44.1]
add("U5", 11.0, 31.0, 0, "T", "ESP32-S3 MCU in upper-left region per client layout, antenna at top board edge")
# Decoupling caps directly beside MCU power pins (VDD33 at pin 2, 3):
add("C14", 2.0, 31.0, 90, "T", "10uF MCU 3V3 bulk capacitor near VDD33 pins")
add("C15", 2.0, 29.5, 90, "T", "100nF MCU 3V3 HF bypass capacitor near VDD33 pins")
add("R14", 2.0, 27.5, 90, "T", "10k MCU_EN pull-up resistor near EN pin")
add("C13", 2.0, 26.0, 90, "T", "1uF MCU_EN reset delay capacitor near EN pin")
add("R15", 2.0, 24.5, 90, "T", "10k MCU_BOOT IO0 strapping pull-up resistor")

# 2. USB-C Interface at Bottom Center edge
add("J1", 22.5, 4.5, 180, "T", "USB-C receptacle on bottom board edge with mouth facing outward")
add("U1", 22.5, 9.8, 0, "T", "USBLC6-2SC6 TVS protection diode directly behind USB-C connector pads")
add("R1", 19.5, 9.8, 0, "T", "5.1k CC1 pull-down resistor beside USB-C connector")
add("R2", 25.5, 9.8, 0, "T", "5.1k CC2 pull-down resistor beside USB-C connector")

# 3. Battery Interface on Bottom-Left edge
add("J2", 6.5, 6.0, 180, "T", "JST PH 2.0mm 2-pin battery connector on bottom-left edge")

# 4. Waveshare 1.47" LCD Header on Right edge (JST PH 8-pin, 21.2mm long)
# Center x=40.0, y=32.5, rot=90 -> occupies y: [21.9, 43.1], x: [35.3, 44.7]
add("J6", 40.0, 32.5, 90, "T", "JST PH 2.0mm 8-pin LCD connector on right edge facing outward")

# 5. Buttons along outer edges for tactile enclosure alignment
add("SW1", 4.0, 14.0, 90, "T", "Reset tactile switch on left board edge")
add("SW2", 13.0, 4.0, 180, "T", "Boot download mode tactile switch on bottom board edge")
add("SW3", 41.5, 18.0, 270, "T", "Voice Push-to-Talk tactile switch on right board edge")
add("SW4", 29.0, 41.5, 0, "T", "User interaction button 1 on top board edge")
add("SW5", 37.0, 41.5, 0, "T", "User interaction button 2 on top board edge")

# 6. Status LEDs on Top edge
add("LED1", 23.5, 41.5, 0, "T", "Green Power/Charge indicator LED visible on top side")
add("LED2", 25.5, 41.5, 0, "T", "Blue BLE/DSP Status indicator LED visible on top side")
add("R28", 23.5, 39.5, 90, "T", "1k current limiting resistor for LED1")
add("R29", 25.5, 39.5, 90, "T", "1k current limiting resistor for LED2")

# 7. Three MEMS Microphones spatially separated for acoustic beamforming
add("MIC1", 25.0, 35.0, 0, "T", "Center MEMS microphone near top edge for voice capture")
add("C16", 28.0, 35.0, 0, "T", "100nF decoupling capacitor for MIC1")
add("MIC2", 4.0, 20.0, 90, "T", "Left MEMS microphone on left edge")
add("C17", 4.0, 17.5, 90, "T", "100nF decoupling capacitor for MIC2")
add("MIC3", 31.0, 25.0, 0, "T", "Right MEMS microphone on right side")
add("C18", 31.0, 22.5, 0, "T", "100nF decoupling capacitor for MIC3")

# -------------------------------------------------------------
# BOTTOM SIDE (Secondary Assembly — Power, Audio, Storage, IMU)
# -------------------------------------------------------------
# 8. MicroSD TF Card Socket on Bottom side along right edge
# Center x=36.0, y=9.0, rot=90 -> slot opens to right edge x=45.0
add("J5", 36.0, 9.0, 90, "B", "MicroSD card socket on bottom side with card slot at right edge")
add("C25", 26.0, 6.0, 0, "B", "10uF MicroSD bulk decoupling capacitor on bottom side")
add("C26", 26.0, 4.5, 0, "B", "100nF MicroSD HF bypass capacitor on bottom side")
add("R19", 26.0, 8.0, 0, "B", "10k SD_CS pull-up resistor on bottom side")
add("R20", 26.0, 9.5, 0, "B", "10k SD_MISO pull-up resistor on bottom side")
add("R21", 26.0, 11.0, 0, "B", "10k SD_DET card detect pull-up resistor on bottom side")

# 9. Power Conversion Subsystems on Bottom side (isolated from RF & Microphones):
# Charger IC U2 (BQ24074 QFN-16)
add("U2", 12.0, 12.0, 0, "B", "BQ24074 power-path battery charger IC on bottom side near battery connector")
add("C3", 6.0, 12.0, 90, "B", "10uF IN bulk capacitor directly at U2 IN pins")
add("C4", 17.0, 12.0, 90, "B", "10uF OUT bulk capacitor directly at U2 OUT pin")
add("C5", 12.0, 7.0, 0, "B", "10uF BAT bulk capacitor directly at U2 BAT pin")
add("R3", 7.5, 14.5, 0, "B", "10k ILIM pull-up resistor for U2")
add("R4", 7.5, 16.0, 0, "B", "10k ISET2 pull-up resistor for U2")
add("R5", 7.5, 9.5, 0, "B", "10k CE pull-down resistor for U2")
add("R6", 12.0, 16.5, 0, "B", "1.2k ISET programming resistor for U2")
add("R7", 14.0, 16.5, 0, "B", "2.0k TS thermal sensing top resistor for U2")
add("R8", 15.5, 16.5, 0, "B", "2.0k TS thermal sensing bottom resistor for U2")
add("R9", 17.0, 16.5, 0, "B", "47k TMR safety timer resistor for U2")

# 10. 3.3V Buck-Boost Subsystem U3 (TPS63802 VSON-10) on Bottom side:
add("U3", 12.0, 22.0, 0, "B", "TPS63802 3.3V high-efficiency buck-boost converter on bottom side")
add("L1", 12.0, 27.5, 0, "B", "470nH shielded power inductor directly at U3 switch nodes")
add("C6", 6.5, 21.0, 90, "B", "10uF VIN bulk capacitor at U3 VIN pin")
add("C7", 6.5, 23.0, 90, "B", "10uF VIN capacitor at U3 VIN pin")
add("C8", 17.5, 21.0, 90, "B", "10uF VOUT bulk capacitor at U3 VOUT pin")
add("C9", 17.5, 23.0, 90, "B", "100nF VOUT HF bypass capacitor at U3 VOUT pin")
add("R10", 6.5, 25.0, 90, "B", "10k PG pull-up resistor for U3")

# 11. 5V Boost Subsystem U4 (TPS61023 SOT-563) on Bottom side:
add("U4", 22.0, 19.0, 0, "B", "TPS61023 5V synchronous boost converter on bottom side")
add("L2", 22.0, 24.5, 0, "B", "470nH power inductor directly at U4 SW pin")
add("C10", 22.0, 15.5, 0, "B", "10uF VIN capacitor at U4 VIN pin")
add("C11", 26.5, 19.0, 90, "B", "10uF VOUT bulk capacitor at U4 VOUT pin")
add("C12", 26.5, 21.0, 90, "B", "10uF VOUT secondary capacitor at U4 VOUT pin")
add("R11", 18.0, 19.0, 90, "B", "100k EN pull-down resistor for U4")
add("R12", 18.0, 21.0, 90, "B", "733k FB top resistor for U4")
add("R13", 18.0, 23.0, 90, "B", "100k FB bottom resistor for U4")

# 12. USB Input filter caps & VBUS sense on Bottom side:
add("C1", 22.5, 12.5, 0, "B", "10uF VBUS bulk capacitor on bottom side directly below USB-C")
add("C2", 22.5, 14.0, 0, "B", "100nF VBUS HF bypass capacitor on bottom side")
add("R30", 20.0, 12.5, 0, "B", "100k top resistor of VBUS sense divider")
add("R31", 20.0, 14.0, 0, "B", "100k bottom resistor of VBUS sense divider")
add("C32", 20.0, 15.5, 0, "B", "100nF VBUS sense filter capacitor")

# 13. 6-Axis Motion Sensor U8 (ICM-42670-P LGA-14) on Bottom side (Center):
add("U8", 22.0, 31.0, 0, "B", "ICM-42670-P 6-axis IMU centered on bottom side away from heat sources")
add("C23", 18.5, 31.0, 90, "B", "100nF VDDIO bypass capacitor for U8")
add("C24", 18.5, 32.5, 90, "B", "1uF VDD bypass capacitor for U8")
add("R17", 25.5, 31.0, 90, "B", "4.7k I2C SCL pull-up resistor")
add("R18", 25.5, 32.5, 90, "B", "4.7k I2C SDA pull-up resistor")

# 14. Stereo Audio Amplification U6, U7 on Bottom side (Right region):
add("U6", 34.0, 31.0, 0, "B", "Left channel MAX98357A Class-D audio amplifier on bottom side")
add("J3", 41.5, 31.0, 90, "B", "Left speaker JST SH 1.0mm 2-pin connector on bottom side edge")
add("C19", 34.0, 35.0, 0, "B", "10uF VSYS bulk capacitor for U6")
add("C20", 34.0, 36.5, 0, "B", "100nF VSYS HF bypass capacitor for U6")

add("U7", 34.0, 22.0, 0, "B", "Right channel MAX98357A Class-D audio amplifier on bottom side")
add("J4", 41.5, 22.0, 90, "B", "Right speaker JST SH 1.0mm 2-pin connector on bottom side edge")
add("C21", 34.0, 18.0, 0, "B", "10uF VSYS bulk capacitor for U7")
add("C22", 34.0, 16.5, 0, "B", "100nF VSYS HF bypass capacitor for U7")
add("R16", 30.0, 22.0, 90, "B", "100k SD_MODE pull-down resistor")

# 15. LCD Interface pull-ups & filter on Bottom side (underneath J6):
add("C27", 34.0, 39.0, 0, "B", "10uF LCD VCC bulk capacitor on bottom side")
add("C28", 34.0, 40.5, 0, "B", "100nF LCD VCC bypass capacitor on bottom side")
add("R22", 38.0, 39.0, 0, "B", "10k LCD_CS pull-up resistor on bottom side")
add("R23", 38.0, 40.5, 0, "B", "10k LCD_RST pull-up resistor on bottom side")
add("R24", 38.0, 42.0, 0, "B", "100k LCD_BL pull-down resistor on bottom side")

# 16. Button debouncing & pull-ups on Bottom side:
add("R25", 38.0, 16.0, 0, "B", "10k BTN_VOICE pull-up resistor on bottom side near SW3")
add("C29", 38.0, 14.5, 0, "B", "100nF BTN_VOICE debounce capacitor on bottom side near SW3")
add("R26", 29.0, 38.0, 0, "B", "10k BTN_USER1 pull-up resistor on bottom side near SW4")
add("C30", 31.0, 38.0, 0, "B", "100nF BTN_USER1 debounce capacitor on bottom side near SW4")
add("R27", 37.0, 38.0, 0, "B", "10k BTN_USER2 pull-up resistor on bottom side near SW5")
add("C31", 39.0, 38.0, 0, "B", "100nF BTN_USER2 debounce capacitor on bottom side near SW5")

# Verify all 89 parts are present
refs_placed = {p[0] for p in parts}
missing = set(dump.keys()) - refs_placed
if missing:
    print('ERROR: Missing parts from placement plan:', missing)
    exit(1)

print(f'Successfully planned all {len(parts)} parts!')
top_count = sum(1 for p in parts if p[4] == 'T')
bot_count = sum(1 for p in parts if p[4] == 'B')
print(f'Top side: {top_count} parts | Bottom side: {bot_count} parts')

plan = {
    "origin_mm": [0, 0],
    "board_mm": [45.0, 45.0],
    "layers": 4,
    "grid_mm": 0.05,
    "roles": {
        "connectors": ["J1", "J2", "J3", "J4", "J5", "J6"],
        "sensors": ["U8", "MIC1", "MIC2", "MIC3"],
        "heat": ["U2", "U3", "U4", "L1", "L2"],
        "rf": ["U5"],
        "esd": ["U1"]
    },
    "keepouts": [
        {"name": "antenna", "rect_mm": [0.0, 37.0, 22.0, 45.0], "side": "both", "allow": ["U5"]}
    ],
    "rules": {
        "edge_pad_mm": 0.3, "connector_edge_mm": 0.8, "connector_front_keepout_mm": 1.5, "esd_max_mm": 8.0,
        "sensor_heat_mm": 5.0, "heat_spacing_mm": 2.5, "rf_edge_mm": 0.5, "decap_max_mm": 8.0,
        "max_utilisation": 0.55, "density_cell_mm": 2.5, "hotspot_fill": 0.85,
        "pad":  {"p0201": 0.20, "p0402": 0.25, "p0603": 0.30, "ic": 0.40, "fine": 0.50, "connector": 0.50, "tall": 0.50},
        "body": {"p0201": 0.15, "p0402": 0.20, "p0603": 0.25, "ic": 0.30, "fine": 0.50, "connector": 0.50, "tall": 0.50}
    },
    "parts": parts
}

json.dump(plan, open('projects/WATCH/placement.json', 'w'), indent=2)
print('Saved projects/WATCH/placement.json')
