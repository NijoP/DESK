"""Project memory. Record decisions, verified facts and assumptions WITH their source, so no session re-derives them.
Usage:
  python tools/ledger.py <project> add <decision|fact|assumption|correction> "<text>" --source "<where>" [--block ID] [--refs L-0003]
  python tools/ledger.py <project> list [--block ID] [--type decision]
'built' and 'verified' entries are written automatically by tools/build.py and tools/verify.py."""
import sys
from _common import S  # noqa: F401
from desk import ledger as LG
from desk.context import fmt_ledger

a = sys.argv[1:]
def opt(name):
    if name in a:
        i = a.index(name); v = a[i + 1]; del a[i:i + 2]; return v
    return None
block, source, refs, typ = opt("--block"), opt("--source"), opt("--refs"), opt("--type")
if len(a) < 2: raise SystemExit(__doc__)
proj, cmd = a[0], a[1]
if cmd == "add":
    if len(a) < 4: raise SystemExit(__doc__)
    if block: S.find_block(proj, block)
    print(fmt_ledger(LG.add(proj, a[2], a[3], block=block, source=source, refs=refs)))
elif cmd == "list":
    for e in LG.read(proj):
        if (not block or e.get("block") == block) and (not typ or e["type"] == typ): print(fmt_ledger(e))
else: raise SystemExit(__doc__)
