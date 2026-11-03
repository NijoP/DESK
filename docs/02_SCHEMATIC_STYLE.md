# 02 — Schematic style (NON-NEGOTIABLE)

Neatness is not optional and is not left to the model. It is fixed in `desk/draw.py` (`STYLE` dict + `BLOCK_JS`).
**A model must never write its own drawing JavaScript.** If a sheet looks wrong, fix the *spec* (order, block split)
or, for a global change, edit `STYLE` once — never hand-place parts in a one-off script.

## What every sheet looks like

```
+-- 3V3 REGULATOR -----------------------+  +-- MCU CORE --------------------------------+
|                                        |  |                                            |
|  VSYS--+----+--+3V3                    |  |  +3V3-+------------+--IO1                  |
|  PWR_EN-| U3 |--FB_3V3                 |  |  GND--|    U1      |--IO2   ...             |
|  GND---+----+--L_SW                    |  |       +------------+                       |
|                                        |  |                                            |
|  VSYS-[C9]-GND    +3V3-[C10]-GND       |  |  +3V3-[C1]-GND  +3V3-[C2]-GND  EN-[R1]-+3V3 |
|  +3V3-[R15]-FB_3V3  FB_3V3-[R16]-GND   |  |  EN-[C4]-GND    IO0-[SW1]-GND              |
+----------------------------------------+  +--------------------------------------------+
```

## The rules (each one prevents a real failure)

| # | Rule | Why |
|---|---|---|
| S1 | **One framed, titled rectangle per subsystem block.** Title = UPPER-CASE function name, top-left, bold, frame colour. | The sheet reads like a block diagram; reviewers find things instantly. |
| S2 | **ICs / connectors in one row at the top of the block, in signal-flow order** (spec order, left → right: input → processing → output). | Consistent reading direction. |
| S3 | **Passives in a grid below the ICs**, in spec order, grouped by the IC/pin they serve (all U3 caps together, then U3 divider ...). | Reviewer sees "what belongs to what" by position. |
| S4 | **Every connected pin = short real wire stub + net label at its end.** Never a floating label, never long wires across the sheet. | Real copper, no hidden opens; no spaghetti. |
| S5 | **Stub length alternates short/long (110/170) between neighbouring pins.** | Adjacent labels never touch → no accidental net merge. |
| S6 | **Labels rotated with the stub** (vertical for top/bottom pins), small fixed font (5). | Compact, uniform. |
| S7 | **Unused pins get an explicit No-Connect flag** (spec `nc`). | ERC-clean, and proves the pin was *decided*. |
| S8 | **All coordinates on the 100-mil grid; blocks never overlap**; blocks flow left → right in rows, `block_gap` apart. | Clean alignment; reproducible layout. |
| S9 | **Real library device for every part** (resolved MPN/LCSC), designator set from the spec. | BOM/footprint correct from day one. |
| S10 | **No decoration that carries meaning** (no hand-drawn arrows, no notes that replace a connection). Notes go in the spec `decisions`. | The netlist is complete on its own. |

## How to make a block look good (spec-level levers)

- **Order `parts`**: ICs first in signal-flow order, then passives grouped by the pin they serve.
- **Split big blocks**: if the IC row would exceed the sheet width or the block exceeds ~25 parts, split it.
- **Name ports clearly**: the labels are the only "wires" between blocks, so their names are the readability.
- **Multi-unit / huge parts** (MCU modules, big connectors) get their own block (`MCU CORE`, `CONNECTORS`).
- **Block order on the sheet** = `block_order` in `project.json` = power → MCU → interfaces → indicators.
  Build in that order so the rows come out in that order.

## Global look changes

Edit `STYLE` in `desk/draw.py` (colour, fonts, stub lengths, pitches). It applies to every future block of every product.
Do it in a dedicated commit, never per block.
