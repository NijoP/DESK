# 02 — Schematic style (NON-NEGOTIABLE)

Neatness is not optional and is not left to the model. It is fixed in code: `desk/draw.py` (`STYLE`, `BLOCK_JS`,
`SUBSYSTEM_STYLE`, `PLACE_JS`) and `desk/schematic_router.py` (the in-block wire router and its checker).
**A model must never write its own drawing JavaScript.** If a sheet looks wrong, fix the *spec* (order, block split,
ports) or, for a global change, edit the style tables once — never hand-place parts in a one-off script.

> Status: the `subsystem` style is **software-tested with fixtures; not validated on a live design.** The EasyEDA calls
> it needs beyond the `labels` style are marked UNVERIFIED-LIVE (see [UNVERIFIED-LIVE](#unverified-live)).

## Wiring policy: `subsystem` (default for new projects) or `labels` (legacy)

| Policy | What is drawn | Who gets it |
|---|---|---|
| `subsystem` | Physically wired subsystems: real orthogonal wires between the parts of a block; labels / power-style labels for rails, ground and interfaces, **supplementing** the wires | every project made by `tools/new_project.py` (`templates/project/project.json` has `"wiring": "subsystem"`) |
| `labels` | Every connected pin = short stub + net label (rules S4–S6); no wires between parts | every existing project without a `wiring` key — **never rewritten silently** |

Precedence for one block: block spec `"wiring"` (a client requirement for that block) > `project.json` `"wiring"` >
`labels`. An unknown value is a lint error. A block spec may also list `"label_nets": [...]` — nets the client wants
drawn as labels only.

**Netlist equality (`tools/verify.py`) is the acceptance test in both styles.** A block *built* with `subsystem`
must also have its saved plan (`state/wiring/<BLOCK_ID>.json`) pass the geometric check (zero crossings, zero shorts,
junctions only at shared end points, no dangling wires, no overlaps, netlist equal to the current spec).

## What a `subsystem` block looks like

```
+-- 3V3 REGULATOR --------------------------------------------+
|                                                              |
|  VIN_5V--+------+--+3V3                                      |
|  GND-----|  U3  |----------------+                           |
|  EN---+--+------+                |  FB                       |
|       |                         |                           |
|       +--[R9]--*--[C4]--GND     +---[R15]---*---[R16]--GND   |
|                |                            |               |
|               (EN_RC wired)          +3V3--+ (label: rail)  |
+--------------------------------------------------------------+
   * = junction dot
```

### Net classes (from the spec alone: `desk.spec.classify_nets`)

| Class | Rule | Drawn as |
|---|---|---|
| `power` | name matches the rail / ground pattern (`GND`, `+3V3`, `VBAT…`, `VIN…`, `…_GND`) or is in `project.json` `"rails"` | stub + label on every pin (power-symbol style; ground in `ground_color`) |
| `port` | listed in the block's `ports` | wires between its in-block pins **plus one** interface label (the label marks the cross-subsystem connection) |
| `cross` | used by another block but not declared a port | as `port` |
| `local` | ≥ 2 pins, only in this block | wires only |
| `single` | one pin, not a port | stub + label (lint already flags it) |

### Router guarantees (`desk/schematic_router.py`)

- Orthogonal wires on the 10-unit grid, inside the block's column (never left of the block origin, never into the
  title band); A* with a bend penalty, shortest nets first; each pin leaves in its outward direction.
- A wire never enters a symbol body, never touches a pin tip except its own end, never enters a cell of another net
  (wire, stub, label text, reserved escape) — **different nets never cross, touch or overlap.**
- A branch that joins a wire mid-way splits it: every junction is a shared end point, and every point where three or
  more same-net wire ends meet gets a **junction dot**. A crossing is never a connection (there are none).
- A net that cannot be routed (pin off the grid, no free path) **falls back to labels** for that net — still
  netlist-correct — and is reported by `tools/build.py` and in the plan's `fallback`.
- Deterministic: the same spec and pin read-back give the same plan byte-for-byte.
- Placement is the same code as the `labels` style (`PLACE_JS` is derived from `BLOCK_JS` by exact substitution),
  except that the part origins, the block origin and the passive row pitch (125 → 130) are snapped to the 10-unit
  grid so every pin can be wired.
- Measured on the synthetic fixtures (laptop, Python 3.12): 41 ms and 230 ms per block for plan + route.

### How `tools/build.py` draws it

1. `PLACE_JS` places the parts and sets the NC flags; it returns every pin tip (x, y, rotation).
2. `desk.draw.plan_subsystem` classifies the nets and routes them offline; `check_plan` must pass, else the build
   stops before any wire is drawn (parts placed, operation left dirty → `tools/clear_block.py`).
3. `desk.schematic_io.subsystem_draw_js` draws wires, labels, junction dots, frame and title. Connectivity calls are
   never wrapped; appearance calls (colours, dots) are each in their own try/catch and only counted when refused.

### Checker (`desk.schematic_router.check_plan`)

Errors on: wires of different nets that cross or touch; overlapping same-net wires; a T-join or crossing in the middle
of a wire; a wire over a pin; a dangling wire end; a floating label; a label on another net's wire; a missing or extra
junction dot; a symbol overlapping a symbol; a wire under a symbol or a label; label text over a symbol or over other
label text; an open (net drawn in pieces) or a short (nets merged); a drawn netlist that differs from the spec. Symbol
outlines and label text extents are models (pin tips + pin lines; `len(net) × 5.5` along the stub), not readbacks.

## Appearance (`desk.draw.SUBSYSTEM_STYLE`)

The owner's style spec, section 1, as data — extend by adding a key **and** a row in `SUBSYSTEM_STYLE_APPLIED`:

| Key | Value | Reaches the sheet by |
|---|---|---|
| `background` | `#FFFFFF` (white) | not applied: EasyEDA's background is an editor theme setting (white by default) |
| `frame_color`, `frame_line_width` | `#1F3A68`, 1 — thin rectangular subsystem boundary | drawn (the frame call `BLOCK_JS` uses) |
| `title_color`, `title_size`, `title_bold` | `#1F3A68`, 12, bold — prominent title, top-left | drawn |
| `reference_color` | `#1F3A68` (dark blue designators) | not applied: no known API sets a designator colour |
| `label_color`, `label_size` | `#1F4FBF` (blue), 5 | colour UNVERIFIED-LIVE; size drawn |
| `ground_color` | `#000000` (black ground) | UNVERIFIED-LIVE |
| `wire_color` | `#008000` (green) | UNVERIFIED-LIVE |
| `junction_dots`, `junction_color`, `junction_radius` | on, `#008000`, 3 | UNVERIFIED-LIVE |

`desk.draw.plan_svg(plan)` renders a plan as a deterministic SVG in this style (symbols are the checker's outline
model, not library symbols) for offline review and the visual-regression snapshots in
`tests/fixtures/schematic_wiring/`.

## Multi-sheet projects (data / spec level)

```json
"sheets": [
  {"id": "POWER", "title": "POWER SUBSYSTEM", "uuid": "<page uuid>", "blocks": ["01_PWR_IN", "02_PWR_3V3"]},
  {"id": "MCU",   "title": "MCU SUBSYSTEM",   "uuid": "<page uuid>", "blocks": ["03_MCU"]}
]
```

- Lint: every block on exactly one sheet, sheet blocks exist, and every non-power net that crosses sheets
  (`desk.spec.cross_sheet_ports`) is in the `ports` of each block that uses it — so it is labelled on both sheets.
- `tools/build.py` draws a block on its sheet's `uuid`; `tools/verify.py` reads the sheet of the selected blocks
  (blocks on different sheets: verify one sheet at a time).
- DESK does **not** create pages (`eda.dmt_Schematic.createSchematicPage` is UNVERIFIED-LIVE): create the page in
  EasyEDA and paste its uuid. Hierarchical sheet symbols are not drawn; cross-sheet links are net labels.
- `tools/clear_block.py` still guards `project.json` `sheet_uuid` (multi-sheet clear is not done yet).

## Migrating an existing project (explicit, previewed, backed up)

```bash
python tools/migrate_wiring.py projects/<P>                 # preview only: what gets wired, which drawn blocks need a rebuild
python tools/migrate_wiring.py projects/<P> --apply <TOKEN> # backup project.json to state/backups/, set "wiring": "subsystem"
```

The token ties the apply to the reviewed preview; any change to `project.json`, a block spec or the layout voids it.
The tool never touches the live sheet and never rebuilds a block: drawn blocks keep their labels drawing (verify keeps
accepting them and notes them) until you run `tools/clear_block.py` + `tools/build.py` for each one yourself.

## The rules (each one prevents a real failure)

| # | Rule | Why |
|---|---|---|
| S1 | **One framed, titled rectangle per subsystem block.** Title = UPPER-CASE function name, top-left, bold, frame colour. | The sheet reads like a block diagram; reviewers find things instantly. |
| S2 | **ICs / connectors in one row at the top of the block, in signal-flow order** (spec order, left → right: input → processing → output). | Consistent reading direction. |
| S3 | **Passives in a grid below the ICs**, in spec order, grouped by the IC/pin they serve (all U3 caps together, then U3 divider ...). | Reviewer sees "what belongs to what" by position. |
| S4 | **`labels` style: every connected pin = short real wire stub + net label at its end.** In the `subsystem` style this holds for rails, ground and single pins; local and interface nets are wired (S11). Never a floating label, never long wires across the sheet. | Real copper, no hidden opens; no spaghetti. |
| S5 | **Stub length alternates short/long (110/170) between neighbouring pins.** | Adjacent labels never touch → no accidental net merge. |
| S6 | **Labels rotated with the stub** (vertical for top/bottom pins), small fixed font (5). | Compact, uniform. |
| S7 | **Unused pins get an explicit No-Connect flag** (spec `nc`). | ERC-clean, and proves the pin was *decided*. |
| S8 | **All coordinates on the grid; blocks never overlap**; blocks flow left → right in rows, `block_gap` apart. | Clean alignment; reproducible layout. |
| S9 | **Real library device for every part** (resolved MPN/LCSC), designator set from the spec. | BOM/footprint correct from day one. |
| S10 | **No decoration that carries meaning** (no hand-drawn arrows, no notes that replace a connection). Notes go in the spec `decisions`. | The netlist is complete on its own. |
| S11 | **`subsystem` style: parts of a block are physically wired; labels supplement wires** (rails, ground, one label per interface net). Zero crossings, junction dots at every T, no dangling wire, nothing hidden under a symbol or a label. | Another engineer can follow the circuit without reconstructing it from scattered labels. |

## How to make a block look good (spec-level levers)

- **Order `parts`**: ICs first in signal-flow order, then passives grouped by the pin they serve.
- **Split big blocks**: if the IC row would exceed the sheet width or the block exceeds ~25 parts, split it.
- **Name ports clearly**: in the `labels` style the labels are the only "wires" between blocks; in the `subsystem`
  style they are the interface between subsystems.
- **Multi-unit / huge parts** (MCU modules, big connectors) get their own block (`MCU CORE`, `CONNECTORS`).
- **Block order on the sheet** = `block_order` in `project.json` = power → MCU → interfaces → indicators.
  Build in that order so the rows come out in that order.

## Global look changes

Edit `STYLE` (the `labels` style) or `SUBSYSTEM_STYLE` in `desk/draw.py`. It applies to every future block of every
product. Do it in a dedicated commit, never per block. `STYLE` is frozen by a byte-identical snapshot test of the
`labels` output; changing it is a deliberate, reviewed change of that snapshot.

## UNVERIFIED-LIVE

`desk.schematic_io.UNVERIFIED_LIVE` lists every EasyEDA call the `subsystem` style or multi-sheet projects need that is
not VERIFIED in `desk/reliability/api_registry.py`; all of them live in that one adapter:

- `wire_network` — `eda.sch_PrimitiveWire.create([x1,y1,x2,y2], net)` once per segment of a branching net: that
  segments meeting at shared end points (including T-junctions) form one net named `net` is not yet observed live.
- `wire_style` — colouring wires and labels via `modify(id, {color})`, junction dots via
  `eda.sch_PrimitiveCircle.create(...)`: no signature in the API reference; isolated, appearance only.
- `create_sheet` — `eda.dmt_Schematic.createSchematicPage`: never exercised; `create_sheet_js` refuses.

A live probe on a disposable project must confirm each entry before it is trusted. Until then the `subsystem` style is
software-tested with fixtures only and must not be reported as validated on a live design.
