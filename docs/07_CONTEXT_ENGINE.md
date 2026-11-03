# 07 — Context Engine

**Goal:** a model gets exactly the context its current task needs — correct, current, sourced — in a few hundred
tokens instead of reading the repo. Code: `desk/context.py`, `desk/ledger.py`. CLI: `tools/ctx.py`, `tools/ledger.py`.

## Session protocol (every model, every session)
```bash
python tools/ctx.py projects/<P> brief             # ~300 tokens: state of every block, next action, rules, recent decisions
python tools/ctx.py projects/<P> block <ID>        # ~800 tokens: everything to do the next gate of that block
# ... work ... (run the gate tool the pack tells you)
python tools/ctx.py projects/<P> block <ID>        # re-pack: live lint + new gate after each step
python tools/ctx.py projects/<P> delta             # in a follow-up session: only what changed since your last pack
```
Do **not** open docs or block JSON files whole unless a pack says something is truncated and you need it.

## Commands
| Command | Returns | Default budget |
|---|---|---|
| `brief` | gate R/B status, block table with **derived** next gate, lint error count, verify state, next action, AGENTS "Never" rules, last decisions | 1500 |
| `block <ID>` | task + exact command, **live lint**, compact spec (all pins), ports → pins in other blocks, requirement rows served, matching BOM-study section, block ledger, real symbol pins (before build), how-to for the next gate, passive rules at G4 | 3000 |
| `net <NAME>` | every pin on the net per block, where it is a port, single-pin warning; suggests similar names | 1200 |
| `req <R-ID>` | requirement row, blocks serving it (or "not covered"), project docs mentioning it | 1500 |
| `find "<text>"` | BM25-ranked docs sections, requirement rows, blocks, ledger entries with source anchors | 1500 |
| `doc "<heading>"` | one doc section by heading (`G4`, `Passive selection`, `Troubleshooting`) | 2500 |
| `delta` | NEW / CHANGED / REMOVED chunks since the last `brief`/`delta` | 2000 |
| `index` | refresh index, print reuse stats | — |
Options: `--budget N` (tokens), `--full` (block pack without budget).

## How it decides what is relevant
- **Structure, not similarity.** Relations are exact: block → `requirements` IDs → requirement rows;
  block `ports` → same net in other blocks; block MPNs → `library/pins`; block → ledger entries; MPN/requirement → BOM study section.
  BM25 is used only for free-text `find`.
- **Next gate is computed from real state** in this order: unresolved MPN (G2) → missing pin cache (G3) → QA missing/failed (G4)
  → other lint errors (G5) → not built (G6, from `state/layout.json` or ledger) → verification missing or STALE (G7)
  → status not accepted (ACCEPT) → DONE. The `status` field cannot fake progress.
- **Priority packing.** Each section has a priority; the pack fills the budget in priority order, truncates the first
  must-have section if needed, and lists what it left out — so the model knows to ask for more.

## Preserving decisions and verified facts — the ledger
`projects/<P>/LEDGER.jsonl` (committed, append-only). Each entry has id, time, type, text, block, **source**.
```bash
python tools/ledger.py projects/<P> add decision "TPS62840 over AP2112: Iq 60 nA vs 55 uA (battery life R-03)" --block 02_PWR_3V3 --source "BOM_SELECTION.md 3V3 regulator; datasheets p.1"
python tools/ledger.py projects/<P> add fact "client confirmed max height 3 mm top" --source "mail 2026-01-04"
python tools/ledger.py projects/<P> add correction "EN is active-high on -1 variant" --refs L-0007 --source "ds p.3"
python tools/ledger.py projects/<P> list --block 02_PWR_3V3
```
- `decision`, `fact`, `assumption` **require `--source`**. Entries are never edited; `correction` supersedes (`refs`).
- `tools/build.py` writes `built`, `tools/verify.py` writes `verified` — both carry the block **spec hash**
  (status excluded). Any electrical change to the spec makes the verification **STALE** in every pack until re-verified.

## Incremental behaviour
- Index cache `projects/<P>/state/ctx_index.json`: chunks per source file keyed by content hash; only changed files are re-parsed.
  `FORMAT` in `desk/context.py` invalidates caches when the chunk format changes.
- `state/ctx_served.json`: hashes of what was last served; `delta` prints only differences. `brief` resets the baseline.
- `state/` is local (git-ignored). The ledger is the durable, shared memory.

## Measured (examples/demo_node)
Reading AGENTS + README + docs + specs ≈ 11.5k tokens. `brief` ≈ 300, `block` ≈ 800, unchanged `delta` ≈ 25 → **~10 % of the
read-everything cost**, and block packs stay constant-size as the product grows (an MCU block only adds its own pins).

## Extending
- New project file to index → add it to `PROJECT_MD` in `desk/context.py` (markdown is split by `##`/`###` headings).
- New task pack → add a method on `Engine` that builds a `Pack`, then a command in `tools/ctx.py`, and a test in `tests/test_context.py`.
- Run tests: `python -m unittest discover -s tests -v` (offline, no EasyEDA).
