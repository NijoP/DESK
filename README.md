# DESK — a design desk for neat, netlist-proven EasyEDA Pro schematics

DESK is a workflow + toolkit for capturing hardware products in **EasyEDA Pro**, made so **any AI model
(including small, cheap ones)** or a human produces the same **neat, block-structured, verified** schematics.

**Core idea:** the design lives in small JSON **block specs** (one per subsystem: ICs + all their passives + pin→net map + datasheet QA).
DESK draws each block in one fixed style through the EasyEDA API, then reads back the live netlist and **proves** that the sheet matches the spec.

```
client brief → REQUIREMENTS.md (gate R) → BOM_SELECTION.md (gate B) → BLOCK_PLAN.md → blocks/NN_ID.json → lint → build (draw) → verify (netlist) → accept → next block
                                                                        ↓ all blocks accepted
                                                         placement.json → pcb_place → pcb_check → routing plan → DRC
```

## What you get on the sheet
Every subsystem is a **framed, titled block**: ICs in one row (signal-flow order), passives in a grid underneath,
every pin with a short real wire stub + net label (alternating lengths so labels never collide), NC flags on unused pins,
all on the 100-mil grid. Blocks flow left→right in rows. See [docs/02_SCHEMATIC_STYLE.md](docs/02_SCHEMATIC_STYLE.md).

## Repository map
| Path | What |
|---|---|
| [AGENTS.md](AGENTS.md) / CLAUDE.md | **Rules for any AI model.** Point your model at this file first. |
| [docs/00_REQUIREMENTS.md](docs/00_REQUIREMENTS.md) | **Understand the client**: 10 requirement dimensions (function, electrical, interfaces, mechanical, environment, regulatory, manufacturing, cost, lifecycle), interview method, derivations |
| [docs/00b_COMPONENT_SELECTION.md](docs/00b_COMPONENT_SELECTION.md) | **Select the BOM incl. passives**: selection order, filter funnel F1–F7, category traps, resistor/capacitor/inductor rules, preferred passive set |
| [docs/01_MENTAL_MODEL.md](docs/01_MENTAL_MODEL.md) | How to think: data first, QA before drawing, one block at a time, netlist is truth |
| [docs/02_SCHEMATIC_STYLE.md](docs/02_SCHEMATIC_STYLE.md) | The non-negotiable visual rules |
| [docs/03_BLOCK_WORKFLOW.md](docs/03_BLOCK_WORKFLOW.md) | The 7 gates per block, QA checklists |
| [docs/04_PLACEMENT.md](docs/04_PLACEMENT.md) | PCB placement mental model |
| [docs/05_ROUTING.md](docs/05_ROUTING.md) | Stackup, net classes, routing order, grounding |
| [docs/06_EASYEDA_API.md](docs/06_EASYEDA_API.md) | Connecting EasyEDA, API calls used, gotchas |
| [docs/08_LEARNING_ENGINE.md](docs/08_LEARNING_ENGINE.md) | **Learning Engine**: learns from Claude/Codex/OpenCode/Pi sessions (via Backpass adapters) + DESK logs; human-gated proposals |
| [docs/09_STATUS.md](docs/09_STATUS.md) | **Capability status** with acceptance criteria and evidence (what is live-verified, what is not) |
| [docs/07_CONTEXT_ENGINE.md](docs/07_CONTEXT_ENGINE.md) | **Context Engine**: task-aware, token-budgeted context packs + project ledger (decisions, facts, verifications) |
| `desk/` | `bridge.py` (connection), `draw.py` (**the style, as code**), `spec.py` (lint rules), `context.py` (context engine), `ledger.py` (project memory) |
| `tests/` | offline tests: `python -m unittest discover -s tests -v` |
| `tools/` | command-line tools (below) |
| `library/` | shared across products: `devices.json` (resolved parts), `pins/` (real pin maps) |
| `templates/` | project skeleton, block spec, placement, requirements, block plan, result |
| `examples/demo_node/` | tiny example product (3V3 LDO + status LED) |
| `projects/` | your products live here (`tools/new_project.py NAME`) |

## 1. Connect EasyEDA Pro (once per machine)
1. Install **Python 3.9+** and **Node.js 18+**.
2. In EasyEDA Pro install the extension **Run API Gateway** (`run-api-gateway.eext`) from
   https://jlc-ext.com/item/oshwhub/run-api-gateway → *Extensions → Extension Manager → Import*, enable it.
3. Get the bridge server (`bridge-server.mjs`, e.g. from the open `easyeda-api` agent skill; run `npm install` in its folder).

