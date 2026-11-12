# UPS_1000 rev A — Thermal assessment (CALCULATED, not measured)

Status: **hand calculation**. DESK rule THERM-TJ-050 (junction temperature) is **UNSUPPORTED** by any DESK engine, so nothing here is engine-verified and no thermal measurement exists. Bring-up must include a thermal-camera check at 5 A RMS before any rating is claimed.

Basis: Ta = 40 °C lab ambient (REQUIREMENTS R-06, PROVISIONAL), natural convection (fan header present, fan not assumed), VBUS worst case 58.4 V, phase current 5 A RMS continuous / 10 A peak (HW trip), fsw 20 kHz. Datasheet values from `live-test/ups-1000/requirements/DATASHEET_FACTS.md`.

| Part | Loss model | Loss (W) | θ used | Tj / T est. | Limit | Margin | Source |
|---|---|---:|---|---:|---:|---|---|
| Q1, Q2 BSC070N10NS3 G (each) | Pcond = I²·RDS(on)max·1.5 (hot)·0.5 (duty) = 25·0.007·1.5·0.5; Psw = ½·V·Ipk·(tr+tf)·f = ½·58.4·10·40 ns·20 kHz (tr+tf ASSUMED 40 ns, conservative peak current) | 0.13 + 0.23 = **0.36** | RthJA 50 K/W (6 cm² Cu, datasheet Table 3) | **58 °C** | 150 °C | 92 K | BSC070N10NS3 Tables 3, 4, 6 |
| R24 shunt 5 mΩ 2512 | I²R | 0.125 (0.5 W at 10 A transient) | — | — | 2 W rating | 6 % | calc |
| U1 LM5164 | 12 V × 0.343 A = 4.1 W out at η ≈ 85 % (ASSUMED) → 0.73 W total, IC share ≈ 0.4 W | 0.4 | ~40 K/W (DDA + pad, ASSUMED) | 56 °C | 150 °C | — | calc; η and θ TO VERIFY with datasheet curves |
| U3 AP2112K-3.3 | (5 − 3.3) × 0.122 | 0.21 | ~250 K/W SOT-23-5 (ASSUMED) | 92 °C | 125 °C | 33 K | calc |
| U2 TPS54202 | 0.65 W out, η ≈ 85 % | ~0.1 | — | low | 150 °C | — | calc |
| U7 UCC21520 | Qg·VDD·f ×2 + quiescent ≈ 2 × 13 mW + 30 mW | ~0.06 | — | low | 150 °C | — | calc |
| C1/C2 100 µF Al | bus ripple ≈ 2.5 A RMS shared with 3 × 2.2 µF MLCC | **TO VERIFY** | — | — | Vishay 140 CRH ripple rating not retrieved | — | V-02 |

## Conductor heating (desk.ipc, IPC-2221 chart formula — table transcription UNVERIFIED in DESK)
| Net class | Current | Required width 2 oz outer ΔT 10 °C | ΔT 20 °C | Implemented |
|---|---|---|---|---|
| VBUS / SW / PHASE / GND / VIN_RAW | 10 A pk / 5 A RMS | 3.62 mm (10 A) / 1.39 mm (5 A) | 2.38 / 0.91 mm | see COPPER / ROUTING records (polygon + 120 mil router target) |
| Via transitions | 10 A | 13 × 0.3 mm (12 mil) drill or 10 × 0.5 mm | — | see routing record |

## Conclusions
* At the rev-A rating (5 A RMS, ≤ 58.4 V) no heatsink and no forced air are required by calculation; the margin to Tj max is > 90 K on the FETs.
* The calculation is **not** valid for the 800 W system power stage (380 V DC link, IGBT/SiC); that stage needs its own thermal design (heatsink Rth, airflow CFM — missing requirement M-08).
* THERM-TJ-050 / THERM-COPPER-051 remain review items; a measured thermal test is required before release.
