"""Project memory. Record decisions, verified facts and assumptions WITH their source, so no session re-derives them.
Usage:
  python tools/ledger.py <project> add <decision|fact|assumption|correction> "<text>" --source "<where>" [--block ID] [--refs L-0003]
  python tools/ledger.py <project> add decision "<text>" --source "<where>" [--req-ids REQ-01,REQ-02]
                        [--alternatives "A; B"] [--reasoning "<why>"] [--supersedes L-0004]
  python tools/ledger.py <project> list [--block ID] [--type decision]
  python tools/ledger.py <project> history <id>    requirement -> decision -> correction -> new decision
A 'correction' must name the corrected entry with --refs; --refs and --supersedes must name existing ids.
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
req_ids, alternatives, reasoning, supersedes = opt("--req-ids"), opt("--alternatives"), opt("--reasoning"), opt("--supersedes")
def _split(v, sep):
    return [x.strip() for x in v.split(sep) if x.strip()] if v else None
if len(a) < 2: raise SystemExit(__doc__)
proj, cmd = a[0], a[1]
if cmd == "add":
    if len(a) < 4: raise SystemExit(__doc__)
    if block: S.find_block(proj, block)
    if a[2] == "decision":
        if not source:
            raise SystemExit("a ledger 'decision' needs --source (datasheet page, client mail, calculation, ...)")
        print(fmt_ledger(LG.add_decision_record(proj, a[3], source, req_ids=_split(req_ids, ","),
                                                alternatives=_split(alternatives, ";"), reasoning=reasoning, block=block,
                                                supersedes=supersedes, refs=refs)))
    else:
        print(fmt_ledger(LG.add(proj, a[2], a[3], block=block, source=source, refs=refs)))
elif cmd == "list":
    for e in LG.read(proj):
        if (not block or e.get("block") == block) and (not typ or e["type"] == typ): print(fmt_ledger(e))
elif cmd == "history":
    if len(a) < 3: raise SystemExit(__doc__)
    from desk.decision_graph import history, fmt_history
    print(fmt_history(history(LG.read(proj), a[2])))
else: raise SystemExit(__doc__)
