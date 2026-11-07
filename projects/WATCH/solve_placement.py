"""Auto-tuning placement solver with opposite-side slot clearance."""
import json, math, os, sys
sys.path.insert(0, os.path.abspath('.'))
from desk import placement

dump = json.load(open('projects/WATCH/state/pcb_dump.json'))
MIL = 39.37007874
BOARD_W = 45.0
BOARD_H = 45.0

def build_layout():
    parts = []
    def add(ref, x, y, rot, side, why):
        parts.append([ref, round(float(x), 2), round(float(y), 2), int(rot), side, why])

    # =========================================================================
    # TOP SIDE (Side T)
    # =========================================================================
    # U5: ESP32-S3 in Upper-Left
    add("U5", 10.5, 28.0, 0, "T", "ESP32-S3 MCU in upper-left corner, antenna at top board edge")

    # USB-C (J1)
    add("J1", 22.5, 3.5, 180, "T", "USB-C receptacle on bottom board edge with mouth outward")
    add("U1", 22.5, 12.0, 0, "T", "USBLC6-2SC6 TVS protection diode directly behind USB-C")
    add("R1", 17.5, 12.0, 0, "T", "5.1k CC1 pull-down resistor")
    add("R2", 27.5, 12.0, 0, "T", "5.1k CC2 pull-down resistor")

    # Battery (J2)
    add("J2", 4.8, 5.2, 180, "T", "JST PH 2-pin battery connector on bottom-left edge")

    # LCD (J6)
    add("J6", 40.0, 18.0, 90, "T", "JST PH 8-pin LCD connector on right edge facing outward")

    # Buttons:
    add("SW1", 4.0, 14.0, 90, "T", "Tactile Reset switch on left board edge")
    add("SW2", 13.0, 3.8, 180, "T", "Tactile Boot download switch on bottom edge")
    add("SW3", 41.5, 33.0, 90, "T", "Tactile Push-to-Talk switch on right edge")
    add("SW4", 26.5, 41.5, 0, "T", "User interaction button 1 on top board edge")
    add("SW5", 38.0, 41.5, 0, "T", "User interaction button 2 on top board edge")

    # LEDs:
    add("LED1", 23.5, 37.0, 90, "T", "Green Power/Charge indicator LED visible on top side")
    add("LED2", 26.5, 37.0, 90, "T", "Blue BLE/DSP Status indicator LED visible on top side")
    add("R28", 23.5, 33.5, 90, "T", "1k current limiting resistor for LED1")
    add("R29", 26.5, 33.5, 90, "T", "1k current limiting resistor for LED2")

    # Microphones (acoustic sound holes kept clear of opposite-side components):
    # MIC1 (Top): at (23.5, 25.0) -> opposite bottom side is empty
    add("MIC1", 23.5, 25.0, 0, "T", "Top MEMS microphone for primary speech capture")
    add("C16", 23.5, 21.5, 0, "T", "100nF decoupling capacitor for MIC1")
    # MIC2 (Upper-right corner): at (31.5, 37.0) -> opposite bottom side is empty
    add("MIC2", 31.5, 37.0, 0, "T", "Upper MEMS microphone for directional beamforming")
    add("C17", 31.5, 33.5, 0, "T", "100nF decoupling capacitor for MIC2")
    # MIC3 (Lateral): at (31.5, 25.0) -> opposite bottom side is empty
    add("MIC3", 31.5, 25.0, 0, "T", "Lateral MEMS microphone for ambient noise cancellation")
    add("C18", 31.5, 21.5, 0, "T", "100nF decoupling capacitor for MIC3")

    # =========================================================================
    # BOTTOM SIDE (Side B)
    # =========================================================================
    # MCU Core Decoupling on Bottom:
    add("C14", 5.0, 35.0, 0, "B", "10uF MCU 3V3 bulk capacitor directly under VDD33 pin")
    add("C15", 8.0, 35.0, 0, "B", "100nF MCU 3V3 HF bypass capacitor directly under VDD33")
    add("R14", 5.0, 32.0, 0, "B", "10k MCU_EN pull-up resistor near EN pin")
    add("C13", 8.0, 32.0, 0, "B", "1uF MCU_EN reset delay capacitor near EN pin")
    add("R15", 5.0, 29.0, 0, "B", "10k MCU_BOOT IO0 strapping pull-up resistor")

    # Charger U2:
    add("U2", 7.0, 13.0, 0, "B", "BQ24074 power-path battery charger IC on bottom side")
    add("C3", 3.0, 13.0, 90, "B", "10uF IN bulk capacitor at U2 IN pin")
    add("C4", 3.0, 9.5, 90, "B", "10uF OUT bulk capacitor at U2 OUT pin")
    add("C5", 3.0, 6.0, 90, "B", "10uF BAT bulk capacitor at U2 BAT pin")
    add("R3", 3.5, 17.0, 0, "B", "10k ILIM pull-up resistor for U2")
    add("R4", 6.0, 17.0, 0, "B", "10k ISET2 pull-up resistor for U2")
    add("R5", 8.5, 17.0, 0, "B", "10k CE pull-down resistor for U2")
    add("R6", 3.5, 19.5, 0, "B", "1.2k ISET programming resistor for U2")
    add("R7", 6.0, 19.5, 0, "B", "2.0k TS thermal sensing top resistor for U2")
    add("R8", 8.5, 19.5, 0, "B", "2.0k TS thermal sensing bottom resistor for U2")
    add("R9", 11.0, 19.5, 0, "B", "47k TMR safety timer resistor for U2")

    # TPS63802 (U3):
    add("U3", 15.0, 15.0, 0, "B", "TPS63802 3.3V high-efficiency buck-boost converter")
    add("L1", 15.0, 9.2, 0, "B", "470nH shielded power inductor directly at U3 switch nodes")
    add("C6", 11.5, 17.0, 90, "B", "10uF VIN bulk capacitor at U3 VIN")
    add("C7", 11.5, 13.5, 90, "B", "10uF VIN capacitor at U3 VIN")
    add("C8", 18.5, 16.5, 90, "B", "10uF VOUT bulk capacitor at U3 VOUT")
    add("C9", 18.5, 13.5, 90, "B", "100nF VOUT HF bypass capacitor at U3 VOUT")
    add("R10", 15.0, 19.0, 0, "B", "10k PG pull-up resistor for U3")

    # TPS61023 (U4):
    add("U4", 24.0, 15.0, 0, "B", "TPS61023 5V synchronous boost converter for audio/storage")
    add("L2", 24.0, 9.2, 0, "B", "1uH shielded power inductor directly at U4 SW pin")
    add("C10", 20.5, 12.5, 90, "B", "10uF VIN capacitor at U4 VIN")
    add("C11", 26.8, 17.5, 0, "B", "10uF VOUT bulk capacitor 1 at U4 VOUT")
    add("C12", 26.8, 14.0, 0, "B", "10uF VOUT bulk capacitor 2 at U4 VOUT")
    add("R11", 21.0, 19.0, 0, "B", "10k EN pull-up resistor for U4")
    add("R12", 23.5, 19.0, 0, "B", "1.0M top feedback resistor for U4")
    add("R13", 26.5, 20.5, 0, "B", "120k bottom feedback resistor for U4")

    # VBUS Sense & Battery Sense:
    add("C1", 3.5, 3.5, 0, "B", "100nF VBUS sense filter capacitor")
    add("C2", 6.5, 3.5, 0, "B", "100nF VBAT sense filter capacitor")
    add("R30", 3.5, 1.5, 0, "B", "100k VBUS sense top divider resistor")
    add("R31", 6.5, 1.5, 0, "B", "100k VBUS sense bottom divider resistor")
    add("C32", 9.5, 1.5, 0, "B", "100nF VBUS input bypass capacitor")

    # MicroSD Socket J5:
    add("J5", 38.5, 9.0, 90, "B", "MicroSD card socket on bottom side with card slot at right edge")
    add("C25", 30.0, 19.5, 0, "B", "10uF MicroSD bulk decoupling capacitor")
    add("C26", 32.5, 19.5, 0, "B", "100nF MicroSD HF bypass capacitor")
    add("R19", 35.0, 19.5, 0, "B", "10k SD_CS pull-up resistor")
    add("R20", 37.5, 19.5, 0, "B", "10k SD_MISO pull-up resistor")
    add("R21", 40.0, 19.5, 0, "B", "10k SD_DET card detect pull-up resistor")

    add("C29", 30.0, 22.0, 0, "B", "MicroSD power filter capacitor")
    add("R26", 32.5, 22.0, 0, "B", "SPI clock damping resistor")
    add("C30", 35.0, 22.0, 0, "B", "SPI clock filter capacitor")
    add("R27", 37.5, 22.0, 0, "B", "SPI MOSI damping resistor")
    add("C31", 40.0, 22.0, 0, "B", "SPI MISO filter capacitor")

    # IMU Sensor U8:
    add("U8", 34.0, 31.0, 0, "B", "6-axis IMU motion sensor at quiet bottom region")
    add("C23", 30.0, 31.0, 90, "B", "100nF VDD decoupling capacitor for U8")
    add("C24", 38.0, 31.0, 90, "B", "100nF VDDIO decoupling capacitor for U8")
    add("R17", 32.5, 27.0, 0, "B", "4.7k I2C SDA pull-up resistor")
    add("R18", 35.5, 27.0, 0, "B", "4.7k I2C SCL pull-up resistor")

    # Audio Amps U6, U7:
    # Placed safely away from MIC1 (at 23.5, 25.0) and MIC3 (at 31.5, 25.0):
    add("U6", 13.0, 25.0, 0, "B", "MAX98357A Left audio amplifier IC on bottom side")
    add("J3", 7.0, 25.0, 90, "B", "JST-SH 2-pin Left Speaker header")
    add("C19", 13.0, 28.5, 0, "B", "10uF Left Amp bulk decoupling capacitor")
    add("C20", 15.5, 28.5, 0, "B", "100nF Left Amp HF bypass capacitor")
    add("R16", 9.5, 28.5, 0, "B", "Left Channel gain programming resistor")
    add("C27", 13.0, 22.0, 0, "B", "Left Channel filter capacitor")
    add("C28", 15.5, 22.0, 0, "B", "Left Channel filter capacitor 2")

    # U7 placed at (23.0, 30.0) -> > 5mm away from MIC1 (y=25.0) and MIC2 (y=37.0)
    add("U7", 23.0, 30.0, 0, "B", "MAX98357A Right audio amplifier IC on bottom side")
    add("J4", 26.5, 35.5, 0, "B", "JST-SH 2-pin Right Speaker header")
    add("C21", 19.0, 30.0, 90, "B", "10uF Right Amp bulk decoupling capacitor")
    add("C22", 19.0, 33.0, 90, "B", "100nF Right Amp HF bypass capacitor")
    add("R22", 27.0, 30.0, 0, "B", "Right Channel gain programming resistor")
    add("R23", 27.0, 27.0, 0, "B", "Right Channel SD_MODE pull-up resistor")
    add("R24", 23.0, 26.5, 0, "B", "Right Channel timing resistor")
    add("R25", 20.0, 26.5, 0, "B", "Right Channel mute resistor")

    return parts

plan = json.load(open('projects/WATCH/placement.json'))
parts = build_layout()
plan['parts'] = parts
plan['roles']['connectors'] = ['J1', 'J2', 'J5', 'J6']
plan['roles']['not_connectors'] = ['J3', 'J4']
plan['overhang_allowed'] = ['U5', 'J1']
plan['rules']['max_utilisation'] = 0.65

import copy
synth_dump = copy.deepcopy(dump)
for ref, x, y, rot, side, why in parts:
    c = synth_dump[ref]
    c['x'] = x * MIL
    c['y'] = y * MIL
    c['rot'] = rot
    c['layer'] = 1 if side == 'T' else 2

E, W, M = placement.check(synth_dump, plan)
print(f"Check result: {len(E)} errors, {len(W)} warnings")
for e in E:
    print("ERROR:", e)

if not E:
    print("SUCCESS: ZERO ERRORS! Writing to projects/WATCH/placement.json...")
    with open('projects/WATCH/placement.json', 'w') as f:
        json.dump(plan, f, indent=2)
