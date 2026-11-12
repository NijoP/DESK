"""Check what one Weft run did on the DESK side, from DESK's own records (never from Weft's word).

    python3 check_trace.py --projects-root R --project P --run RUN_ID
        [--called NODE ...] [--replayed NODE ...] [--not-called NODE ...] [--failed NODE=CODE ...]
        [--approval STAGE=approved|rejected ...] [--no-approval] [--all-passed]

Prints one JSON object: every check with PASS or FAIL, and the trace it read. Exit 0 only when every check passes.
A check that reads nothing fails: an empty trace never counts as "not called" for a run DESK never heard of.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from desk.weft.store import RecordStore, StoreError  # noqa: E402


def approvals_of(store: RecordStore, run_id: str) -> List[Dict[str, Any]]:
    d = os.path.join(store.root, "approvals")
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    rec = json.load(f)
                if rec.get("run_id") == run_id:
                    out.append(rec)
    return out


def check(args: argparse.Namespace) -> Dict[str, Any]:
    store = RecordStore(args.project, args.projects_root)
    trace = store.read_trace(args.run)
    approvals = approvals_of(store, args.run)
    called = [e.get("node") for e in trace]
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    add("DESK has a trace for this run", bool(trace), f"{len(trace)} call(s)")
    for node in args.called:
        add(f"called {node}", node in called)
    for node in args.replayed:
        hit = [e for e in trace if e.get("node") == node]
        add(f"{node} replayed DESK's stored result", bool(hit) and all(e.get("replayed") for e in hit),
            ", ".join("replayed" if e.get("replayed") else "executed" for e in hit))
    for node in args.not_called:
        add(f"not called {node}", bool(trace) and node not in called)
    for spec in args.failed:
        node, _, code = spec.partition("=")
        hit = [e for e in trace if e.get("node") == node and not e.get("ok")]
        add(f"{node} failed with {code}", any(e.get("error") == code for e in hit), ", ".join(str(e.get("error")) for e in hit))
    for spec in args.approval:
        stage, _, decision = spec.partition("=")
        hit = [a for a in approvals if a.get("stage") == stage]
        add(f"{stage} approval recorded as {decision}", any(a.get("decision") == decision for a in hit),
            ", ".join(f"{a.get('stage')}={a.get('decision')}" for a in hit))
    if args.no_approval:
        add("no approval recorded", bool(trace) and not approvals, ", ".join(a.get("ref", "") for a in approvals))
    if args.all_passed:
        bad = [e.get("node") for e in trace if not (e.get("ok") and e.get("passed"))]
        add("every DESK call passed", bool(trace) and not bad, ", ".join(str(b) for b in bad))
    return {"project": args.project, "run": args.run, "ok": all(c["result"] == "PASS" for c in checks), "checks": checks,
            "called": called, "approvals": [{k: a.get(k) for k in ("ref", "stage", "decision", "subject_hash")} for a in approvals]}


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--projects-root", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--called", nargs="*", default=[])
    p.add_argument("--replayed", nargs="*", default=[])
    p.add_argument("--not-called", nargs="*", default=[])
    p.add_argument("--failed", nargs="*", default=[])
    p.add_argument("--approval", nargs="*", default=[])
    p.add_argument("--no-approval", action="store_true")
    p.add_argument("--all-passed", action="store_true")
    args = p.parse_args(argv)
    try:
        doc = check(args)
    except StoreError as e:
        doc = {"ok": False, "checks": [{"check": "open the DESK project", "result": "FAIL", "detail": e.message}]}
    print(json.dumps(doc, indent=2))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
