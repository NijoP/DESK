# DESK Weft programs

Weft orchestrates. DESK engineers. Documentation: [`docs/weft/`](../../docs/weft/); start with
[`04_STATUS.md`](../../docs/weft/04_STATUS.md).

| Path | What |
|---|---|
| `WEFT_PIN.json` | The upstream Weft commit this integration is written and compiled against |
| `nodes/desk/` | One typed Weft group per DESK node. **Generated** from `desk/weft/contracts.py` by `python desk.py weft gen`; do not edit |
| `nodes/desk_stages/` | Stage groups built from the nodes: `understand`, `bom`, `components`, `schematic`, `layout`, `verification`, `release`, and the shared human `approve` |
| `workflows/requirement_to_profile/` | Requirements to an approved engineering profile; every stage is backed by a DESK engine |
| `workflows/hardware_design/` | Requirements to manufacturing release; stages without an engine adapter fail closed |
| `validator/` | Source of the compiler harness (`python desk.py weft build-validator`) |

Weft is Copyright (c) 2026 WeaveMind, Inc., under the O'Saasy License Agreement. No Weft code is in this folder;
the programs here are DESK's. See [`docs/weft/03_LICENCE.md`](../../docs/weft/03_LICENCE.md).
