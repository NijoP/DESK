"""DESK Learning Engine CLI (docs/08_LEARNING_ENGINE.md). Nothing here edits a file except `accept`.
  python tools/learn.py setup                 clone Backpass (MIT) at the pinned commit into library/tools/backpass
  python tools/learn.py run [--top 10]        collect -> detect -> corroborate -> propose -> report (read-only)
  python tools/learn.py bench                 replay measured waste against the current DESK tools (before/after tokens)
  python tools/learn.py review                compact list of open proposals
  python tools/learn.py show <ID>             one proposal with its verbatim evidence
  python tools/learn.py accept <ID> --reviewer NAME [--engineering-review NAME]
  python tools/learn.py reject <ID> --reviewer NAME --reason "..."
Accepting an instruction/gotcha proposal appends ONE line to a marked, human-approved section (budget-checked,
regression tests run, auto-revert on failure). All other proposals become task files; protected engineering
surfaces (lint/ERC/calc/release/verify/style) can never be edited by this tool."""
import os, sys, json, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk.learn import engine as L

a = sys.argv[1:]
def opt(n, d=None):
    if n in a:
        i = a.index(n); v = a[i + 1]; del a[i:i + 2]; return v
    return d
reviewer, reason, eng = opt("--reviewer", ""), opt("--reason", ""), opt("--engineering-review")
top = int(opt("--top", "10"))
cmd = a[0] if a else "run"
if cmd == "setup":
    pin = open(os.path.join(L.ROOT, "library", "tools", "BACKPASS_PIN")).read().strip()
    d = L.DEFAULTS["backpass_dir"]
    if not os.path.exists(d):
        subprocess.run(["git", "clone", "-q", "https://github.com/kunchenguid/backpass", d], check=True)
    subprocess.run(["git", "-C", d, "fetch", "-q", "--depth", "50", "origin"], check=False)
    subprocess.run(["git", "-C", d, "checkout", "-q", pin], check=True)
    print("backpass at", pin)
elif cmd == "run":
    t0 = time.time()
    st = L.collect(); gaps, summ = L.analyze(); props = L.propose(gaps)
    rep = L.report(props, summ, st)
    t = summ["totals"]
    print(f"sessions {t.get('sessions', 0)} (new/changed {st['new_or_changed']}), tool calls {t.get('tools', 0)}, "
          f"tool-output tokens {t.get('result_tokens', 0)}, gaps {len(gaps)}, proposals {len(props)}, {time.time() - t0:.1f}s")
    for p in props[:top]:
        print(f"{p['id']} {p['kind']:16s} {p['target']:14s} s={p['n_sessions']:<3d} tok={p['measured_tokens']:<8d} {p['why'][:90]}")
    print("full report: .desk_learn/report.md | next: python tools/learn.py show <ID>")
elif cmd == "bench":
    b = L.bench()
    for f, n, bt, at in b["rows"][:12]: print(f"{f:32s} reads={n:<3d} measured={bt:<7d} via ctx api={at:<6d} saved={100 * (1 - at / max(1, bt)):.0f}%")
    print(f"replayable reference reads: {b['before']} tokens -> {b['after']} tokens "
          f"({100 * (1 - b['after'] / max(1, b['before'])):.0f}% less); not replayable (generic SKILL.md etc.): {b['not_replayable_tokens']} tokens")
elif cmd == "review":
    for p in json.load(open(os.path.join(L.STATE, "proposals.json"))):
        print(f"{p['id']} {p['kind']:16s} s={p['n_sessions']:<3d} tok={p['measured_tokens']:<8d} {'PROTECTED ' if p['protected'] else ''}{p['change'][:100]}")
elif cmd == "show":
    p = {x["id"]: x for x in json.load(open(os.path.join(L.STATE, "proposals.json")))}[a[1]]
    print(f"{p['id']} [{p['kind']} -> {p['target']}] sessions={p['n_sessions']} occurrences={p['occurrences']} tokens={p['measured_tokens']}"
          f"{' PROTECTED' if p['protected'] else ''}\nwhy: {p['why']}\nchange: {p['change']}\n"
          + (f"edit: {p['edit_file']} += \"{p['rule']}\"\n" if p.get("edit_file") and p.get("rule") else "on accept: task file\n") + "evidence:")
    for e in p["evidence"]: print(f"  - {e['session']} ({e['model']}) ev {e['event']}: \"{e['quote'][:200]}\"")
elif cmd in ("accept", "reject"):
    if not reviewer: raise SystemExit("--reviewer NAME is required (the human gate)")
    if cmd == "reject" and not reason: raise SystemExit("--reason is required for reject")
    r = L.decide(a[1], cmd, reason, reviewer, eng)
    print(json.dumps({k: v for k, v in r.items() if v not in (None, "")}, indent=1))
else:
    raise SystemExit(__doc__)
