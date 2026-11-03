# <PRODUCT> — Requirements (gate R: frozen before part selection)

Client: ____  Confirmed by: ____  Date: ____   Method: docs/00_REQUIREMENTS.md
Status tags: **CONFIRMED** · **PROVISIONAL** (assumption, risk noted) · **TBD** (blocks depending on it wait)

## 1. Use case & operating modes
One-day story: ...
| Mode | Trigger | What is ON | Duration / duty |
|---|---|---|---|
| OFF / ship | | nothing | |
| SLEEP | | RTC, ... | |
| ACTIVE | | | |
| CHARGING | | | |
| FAULT | | all loads OFF | |

## 2. Requirement table (all 10 dimensions)
| ID | Dimension | Requirement | Value / limit | Source | Status | Risk if wrong |
|---|---|---|---|---|---|---|
| R-01 | Function | | | client | | |
| R-02 | Supply | input source & range | e.g. USB-C 4.5–5.5 V | | | |
| R-03 | Budget | battery life / avg current | | | | |
| R-04 | Interfaces | | | | | |
| R-05 | Mechanical | outline / max height T/B | e.g. 40×30 mm, 3 mm / 1 mm | | | |
| R-06 | Environmental | operating temp / IP | e.g. −20..+60 °C, IP54 | | | |
| R-07 | Regulatory | markets / radio cert | | | | |
| R-08 | Manufacturing | qty / assembler / sides | e.g. 1k, JLC, top only | | | |
| R-09 | Cost & supply | BOM target @ qty | | | | |
| R-10 | Lifecycle | OTA, variants, expansion | | | | |

## 3. Power budget
| Load | Rail | Active mA | Sleep µA | Duty | Average |
|---|---|---|---|---|---|
| **Total** | | | | | → life = capacity×0.8 / average |

## 4. Voltage tree
| Rail | Source | Min | Typ | Max | Loads |
|---|---|---|---|---|---|

## 5. Mechanical envelope
Outline drawing / file: ____ · Mounting holes: ____ · Fixed positions (connectors, buttons, LEDs, sensor ports): ____
| Zone | Max height top | Max height bottom | Keep-out reason |
|---|---|---|---|

## 6. Thermal check
| Part | Dissipation W | θJA | Tj at max ambient | Limit |
|---|---|---|---|---|

## 7. External interface table
| Connector.pin | Net | Dir | Level | Current | ESD exposure |
|---|---|---|---|---|---|

## 8. GPIO / pin budget
| MCU pin | Net | Function | Strap / boot constraint | Level at reset |
|---|---|---|---|---|