## 2. Every session — connect the port
```bash
node path/to/bridge-server.mjs &                 # starts on the first free port 49620-49629
curl http://localhost:49620/health               # {"service":"easyeda-bridge",...}
curl http://localhost:49620/eda-windows          # count >= 1 once EasyEDA Pro is open with the extension
python tools/ping.py                             # shows the open project + ACTIVE document uuid
```
- DESK finds the port automatically (scans 49620–49629). To force: `set EDA_PORT=49621` (Windows) / `export EDA_PORT=49621`.
- Several EasyEDA windows: `curl -X POST http://localhost:49620/eda-windows/select -H "Content-Type: application/json" -d "{\"windowId\":\"<id>\"}"`
- Problems → [docs/06_EASYEDA_API.md#troubleshooting](docs/06_EASYEDA_API.md#troubleshooting)

## 3. Start a product
```bash
python tools/new_project.py MY_PRODUCT
```
1. **Understand the client** → fill `projects/MY_PRODUCT/REQUIREMENTS.md` with all 10 dimensions, power budget,
   voltage tree, mechanical envelope, interface table; get client confirmation (gate R, [docs/00](docs/00_REQUIREMENTS.md)).
2. **Select the parts** → `BOM_SELECTION.md`: comparison matrix per key part, preferred passive set (gate B, [docs/00b](docs/00b_COMPONENT_SELECTION.md)).
3. Fill `BLOCK_PLAN.md` (list of blocks, order, ports, global net names).
4. In EasyEDA: create the project + a schematic page, open it, run `python tools/ping.py`,
   paste the document uuid into `project.json` → `sheet_uuid` (later the PCB uuid into `pcb_uuid`).

## 4. One block, start to finish
```bash
# write projects/MY_PRODUCT/blocks/02_PWR_3V3.json  (template: templates/block.template.json)
python tools/resolve.py projects/MY_PRODUCT              # MPN -> real EasyEDA device (asks when ambiguous)
python tools/pins.py    projects/MY_PRODUCT              # real pin numbers/names -> rewrite the pin map from them
python tools/lint.py    projects/MY_PRODUCT 02_PWR_3V3   # offline gate: must print PASS
python tools/build.py   projects/MY_PRODUCT 02_PWR_3V3   # draws the framed block on the open sheet
python tools/verify.py  projects/MY_PRODUCT 02_PWR_3V3   # live netlist == spec: must print VERIFIED
```
Wrong? `python tools/clear_block.py projects/MY_PRODUCT 02_PWR_3V3`, fix the **spec**, build again.
Accepted → save an EasyEDA revision, `git commit`, next block.

BOM at any time: `python tools/bom.py projects/MY_PRODUCT` → `bom.csv` + warnings (missing ratings, under-rated caps, odd values, too many package sizes).

Whole sheet at the end: `python tools/verify.py projects/MY_PRODUCT all` and `python tools/lint.py projects/MY_PRODUCT --final`.

## 5. PCB
```bash
python tools/pcb_dump.py  projects/MY_PRODUCT            # read footprints/pads after "Update PCB from schematic"
# write projects/MY_PRODUCT/placement.json  (template: templates/placement.template.json, every line has a reason)
python tools/pcb_place.py projects/MY_PRODUCT --dry      # review targets
python tools/pcb_place.py projects/MY_PRODUCT
python tools/pcb_dump.py  projects/MY_PRODUCT && python tools/pcb_check.py projects/MY_PRODUCT
```
Then routing by [docs/05_ROUTING.md](docs/05_ROUTING.md), EasyEDA DRC to 0 errors.

## Using DESK with a lightweight model
Start every session with the **Context Engine** instead of letting the model read files:
```bash
python tools/ctx.py projects/MY_PRODUCT brief              # ~300 tokens: state, next action, rules, decisions
python tools/ctx.py projects/MY_PRODUCT block 02_PWR_3V3   # ~800 tokens: live lint, spec, neighbours, requirements, pins, how-to
python tools/ctx.py projects/MY_PRODUCT delta              # follow-up: only changes
python tools/ledger.py projects/MY_PRODUCT add decision "..." --source "datasheet p.12"
```
Measured on the example: ~10 % of the tokens of reading the docs and specs, with the next step computed from real state.

Tell the model: *"Read AGENTS.md, then run `python tools/ctx.py projects/X block NN_ID`. Work on that block only. Stop at each gate failure."*
The model only writes JSON and runs tools; the style is in code and correctness is proven by the netlist,
so model size affects speed of spec writing, not sheet quality. Keep tasks one block per session to save tokens.

## Learning from sessions
```bash
python tools/learn.py setup && python tools/learn.py run    # read-only analysis of real agent sessions
python tools/learn.py show <ID>; python tools/learn.py accept <ID> --reviewer NAME
```
See [docs/08_LEARNING_ENGINE.md](docs/08_LEARNING_ENGINE.md).

## License
[MIT](LICENSE). Third-party notices: [NOTICE](NOTICE).
