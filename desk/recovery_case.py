"""Recovery case: the ten records every engineering recovery must retain (study report section 7.3, fragment 2).

    projects/<P>/state/recovery/<case_id>.json      one case per failure being recovered

 #  item                     field            source of truth (by reference)
 1  original requirement     requirements     REQ-xx ids (+ REQUIREMENTS.md hash)
 2  engineering assumptions  assumptions      ledger 'assumption' ids
 3  calculation evidence     calculations     qa[] / calc records (formula, inputs, result, datasheet page)
 4  selected components      components       ref, MPN, footprint, resolve.py record
 5  design decisions         decision_chain   ledger 'decision' ids from the failing object back to the requirement
 6  failure details          failure          FailureRecord id + gate report excerpt
 7  root-cause analysis      root_cause       claims, each citing an evidence ref that must exist; the originating decision
 8  proposed correction      correction       response kind, target decision id, new value, proposer
 9  verification results     verification     re-run gate result from a validator, never from the proposer
10  engineer approval        approval         ops.record_approval / RW-APR- id, or not_required + the policy rule

`close()` is fail-closed (AGENTS.md section L): it refuses unless every item is present or explicitly marked
not_applicable with a reason, the verification passed and came from someone other than the proposer, and the approval
id exists. On close it appends a ledger `correction` (refs -> the corrected decision) and the revised decision as a new
ledger `decision` with `supersedes`, so `tools/ledger.py history` shows the complete decision history.

Zero external dependencies.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from desk.errors import ProjectError, RecoveryRefused

ITEMS = ("requirements", "assumptions", "calculations", "components", "decision_chain", "failure", "root_cause",
         "correction", "verification", "approval")
TITLES = ("Original requirement", "Engineering assumptions", "Calculation evidence", "Selected components",
          "Design decisions", "Failure details", "Root-cause analysis", "Proposed correction", "Verification results",
          "Engineer approval")
_LEDGER_ID = re.compile(r"^L-\d{4,}$")
_EMPTY = (None, "", [], {})


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir(project: str) -> str:
    return os.path.join(project, "state", "recovery")


def _path(project: str, case_id: str) -> str:
    if not re.match(r"^RC-[A-Za-z0-9_\-]+$", case_id or ""):
        raise ProjectError(f"bad recovery case id {case_id!r}")
    return os.path.join(_dir(project), case_id + ".json")


def load(project: str, case_id: str) -> Dict[str, Any]:
    p = _path(project, case_id)
    if not os.path.exists(p):
        raise ProjectError(f"no recovery case {case_id} in {project}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(project: str, case: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(_dir(project), exist_ok=True)
    p = _path(project, case["case_id"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(case, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)        # atomic: a crash never leaves a half-written case
    return case


def ids(project: str) -> List[str]:
    d = _dir(project)
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []


def open_case(project: str, failure: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
    """Open a case for one failure. `failure` (item 6) needs failure_id and category."""
    if not failure.get("failure_id") or not failure.get("category"):
        raise ProjectError("a recovery case needs a failure with failure_id and category")
    case = {"case_id": f"RC-{uuid.uuid4().hex[:10]}", "status": "OPEN", "task_id": task_id, "opened_ts": _now(),
            "items": {k: None for k in ITEMS}, "not_applicable": {}, "discarded": [], "closed": None}
    case["items"]["failure"] = dict(failure)
    return save(project, case)


def _check_open(case: Dict[str, Any]) -> None:
    if case.get("status") != "OPEN":
        raise RecoveryRefused(f"recovery case {case.get('case_id')} is {case.get('status')}; a closed case is never edited")


def set_item(project: str, case_id: str, item: str, value: Any) -> Dict[str, Any]:
    if item not in ITEMS or item == "root_cause":
        raise ProjectError(f"unknown or guarded item {item!r} (root_cause goes through add_root_cause_claim)")
    case = load(project, case_id)
    _check_open(case)
    case["items"][item] = value
    case["not_applicable"].pop(item, None)
    return save(project, case)


def mark_not_applicable(project: str, case_id: str, item: str, reason: str) -> Dict[str, Any]:
    if item not in ITEMS:
        raise ProjectError(f"unknown item {item!r}")
    if not (reason or "").strip():
        raise RecoveryRefused(f"not_applicable for {item} needs a reason")
    case = load(project, case_id)
    _check_open(case)
    case["not_applicable"][item] = reason.strip()
    return save(project, case)


# ------------------------------------------------------------------------------------------------ evidence anchoring
def _evidence_problem(project: str, ref: str, excerpt: Optional[str]) -> Optional[str]:
    """None when `ref` resolves (and contains `excerpt`, when given); otherwise why it does not."""
    from desk import ledger as LG
    if _LEDGER_ID.match(ref):
        e = next((x for x in LG.read(project) if x.get("id") == ref), None)
        if e is None:
            return f"ledger id {ref} does not exist"
        if excerpt and excerpt not in json.dumps(e, ensure_ascii=False):
            return f"excerpt not found in ledger entry {ref}"
        return None
    if ref.startswith(("EV-", "FR-")):
        fp = os.path.join(project, "state", "reliability", "failures.jsonl")
        text = ""
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as f:
                text = f.read()
        return None if f'"{ref}"' in text else f"evidence id {ref} is not in state/reliability/failures.jsonl"
    rel = ref.split("#", 1)[0]
    root = os.path.realpath(project)
    full = os.path.realpath(os.path.join(project, rel))
    if not rel or os.path.isabs(rel) or not full.startswith(root + os.sep) or not os.path.isfile(full):
        return f"artifact {ref} does not exist in the project"
    if excerpt:
        with open(full, encoding="utf-8", errors="replace") as f:
            if excerpt not in f.read():
                return f"excerpt not found in {rel}"
    return None


def add_root_cause_claim(project: str, case_id: str, statement: str, evidence: List[Dict[str, str]],
                         confidence: str = "PLAUSIBLE", decision_id: Optional[str] = None,
                         source: str = "deterministic") -> Dict[str, Any]:
    """Item 7. A claim is kept only if it cites evidence and every cited ref resolves (and every excerpt is found in
    its artifact); otherwise it is discarded with the reasons. `decision_id` (the originating decision) must exist."""
    case = load(project, case_id)
    _check_open(case)
    problems = [] if evidence else ["cites no evidence"]
    for ev in evidence or []:
        why = _evidence_problem(project, str(ev.get("ref") or ""), ev.get("excerpt"))
        if why:
            problems.append(why)
    if decision_id:
        why = _evidence_problem(project, decision_id, None) if _LEDGER_ID.match(decision_id) else f"{decision_id} is not a ledger id"
        if why:
            problems.append(f"originating decision: {why}")
    claim = {"statement": statement, "evidence": list(evidence or []), "confidence": confidence,
             "decision_id": decision_id, "source": source, "ts": _now()}
    if problems:
        case["discarded"].append(dict(claim, reasons=problems))
    else:
        rc = case["items"]["root_cause"] or {"claims": [], "decision_id": None}
        rc["claims"].append(claim)
        if decision_id:
            rc["decision_id"] = decision_id
        case["items"]["root_cause"] = rc
        case["not_applicable"].pop("root_cause", None)
    return save(project, case)


# ------------------------------------------------------------------------------------------------ close
def missing_items(case: Dict[str, Any]) -> List[str]:
    out = []
    for k in ITEMS:
        v = case["items"].get(k)
        present = v not in _EMPTY and (k != "root_cause" or bool(v.get("claims")))
        if not present and not case["not_applicable"].get(k):
            out.append(k)
    return out


def close(project: str, case_id: str, decision_text: str, source: str) -> Dict[str, Any]:
    """Fail-closed close: raises RecoveryRefused unless all ten items are accounted for and independently verified."""
    from desk import ledger as LG
    from desk import ops
    case = load(project, case_id)
    _check_open(case)
    problems = [f"item {ITEMS.index(k) + 1} ({k}) is missing and not marked not_applicable" for k in missing_items(case)]
    it, na = case["items"], case["not_applicable"]
    corr, ver, appr = it.get("correction") or {}, it.get("verification") or {}, it.get("approval") or {}
    if corr:
        problems += [f"correction needs {f}" for f in ("response", "target_decision_id", "proposer") if not corr.get(f)]
    if ver:
        if not ver.get("passed"):
            problems.append("verification did not pass")
        src = str(ver.get("source") or "")
        if not src or src == corr.get("proposer") or src.startswith("model:"):
            problems.append("verification must come from a validator, never from the proposer or a model")
    if appr:
        aid = appr.get("approval_id")
        if aid:
            if aid not in {a.get("id") for a in ops.approvals(project)} and not str(aid).startswith("RW-APR-"):
                problems.append(f"approval id {aid} is not a recorded approval")
        elif not (appr.get("not_required") and appr.get("policy_rule")):
            problems.append("approval needs an approval_id, or not_required with the policy rule that allowed AUTO")
    if problems:
        raise RecoveryRefused(f"recovery case {case_id} cannot be closed: " + "; ".join(problems), problems=problems)
    closed: Dict[str, Any] = {"ts": _now(), "correction_id": None, "decision_id": None}
    target = corr.get("target_decision_id")
    if target and "correction" not in na:
        reqs = [r for r in (it.get("requirements") or []) if isinstance(r, str)]
        c = LG.add(project, "correction", f"recovery {case_id}: {corr.get('response')} -> {corr.get('new_value')}",
                   source=f"state/recovery/{case_id}.json", refs=target)
        d = LG.add_decision_record(project, decision_text, source, req_ids=reqs, supersedes=target, refs=c["id"],
                                   reasoning=f"recovery case {case_id}; originating decision "
                                             f"{(it.get('root_cause') or {}).get('decision_id')}",
                                   verification_result="PASS")
        closed.update(correction_id=c["id"], decision_id=d["id"])
    case["status"], case["closed"] = "CLOSED", closed
    return save(project, case)


def fmt(case: Dict[str, Any]) -> str:
    lines = [f"RECOVERY CASE {case['case_id']}  status={case['status']}  task={case.get('task_id') or '-'}"]
    for i, (k, title) in enumerate(zip(ITEMS, TITLES), 1):
        v, na = case["items"].get(k), case["not_applicable"].get(k)
        if v not in _EMPTY:
            shown = json.dumps(v, ensure_ascii=False)[:160]
        else:
            shown = f"not_applicable: {na}" if na else "MISSING"
        lines.append(f"  {i:2d}. {title:24s} {shown}")
    if case.get("discarded"):
        lines.append(f"  discarded root-cause claims: {len(case['discarded'])} (evidence did not resolve)")
    if case.get("closed"):
        lines.append(f"  closed: ledger correction {case['closed'].get('correction_id')}, "
                     f"new decision {case['closed'].get('decision_id')}")
    return "\n".join(lines)
