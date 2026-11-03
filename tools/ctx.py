"""Context Engine CLI — start EVERY model session here instead of reading files.
Usage: python tools/ctx.py <project> <command> [args] [--budget N] [--full]
  brief                 project state, block table with derived next gate, next action, rules, recent decisions
  block <ID>            everything for working on one block: task, live lint, compact spec, ports->neighbours,
                        requirements, BOM study, ledger, real pins, how-to for the next gate
  net <NAME>            every pin on a net across blocks
  req <R-ID>            a requirement, the blocks serving it, where it is discussed
  find "<text>"         ranked search over docs, requirements, blocks, ledger (BM25)
  doc "<heading>"       one doc section by heading (e.g. "G4", "Passive selection", "Troubleshooting")
  delta                 only what changed since the previous delta/brief (incremental follow-up sessions)
  index                 rebuild/refresh the index and print stats
Default budgets (tokens): brief 1500, block 3000, net 1200, req 1500, find 1500, doc 2500, delta 2000."""
import sys
from _common import S  # noqa: F401  (sets sys.path)
from desk.context import Engine

a = sys.argv[1:]
def opt(name, default=None):
    if name in a:
        i = a.index(name); v = a[i + 1]; del a[i:i + 2]; return v
    return default
budget = opt("--budget"); full = "--full" in a
a = [x for x in a if x != "--full"]
if len(a) < 2: raise SystemExit(__doc__)
proj, cmd, rest = a[0], a[1], a[2:]
E = Engine(proj)
kw = {"budget": int(budget)} if budget else {}
if cmd == "brief": out = E.brief(**kw); E.delta(mark=True)
elif cmd == "block": out = E.block(rest[0], full=full, **kw)
elif cmd == "net": out = E.net(rest[0], **kw)
elif cmd == "req": out = E.req(rest[0], **kw)
elif cmd == "find": out = E.find(" ".join(rest), **kw)
elif cmd == "doc": out = E.doc(" ".join(rest), **kw)
elif cmd == "delta": out = E.delta(**kw)
elif cmd == "index": out = f"index: {E.ix.stats}, chunks: {sum(1 for _ in E.ix.chunks())}"
else: raise SystemExit(__doc__)
print(out)
