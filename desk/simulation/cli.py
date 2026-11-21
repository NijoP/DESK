"""desk.py sim: optional circuit simulation.

  python tools/desk.py sim engines [--json]                       registered engines and whether each is installed
  python tools/desk.py sim netlist <sim.json> [--block <block.json>] [--models <store.json>] [--json]
                                                                  print the generated deck and unsupported parts
  python tools/desk.py sim run <sim.json> [--block <block.json>] [--models <store.json>] [--engine ngspice]
        [--expect <expectations.json> | --expect-qa] [--out <dir>] [--timeout <s>] [--json]
                                                                  run, verify against expected ranges, export CSV/JSON
  python tools/desk.py sim models [list|check] [--models <store.json>] [--json]   model provenance

The block comes from --block or from a "block" object inside the sim spec. --expect-qa uses the block's qa
entries that carry a "sim" key. Exit codes: run returns 0 only for verdict PASS, or for a completed run with
no expectations. netlist returns 1 when a part is unsupported.
Simulation alone does not prove a PCB is electrically or thermally safe.
"""
import json
import os
import sys
from typing import List, Optional

from desk.errors import UsageError
from desk.simulation import base as B


def _opt(a: List[str], flag: str) -> Optional[str]:
    if flag in a:
        i = a.index(flag)
        if i + 1 >= len(a):
            raise UsageError(f"{flag} needs a value")
        return a[i + 1]
    return None


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise UsageError(f"cannot read {path}: {e}")
    except ValueError as e:
        raise UsageError(f"{path} is not valid JSON: {e}")


def _positional(a: List[str]) -> List[str]:
    valued = {"--block", "--models", "--engine", "--expect", "--out", "--timeout"}
    out, skip = [], False
    for x in a:
        if skip:
            skip = False
            continue
        if x in valued:
            skip = True
            continue
        if not x.startswith("--"):
            out.append(x)
    return out


def _circuit(a: List[str]):
    from desk.simulation import models as M, netlist as N
    pos = _positional(a[1:])
    if not pos:
        raise UsageError("usage: desk.py sim " + a[0] + " <sim.json> [--block <block.json>] [--models <store.json>]")
    spec = _load(pos[0])
    block_path = _opt(a, "--block")
    block = _load(block_path) if block_path else spec.get("block")
    store = M.ModelStore(_opt(a, "--models") or M.DEFAULT_STORE)
    return N.build_circuit(block, spec, store), block


def _print_netlist_issues(c) -> None:
    for u in c.unsupported:
        print(f"UNSUPPORTED {u['ref']}: {u['reason']}")
    for x in c.excluded:
        print(f"excluded    {x['ref']}: {x['reason']}")
    for w in c.warnings:
        print(f"warning     {w}")
    for m in c.models:
        print(f"model       {m['name']} [{m['status']}] {(m.get('source') or {}).get('reference', '')}")


def main(argv: List[str]) -> int:
    a = list(argv)
    sub = a[0] if a else "engines"
    as_json = "--json" in a

    if sub == "engines":
        infos = B.engines()
        if as_json:
            print(json.dumps([i.__dict__ for i in infos], indent=1))
        else:
            for i in infos:
                state = f"available {i.version} ({i.path})" if i.available else f"not available: {i.detail}"
                print(f"{i.name:10s} {state}")
            print("NOTE: " + B.SAFETY_NOTICE)
        return 0

    if sub == "models":
        from desk.simulation import models as M
        act = next((x for x in a[1:] if x in ("list", "check")), "list")
        store = M.ModelStore(_opt(a, "--models") or M.DEFAULT_STORE)   # loading validates every card
        rows = store.rows()
        if as_json:
            print(json.dumps(rows, indent=1))
        else:
            if not rows:
                print(f"no models in {store.path}")
            for r in rows:
                print(f"{r['name']:16s} {r['kind']:6s} {r['status']:10s} {r['source'] or '-':12s} {r['reference']}")
        if act == "check":
            unverified = [r["name"] for r in rows if r["status"] != M.TRACEABLE]
            if not as_json:
                print(f"{len(rows)} model(s), {len(unverified)} UNVERIFIED" + (f": {', '.join(unverified)}" if unverified else ""))
            return 1 if unverified else 0
        return 0

    if sub == "netlist":
        from desk.simulation.ngspice import render_deck
        c, _ = _circuit(a)
        if as_json:
            print(json.dumps(dict(c.to_dict(), deck=render_deck(c)), indent=1))
        else:
            print(render_deck(c), end="")
            _print_netlist_issues(c)
        return 1 if c.unsupported else 0

    if sub == "run":
        from desk.simulation import export as X, verify as V
        c, block = _circuit(a)
        if c.unsupported:
            _print_netlist_issues(c)
        c.require_complete()
        exp_path = _opt(a, "--expect")
        if exp_path:
            data = _load(exp_path)
            expectations = data.get("expectations", []) if isinstance(data, dict) else data
        elif "--expect-qa" in a:
            expectations = V.expectations_from_qa(block or {})
        else:
            expectations = []
        expectations = [V.normalise(e) for e in expectations]
        timeout = float(_opt(a, "--timeout")) if _opt(a, "--timeout") else None
        engine = B.get(_opt(a, "--engine") or "ngspice")
        out_dir = _opt(a, "--out")
        result = engine.run(c, timeout_s=timeout, work_dir=os.path.join(out_dir, "engine") if out_dir else None)
        report = V.verify(result, expectations, c.node_map)
        paths = X.write_exports(result, out_dir, {"verification": report, "circuit": c.to_dict()}) if out_dir else []
        if as_json:
            print(json.dumps({"result": result.to_dict(), "verification": report, "exports": paths}, indent=1))
        else:
            print(f"{result.engine} {result.engine_version}: {result.status} in {result.elapsed_s}s")
            for m in result.measurements.values():
                print(f"  measure {m.name:20s} " + (f"{m.value:.6g}" if m.ok else f"FAILED ({m.detail})"))
            print(V.render(report))
            for p in paths:
                print(f"  wrote {p}")
        ok = report["verdict"] == V.PASS or (report["verdict"] == V.NO_EXPECTATIONS and result.status == B.COMPLETED)
        return 0 if ok else 1

    raise UsageError(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
