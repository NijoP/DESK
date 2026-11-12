# UPS_1000 rev A — Fabrication and assembly notes (LOW-VOLTAGE PROTOTYPE ONLY)

**Not for mains or high-voltage use.** SELV ≤ 60 V DC board. No safety isolation, no IEC 62040 / IEC 60664 compliance claimed. Release subject to Captain review; no order placed.

## Fabrication
| Item | Requirement | Status |
|---|---|---|
| Size | 160 × 120 mm, R2 mm corners | live outline VERIFIED (tools/pcb_board.py readback) |
| Layers | 4 | live copper-layer count VERIFIED = 4 |
| Thickness | 2.0 mm | client requirement; **fabricator stackup (core/prepreg thicknesses) TBD** (M-13) |
| Copper | L1 2 oz / L2 1 oz / L3 1 oz / L4 2 oz | client requirement; must be ordered explicitly (not the fab default) |
| Material | FR-4, Tg ≥ 170 °C (high-Tg) | client proposal; thermal calc shows ≤ 92 °C hottest part at 40 °C ambient |
| Stackup use | L1 components + power polygons · L2 GND plane · L3 **GND plane (deviation from client "DC distribution", ledger decision)** · L4 signals/aux | |
| Min track / space / drill | per JLCPCB 4-layer preset (3.5 mil / 3.5 mil / 8 mil floor, DESK MFG-MIN-070 / MFG-DRILL-071) | see DRC report |
| Clearance on VBUS-class nets (≤ 70.4 V) | 0.6 mm (IPC-2221B B2 per desk.ipc — **table transcription UNVERIFIED** in DESK) | functional spacing only |
| Impedance control | none required (CAN 1 Mb/s, UART, SWD electrically short) | N/A, stated |
| Mounting holes | 4 × M4 (Ø4.3 mm NPTH) at (5,5), (155,5), (5,115), (155,115) mm | **NOT CREATED**: no verified EasyEDA API for NPTH holes (pcb_PrimitivePad.create has no signature in DESK's API reference). Keep-out regions Ø9 mm are reserved in placement/routing/copper. Holes must be added before fabrication → **release blocker** |
| Surface finish / mask / silk | ENIG recommended (TDSON/LQFP); green mask; white silk | builder recommendation |

## Assembly
* Top-side SMT only. THT: J1, J5 (5.0 mm terminals), J2/J3/J4/J6/J7 headers — hand solder.
* Polarity checks before reflow: C1/C2 electrolytic (+ = pad 1, **verify footprint silkscreen**, V-09), D1 SMBJ60A (cathode = VBUS), D5 STPS1H100A (cathode = BST), LEDs D2/D3, U1–U9 pin 1.
* Q1/Q2 exposed drain pads: full solder coverage; no thermal relief on power pads (COPPER-RELIEF-042).
* Do not fit a heatsink electrically connected to Q1 drain without insulation (drain = VBUS).

## Bring-up procedure (mandatory order)
1. Lab supply 24 V, current limit **0.5 A**, polarity checked (RK-01: reverse polarity not safely protected).
2. Verify 12 V / 5 V / 3.3 V; UCC21520 DIS high (driver disabled) at reset.
3. Flash firmware via SWD; configure TIM1 BKIN (active low) **before** enabling PWM (RK-04).
4. Check FAULT_N chain with an injected ISENSE / NTC / VBUS_SNS level before switching.
5. Switch at 20 kHz into a resistive load, then the external LC filter (L ≥ 200 µH at 24 V for 30 % ripple, block 07 qa).
6. Thermal-camera check at 5 A RMS before claiming any rating (THERMAL_ASSESSMENT.md).
