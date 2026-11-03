# <PRODUCT> — Block plan

Order rule: decision-independent blocks first; a block whose inputs are TBD waits.

| # | Block ID | Title (frame text) | Main ICs | Ports (nets leaving the block) | Depends on | Status |
|---|---|---|---|---|---|---|
| 01 | 01_PWR_IN | USB-C INPUT + PROTECTION | USB-C, ESD | VBUS, USB_DP, USB_DM, GND | R-01 | draft |
| 02 | 02_PWR_3V3 | 3V3 REGULATOR | LDO/buck | VBUS, +3V3, GND | 01 | draft |
| 03 | 03_MCU | MCU CORE | MCU module | +3V3, GPIO nets | 02 | draft |

Status flow: `draft -> qa -> linted -> built -> verified -> accepted` (only one block between draft and accepted at a time).

## Global net names (one table for the whole product — reuse, never invent a synonym)
| Net | Meaning | Driven by | Used by |
|---|---|---|---|
| GND | single ground | — | all |
| +3V3 | logic rail | 02 | all |
