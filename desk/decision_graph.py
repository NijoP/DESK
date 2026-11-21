"""Decision history over the project ledger (study report section 7.3): requirement -> decision -> correction -> new decision.

Edges, all read from projects/<P>/LEDGER.jsonl (append-only; nothing is rewritten):
  decision.supersedes -> the earlier decision it replaces
  correction.refs     -> the entry it corrects
  decision.req_ids    -> the requirement ids (REQ-xx in REQUIREMENTS.md) the decision serves
Legacy entries without these fields load unchanged; they simply have no edges.

Zero external dependencies.
"""
from __future__ import annotations

from typing import Any, Dict, List

from desk.errors import UsageError


def _ids(v: Any) -> List[str]:
    return [v] if isinstance(v, str) else [x for x in (v or []) if isinstance(x, str)]


def history(entries: List[Dict[str, Any]], entry_id: str) -> Dict[str, Any]:
    """The decision chain through `entry_id`: requirements, decisions oldest first, and the corrections between them."""
    by_id = {e.get("id"): e for e in entries}
    if entry_id not in by_id:
        raise UsageError(f"no ledger entry {entry_id}")
    start = by_id[entry_id]
    if start.get("type") == "correction":
        refs = [r for r in _ids(start.get("refs")) if r in by_id]
        if not refs:
            return {"requirements": [], "chain": [], "corrections": [start]}
        start = by_id[refs[0]]
    back, cur, seen = [], start, set()
    while cur is not None and cur.get("id") not in seen:          # back along supersedes (cycle-safe)
        seen.add(cur.get("id"))
        back.append(cur)
        prev = [p for p in _ids(cur.get("supersedes")) if p in by_id]
        cur = by_id[prev[0]] if prev else None
    chain = list(reversed(back))
    cur = start
    while True:                                                    # forward to the current decision
        nxt = [e for e in entries if cur.get("id") in _ids(e.get("supersedes")) and e.get("id") not in seen]
        if not nxt:
            break
        cur = nxt[0]
        seen.add(cur.get("id"))
        chain.append(cur)
    members = {e.get("id") for e in chain}
    corrections = [e for e in entries if e.get("type") == "correction" and members & set(_ids(e.get("refs")))]
    reqs: List[str] = []
    for e in chain + corrections:
        for r in _ids(e.get("req_ids")):
            if r not in reqs:
                reqs.append(r)
    return {"requirements": reqs, "chain": chain, "corrections": corrections}


def fmt_history(h: Dict[str, Any]) -> str:
    """requirement -> decision -> correction -> new decision, one step per line."""
    corr_by_target: Dict[str, List[Dict[str, Any]]] = {}
    for c in h["corrections"]:
        for r in _ids(c.get("refs")):
            corr_by_target.setdefault(r, []).append(c)
    lines = [f"requirement {r}" for r in h["requirements"]] or ["requirement (none recorded: entry has no req_ids)"]
    if not h["chain"]:
        lines += [f"  -> correction {c.get('id')} {c.get('text', '')} (refs unresolved)" for c in h["corrections"]]
    for i, e in enumerate(h["chain"]):
        label = "decision" if i == 0 else "new decision"
        extra = f" (supersedes {', '.join(_ids(e.get('supersedes')))})" if e.get("supersedes") else ""
        lines.append(f"  -> {label} {e.get('id')} [{e.get('type')}] {e.get('text', '')}{extra}")
        for c in corr_by_target.get(e.get("id"), []):
            lines.append(f"  -> correction {c.get('id')} {c.get('text', '')} (refs {', '.join(_ids(c.get('refs')))})")
    return "\n".join(lines)
