# <PRODUCT> — Component selection (gate B)   Method: docs/00b_COMPONENT_SELECTION.md

## 1. Key part decisions (one section per IC / module / sensor / connector)

### <Function, e.g. 3V3 regulator>  — requirement IDs: R-02, R-03, R-05
Derived need: Vin 3.0–5.5 V, Iout ≥ 300 mA (peak 250 mA × 1.2), Iq < 5 µA, height < 1.2 mm, −20..+60 °C

| Filter | Candidate A | Candidate B | Candidate C |
|---|---|---|---|
| MPN / LCSC | | | |
| F1 function | | | |
| F2 operating range | | | |
| F3 key numbers (margin) | | | |
| F4 package / height | | | |
| F5 stock / sources / lifecycle | | | |
| F6 unit cost @ qty | | | |
| F7 ref design / EasyEDA symbol | | | |
| **Verdict** | ✅ chosen | ❌ reason | ❌ reason |

Reason (one line): ...

## 2. Preferred passive set for this product
| Type | Values | Package | Rating | LCSC (basic?) |
|---|---|---|---|---|
| R | 0R, 1k, 4.7k, 10k, 47k, 100k | 0402 | 1 % 62.5 mW | |
| C | 100 nF / 1 µF / 10 µF | 0402 / 0402 / 0603 | 16 V X5R/X7R | |

## 3. Risks
| Part | Risk (stock, EOL, single source, thermal) | Fallback |
|---|---|---|
