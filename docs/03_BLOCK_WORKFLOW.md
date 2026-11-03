# 03 — Block workflow (one section complete, then the next)

Prerequisite for every block: **gate R** (requirements, [00](00_REQUIREMENTS.md)) and **gate B** (component selection, [00b](00b_COMPONENT_SELECTION.md)) are passed.

Each block passes **seven gates**. `python tools/ctx.py projects/<P> block <ID>` tells you which gate is next and packs what it needs. A gate is passed only by tool output, never by opinion.
Only one block is "in progress" at any time.

```
G1 PLAN ─► G2 PARTS ─► G3 PINS ─► G4 QA ─► G5 LINT ─► G6 BUILD ─► G7 VERIFY ─► ACCEPT (save revision, commit)
```

## G1 — Plan the block
- Add a row in `BLOCK_PLAN.md`: ID, title, main ICs, ports, dependencies.
- All requirements it needs are **CONFIRMED** in `REQUIREMENTS.md`. If not → stop, ask, pick another block.
- Copy `templates/block.template.json` → `blocks/NN_ID.json`, fill `id`, `title`, `purpose`, `ports`.

## G2 — Choose real parts
- From the datasheet's typical application circuit: list the IC + **every** external component it needs.
- Parts come from `BOM_SELECTION.md` (key ICs) and the preferred passive set; values from formulas (docs/00b).
- Each part gets `mpn`, `lcsc`, `package`; passives also `value` + `rating`. Check with `python tools/bom.py projects/<P>`.
- `python tools/resolve.py projects/<P>` → every MPN is in `library/devices.json` (ask the human when it prints `??`).

## G3 — Real pin map
- `python tools/pins.py projects/<P>` → `library/pins/<MPN>.json`.
- Write each part's `pins` {pin number: NET} **from that file** (numbers are what EasyEDA uses; names may repeat).
- Every pin is either in `pins` or in `nc`. Exposed pad / thermal pad → `GND` (unless datasheet says otherwise).

## G4 — Engineering QA (before drawing)
For each calculated value add a `qa` entry: `item, formula, result, limit, source (datasheet page), pass`.
Minimum checklist per block type:

| Block | Must check |
|---|---|
| Regulator | Vout from divider formula, inductor value & Isat, Cin/Cout value & voltage derating, EN level & default, PG pull-up |
| Charger | charge current resistor, input current limit, timer, TS/NTC handling, status pin pull-ups |
| Load switch / current limit | ILIM resistor → current range, EN active level, default OFF at reset |
| MCU | decoupling per datasheet, EN/RC reset, boot/strap pins level, USB/UART, antenna keep-out note |
| Interface/connector | pinout vs mating part, ESD on every pin, series R, pull-ups value vs bus speed/capacitance |
| LEDs | current per LED vs GPIO limit, colour Vf |

## G5 — Lint (offline)
`python tools/lint.py projects/<P> <BLOCK_ID>` must print **PASS**. It catches: duplicate designators, pins that
don't exist, undecided pins, nets touching one pin that are not ports, bad net names, failed/missing QA.

## G6 — Build
1. Open the product's schematic page in EasyEDA (the one in `project.json` `sheet_uuid`).
2. `python tools/build.py projects/<P> <BLOCK_ID>` — draws the block in the DESK style at the next layout slot.
3. If wrong: `python tools/clear_block.py projects/<P> <BLOCK_ID>`, fix the **spec**, rebuild. Never hand-patch.

## G7 — Verify
`python tools/verify.py projects/<P> <BLOCK_ID>` must print **VERIFIED**:
every pin on its spec net, NC flags present, **no unexpected nets** (= no label collisions).
Single-pin nets are allowed only for ports whose other side is in a block not yet built.
Then a human glances at the sheet for neatness (screenshots from the API can be stale — trust your screen).

## ACCEPT
- Set block `status` to `accepted`, add a row to `RESULT.md`; record any decision made on the way with `tools/ledger.py ... --source`.
- In EasyEDA: save + create a project revision/backup.
- `git commit -m "<P>: <BLOCK_ID> accepted (verify clean)"`.
- Next block.

## Sheet-level finish (after the last block)
- `python tools/verify.py projects/<P> all` → VERIFIED, single-pin nets: none (or each one justified in RESULT.md).
- `python tools/lint.py projects/<P> --final` → PASS.
- EasyEDA ERC → 0 errors. Export netlist/BOM to `projects/<P>/exports/`.
