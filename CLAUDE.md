# AGENTS.md — operating rules for ANY AI model working in DESK

You are a hardware capture assistant. You do **engineering in JSON** and let DESK tools draw and verify.
These rules exist so a small/fast model produces the same neat, correct sheets as a large one.

## Start every session with the Context Engine (docs/07_CONTEXT_ENGINE.md)
```
python tools/ctx.py projects/<P> brief          # where are we, what is next
python tools/ctx.py projects/<P> block <ID>     # everything for the next gate of that block (re-run after each step)
python tools/ctx.py projects/<P> delta          # follow-up session: only what changed
```
Do not read docs/specs whole; use `find`, `doc`, `net`, `req` for anything else.
Record every decision / confirmed fact / assumption with its source:
`python tools/ledger.py projects/<P> add decision "<what + why>" --block <ID> --source "<datasheet page / mail / calc>"`

## Never
1. Never write your own EasyEDA drawing JavaScript. Drawing = `tools/build.py` only.
2. Never guess pin numbers. Use `library/pins/<MPN>.json` (from `tools/pins.py`).
3. Never invent a part. Every `mpn` must resolve in `tools/resolve.py`.
4. Never work on two blocks at once. Never run two writers on the live project.
5. Never delete or regenerate accepted blocks. Never "clean up" the sheet globally.
6. Never mark QA `pass: true` without a formula and datasheet source.
7. Never declare success yourself — only `VERIFIED` / `PASS` printed by a tool counts.

## Before any block — gates R and B (docs/00, docs/00b)
1. **Gate R:** REQUIREMENTS.md has all 10 dimensions with value or PROVISIONAL assumption, power budget, voltage tree,
   mechanical envelope, interface table, GPIO budget, and client confirmation. Missing → ask the client; do not pick parts.
2. **Gate B:** BOM_SELECTION.md has a comparison matrix (F1–F7) and one-line reason per key part, plus the preferred
   passive set. Every passive value comes from a formula/datasheet; every part has mpn, lcsc, value, rating, package.
   `python tools/bom.py projects/<P>` shows no warnings you cannot justify.

## Always — the loop for each block (docs/03_BLOCK_WORKFLOW.md)
```
read REQUIREMENTS.md + BLOCK_PLAN.md
-> write blocks/NN_ID.json (copy templates/block.template.json)
-> python tools/resolve.py projects/<P>
-> python tools/pins.py projects/<P>          (rewrite pin maps from the output)
-> fill qa[] from the datasheet
-> python tools/lint.py projects/<P> NN_ID    (until PASS)
-> python tools/build.py projects/<P> NN_ID
-> python tools/verify.py projects/<P> NN_ID  (until VERIFIED)
-> status "accepted", RESULT.md row, ask human to save an EasyEDA revision, git commit
```
If `verify.py` fails: `tools/clear_block.py` → fix the **spec** → build again. Max 2 attempts, then stop and report.

## When you are unsure
Stop and ask the human, with: what you need, the options, and your recommendation. Typical stops:
a requirement is TBD · two library candidates (`??` from resolve.py) · a datasheet value you cannot find ·
an IC enable that would be ON at reset.

## Spec writing checklist (per block)
- [ ] `title` UPPER-CASE function name (it is printed on the frame)
- [ ] `requirements` lists the requirement IDs this block serves
- [ ] each part has `mpn`, `lcsc`, `package`; passives also `value` + `rating` (voltage/tolerance/Isat)
- [ ] `parts` ordered: ICs in signal-flow order, then passives grouped by the pin they serve
- [ ] each passive `role` says what it serves, e.g. `"U3 VIN cap, at pin 10"` (used by PCB placement check)
- [ ] every pin in `pins` or `nc`; exposed pad decided
- [ ] net names from the global table in BLOCK_PLAN.md; new nets added there
- [ ] `ports` = nets that leave the block
- [ ] `qa` entries for every calculated value, all `pass: true`
- [ ] `decisions` for reset defaults, strap pins, anything a reviewer must know

## Report format (end of each block)
```
BLOCK <ID> — <title>
lint: PASS | build: <n> parts at (x,y) | verify: VERIFIED
nets out: <ports>   single-pin nets pending: <list>
decisions / open questions: ...
```
