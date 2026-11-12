"""Layers 2 and 3 of the diagnosis: deterministic root cause first, evidence-grounded model reasoning second.

Layer 2 (`diagnose`) applies rules over the facts the collector established. Each rule yields a `Hypothesis` with a
confidence that the rule, not a model, assigns. Examples:

    bound window missing from /eda-windows and one window hosts the project uuid  -> WINDOW_ID_ROTATED, CONFIRMED
    raw return true, before == after fingerprint, method is DIALOG                 -> API_FALSE_SUCCESS, CONFIRMED
    stdout has UnsupportedClassVersionError                                        -> JAVA_RUNTIME_INCOMPATIBLE, CONFIRMED
    feasibility decisions present                                                  -> ROUTER_RULE_CONFLICT, CONFIRMED
    every chunk outcome is CHUNK_TIMEOUT and no checkpoint                         -> ROUTER_ENGINE_TIMEOUT (chunk defect), CONFIRMED
    passes_since_best >= patience                                                  -> ROUTER_STAGNATION, STRONGLY_SUPPORTED

Layer 3 (`diagnostic_packet`, `validate_model_diagnosis`, `evaluate`) prepares a structured packet for a model, parses
the model's answer, and refuses any factual statement that does not cite an evidence id present in the packet. A
model hypothesis is capped at PLAUSIBLE unless a deterministic rule agrees (then STRONGLY_SUPPORTED); CONFIRMED is
reserved for deterministic rules. An independent evaluator answer is compared with the builder's; disagreement is
preserved, never resolved by picking one.

Zero external dependencies; the model call itself lives in the orchestrator adapters.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from desk.reliability.models import Confidence as K, FailureCategory as C, ExecutionState as X, FailureRecord, Hypothesis


# ------------------------------------------------------------------------------------------------ layer 2
def _ev(rec: FailureRecord, *kinds: str, contains: str = "") -> List[str]:
    out = []
    for e in rec.evidence:
        if kinds and e.kind not in kinds:
            continue
        if contains and contains.lower() not in (e.source + " " + e.summary).lower():
            continue
        out.append(e.id)
    return out


def diagnose(rec: FailureRecord, facts: Dict[str, Any]) -> List[Hypothesis]:
    hs: List[Hypothesis] = []
    wins = facts.get("windows") or []
    sess = facts.get("session") or {}
    hosting = facts.get("windows_hosting_project") or []
    text = "\n".join([rec.message, rec.stdout_tail or "", rec.stderr_tail or "", facts.get("freerouting_log_tail", "")])

    # --- window / identity
    if wins and sess.get("window_id") and not facts.get("bound_window_present"):
        if len(hosting) == 1:
            hs.append(Hypothesis(C.WINDOW_ID_ROTATED, f"bound window {sess['window_id']} is gone and exactly one window ({hosting[0]}) "
                                                     "hosts the project uuid: the gateway reconnected and rotated the ids", K.CONFIRMED,
                                 _ev(rec, "readback", contains="/eda-windows") + _ev(rec, "process", contains="session")))
        elif len(hosting) > 1:
            hs.append(Hypothesis(C.WINDOW_ID_ROTATED, f"bound window gone; {len(hosting)} windows host the project uuid: rebind is ambiguous",
                                 K.CONFIRMED, _ev(rec, "readback", contains="/eda-windows"), alternatives=["two EasyEDA windows opened the same project"]))
        else:
            hs.append(Hypothesis(C.WINDOW_DISCONNECTED, "bound window gone and no connected window hosts the project: the project was closed or EasyEDA restarted",
                                 K.STRONGLY_SUPPORTED, _ev(rec, "readback", contains="/eda-windows"), missing_evidence=["EasyEDA process state"]))
    if rec.category == C.WRONG_PROJECT_CONTEXT and sess.get("bound_by") == "unbound":
        hs.append(Hypothesis(C.WRONG_PROJECT_CONTEXT, "the session had no window binding; the gateway would execute in the ACTIVE window",
                             K.CONFIRMED, _ev(rec, "process", contains="session")))
    # --- API false success / unknown outcome
    if rec.execution_state == X.FALSE_SUCCESS or rec.category == C.API_FALSE_SUCCESS:
        dm = facts.get("dialog_method")
        if dm:
            hs.append(Hypothesis(C.API_FALSE_SUCCESS, f"{dm} returned success but is a DIALOG method: nothing is applied until a human confirms; "
                                                     "before/after fingerprints are identical", K.CONFIRMED, _ev(rec, "readback")))
        elif rec.before_fingerprint and rec.before_fingerprint == rec.after_fingerprint:
            hs.append(Hypothesis(C.API_FALSE_SUCCESS, "the API returned success and the readback fingerprint did not change",
                                 K.CONFIRMED, _ev(rec, "readback"), alternatives=["readback was stale (EXECUTED_STALE_READBACK)"],
                                 missing_evidence=["a later readback showing the change"]))
    if rec.execution_state in (X.EXECUTED_RESPONSE_LOST, X.UNKNOWN) and rec.category in (C.UNKNOWN_MUTATION_OUTCOME, C.API_TIMEOUT):
        hs.append(Hypothesis(C.UNKNOWN_MUTATION_OUTCOME, "the request may have executed (gateway cap / lost response); outcome unknown until readback",
                             K.CONFIRMED, _ev(rec, "readback") or _ev(rec, "journal"), missing_evidence=["readback against the postcondition"]))
    if rec.execution_state == X.PARTIAL:
        hs.append(Hypothesis(C.PARTIAL_MUTATION, "readback changed but the postcondition is not met: part of the mutation applied", K.CONFIRMED, _ev(rec, "readback")))
    # --- engine
    if "UnsupportedClassVersionError" in text or "class file version" in text:
        hs.append(Hypothesis(C.JAVA_RUNTIME_INCOMPATIBLE, "the JVM rejected the engine's class-file version", K.CONFIRMED, _ev(rec, "log", "env")))
    if "OutOfMemoryError" in text:
        hs.append(Hypothesis(C.ROUTER_RESOURCE_EXHAUSTION, "the engine ran out of heap", K.CONFIRMED, _ev(rec, "log")))
    outcomes = facts.get("chunk_outcomes") or []
    ckpt = facts.get("checkpoint") or {}
    if outcomes:
        if "ENGINE_UNBOUNDABLE" in outcomes or "ENGINE_IGNORES_LIMITS" in outcomes:
            hs.append(Hypothesis(C.EXTERNAL_TOOL_UNSUPPORTED, "the engine does not honour max_passes/job_timeout: a chunk cannot end with a SES",
                                 K.CONFIRMED, _ev(rec, "file", contains="progress_chunks") + _ev(rec, "env")))
        timeouts = [o for o in outcomes if o == "CHUNK_TIMEOUT"]
        if timeouts and not ckpt.get("has_best"):
            hs.append(Hypothesis(C.ROUTER_ENGINE_TIMEOUT, f"{len(timeouts)} chunk(s) hit DESK's window before writing a SES and no checkpoint exists: "
                                                          "the chunk window is too small for this board's pass time", K.CONFIRMED,
                                 _ev(rec, "file", contains="progress_chunks"), alternatives=["the engine ignores limits (check the profile)"]))
        if "ZERO_PASSES_TIMEOUT" in outcomes:
            hs.append(Hypothesis(C.ROUTER_ENGINE_CRASH, "the window elapsed without a single pass: the engine never started routing (DSN load failure)",
                                 K.STRONGLY_SUPPORTED, _ev(rec, "file", contains="progress_chunks") + _ev(rec, "log"),
                                 alternatives=["one pass is longer than the whole window"], missing_evidence=["engine log of the chunk"]))
        if "SES_CORRUPTED" in outcomes:
            hs.append(Hypothesis(C.ROUTER_SES_INVALID, "a chunk wrote a SES that does not parse or has no routes", K.CONFIRMED, _ev(rec, "file", contains="progress_chunks")))
        if "PLATEAU" in outcomes:
            hs.append(Hypothesis(C.ROUTER_STAGNATION, f"consecutive chunks did not improve on the checkpoint ({ckpt.get('best_unrouted')} unrouted)",
                                 K.STRONGLY_SUPPORTED, _ev(rec, "file", contains="progress_chunks")))
    prog = (facts.get("route") or {}).get("progress.json") or {}
    if prog and prog.get("passes_since_best", 0) >= 4 and (prog.get("best_unrouted") or 0) > 0:
        hs.append(Hypothesis(C.ROUTER_STAGNATION, f"no new best for {prog['passes_since_best']} passes (best {prog['best_unrouted']} at pass {prog.get('best_pass')})",
                             K.STRONGLY_SUPPORTED, _ev(rec, "file", contains="progress.json")))
    if facts.get("decisions"):
        d = facts["decisions"][0]
        hs.append(Hypothesis(C.ROUTER_RULE_CONFLICT, f"net {d.get('net')} has a spacing rule of {d.get('rule_mm')} mm but its own pads sit "
                                                     f"{d.get('pin_field_mm')} mm apart: no trace can satisfy the rule", K.CONFIRMED,
                             _ev(rec, "file", contains="feasibility") + _ev(rec, "file", contains="engineering_decisions")))
    blocked = facts.get("blocked_pads") or []
    if blocked and not facts.get("decisions"):
        kinds = sorted({b.get("classification") for b in blocked if isinstance(b, dict)})
        hs.append(Hypothesis(C.ROUTER_NO_LEGAL_ESCAPE, f"{len(blocked)} pad(s) blocked before routing: {', '.join(k for k in kinds if k)}",
                             K.CONFIRMED, _ev(rec, "file", contains="feasibility")))
    if rec.category == C.DESIGN_PROFILE_INVALID:
        hs.append(Hypothesis(C.DESIGN_PROFILE_INVALID, rec.message[:200], K.CONFIRMED, _ev(rec)))
    if rec.category == C.LOCK_CONFLICT:
        hs.append(Hypothesis(C.LOCK_CONFLICT, "another live writer holds the project lock", K.CONFIRMED, _ev(rec, "journal") or _ev(rec)))
    if not hs:
        hs.append(Hypothesis(rec.category, f"no deterministic rule matched; classified as {rec.category.value} from the error type",
                             K.UNVERIFIED, _ev(rec), missing_evidence=["a known signature or a readback that distinguishes the causes"]))
    return hs


# ------------------------------------------------------------------------------------------------ layer 3
PACKET_SCHEMA = {
    "observed_facts": "list[str]: each fact ends with [EV-xxxx] citing an evidence id from the packet",
    "evidence_references": "list[str]: evidence ids used",
    "root_cause": {"category": "one of the failure categories", "statement": "str", "confidence": "CONFIRMED|STRONGLY_SUPPORTED|PLAUSIBLE|UNVERIFIED|DISPROVEN"},
    "alternatives": "list[str]",
    "missing_evidence": "list[str]",
    "proposed_recovery": "list[{kind: str, description: str}] using the allowed recovery kinds",
    "expected_effect": "str",
    "risks": "list[str]",
    "requires_human_approval": "bool",
    "verification_criteria": "list[str]",
}


def diagnostic_packet(rec: FailureRecord, facts: Dict[str, Any], hypotheses: Sequence[Hypothesis],
                      allowed_kinds: Sequence[str] = ()) -> Dict[str, Any]:
    """The structured packet a model receives: facts with ids, deterministic hypotheses, and nothing else."""
    from desk.reliability.recovery_policy import AUTO_KINDS, APPROVAL_KINDS
    return {
        "failure": {"id": rec.failure_id, "category": rec.category.value, "execution_state": rec.execution_state.value,
                    "module": rec.module, "operation": rec.operation, "message": rec.message[:600], "engine_version": rec.engine_version,
                    "project_id": rec.project_id, "document_uuid": rec.document_uuid, "window_id": rec.window_id},
        "evidence": [{"id": e.id, "kind": e.kind, "source": e.source, "summary": e.summary[:400]} for e in rec.evidence],
        "deterministic_hypotheses": [h.to_dict() for h in hypotheses],
        "facts": {k: v for k, v in facts.items() if k in ("windows", "session", "pending_ops", "chunk_outcomes", "checkpoint", "plans",
                                                          "decisions", "blocked_pads", "hotspots", "problem_nets", "engines", "resources",
                                                          "capabilities", "known_failures", "dialog_method")},
        "categories": [c.value for c in C],
        "allowed_recovery_kinds": sorted(set(allowed_kinds) or (AUTO_KINDS | APPROVAL_KINDS)),
        "answer_schema": PACKET_SCHEMA,
        "rules": ["Every observed fact must cite an evidence id in square brackets.",
                  "Say UNKNOWN when evidence is missing; never invent a measurement.",
                  "A hypothesis is at most PLAUSIBLE unless a deterministic hypothesis above agrees.",
                  "Never propose weakening a clearance, creepage, voltage or current rule; name it as a human decision."],
    }


def _cite_ok(statement: str, ids: set) -> bool:
    import re
    cited = re.findall(r"\[(EV-[0-9a-f]+)\]", statement or "")
    return bool(cited) and all(c in ids for c in cited)


def validate_model_diagnosis(answer: Any, packet: Dict[str, Any], source: str = "model") -> Tuple[Optional[Hypothesis], List[str]]:
    """Parse a model's answer against the packet. Returns (hypothesis or None, problems). Uncited facts are problems;
    an unknown category or confidence is a problem; CONFIRMED from a model is demoted."""
    problems: List[str] = []
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except Exception:
            return None, ["answer is not JSON"]
    if not isinstance(answer, dict):
        return None, ["answer is not an object"]
    ids = {e["id"] for e in packet.get("evidence", [])}
    facts = answer.get("observed_facts") or []
    if not isinstance(facts, list) or not facts:
        problems.append("observed_facts missing")
    for f in facts if isinstance(facts, list) else []:
        if not _cite_ok(str(f), ids):
            problems.append(f"fact without a valid evidence citation: {str(f)[:80]}")
    rc = answer.get("root_cause") or {}
    try:
        cat = C(str(rc.get("category", "")).upper())
    except ValueError:
        problems.append(f"unknown category {rc.get('category')!r}")
        cat = C.UNKNOWN_FAILURE
    try:
        conf = K(str(rc.get("confidence", "UNVERIFIED")).upper())
    except ValueError:
        problems.append(f"unknown confidence {rc.get('confidence')!r}")
        conf = K.UNVERIFIED
    det = {h["category"] for h in packet.get("deterministic_hypotheses", []) if h.get("confidence") in ("CONFIRMED", "STRONGLY_SUPPORTED")}
    if conf == K.CONFIRMED:
        conf = K.STRONGLY_SUPPORTED if cat.value in det else K.PLAUSIBLE
        problems.append("model claimed CONFIRMED; demoted (only deterministic rules confirm)")
    elif conf == K.STRONGLY_SUPPORTED and cat.value not in det:
        conf = K.PLAUSIBLE
    kinds = set(packet.get("allowed_recovery_kinds", []))
    for p in answer.get("proposed_recovery") or []:
        k = p.get("kind") if isinstance(p, dict) else None
        if k not in kinds:
            problems.append(f"proposed recovery kind not allowed: {k!r}")
    stmt = str(rc.get("statement", "")).strip()
    if not stmt:
        problems.append("root_cause.statement missing")
    hyp = Hypothesis(cat, stmt or "(no statement)", conf,
                     evidence_ids=[i for i in (answer.get("evidence_references") or []) if i in ids],
                     alternatives=[str(a) for a in (answer.get("alternatives") or [])],
                     missing_evidence=[str(m) for m in (answer.get("missing_evidence") or [])], source=source)
    if any("without a valid evidence citation" in p for p in problems) or not stmt:
        hyp.confidence = K.UNVERIFIED
    return hyp, problems


def evaluate(builder: Optional[Hypothesis], evaluator: Optional[Hypothesis], evaluator_problems: Sequence[str] = ()) -> Dict[str, Any]:
    """Compare the builder's diagnosis with an independent evaluator's. Both are preserved; the result says whether
    they agree, and when they do not, asks for more evidence or human review instead of choosing."""
    if builder is None or evaluator is None:
        return {"agreement": None, "verdict": "INCOMPLETE", "needs_human": True,
                "note": "builder or evaluator answer missing / invalid"}
    same_cat = builder.category == evaluator.category
    if same_cat:
        order = [K.CONFIRMED, K.STRONGLY_SUPPORTED, K.PLAUSIBLE, K.UNVERIFIED, K.DISPROVEN]
        conf = max((builder.confidence, evaluator.confidence), key=order.index)   # the weaker of the two
        return {"agreement": True, "verdict": "AGREE", "category": builder.category.value, "confidence": conf.value,
                "needs_human": conf in (K.UNVERIFIED, K.DISPROVEN), "note": "evaluator agrees on the category; confidence is the lower of the two"}
    return {"agreement": False, "verdict": "DISAGREE", "builder": builder.to_dict(), "evaluator": evaluator.to_dict(),
            "needs_human": True, "note": "builder and evaluator disagree; both findings kept; collect the missing evidence or ask the Captain",
            "missing_evidence": sorted(set(builder.missing_evidence) | set(evaluator.missing_evidence))}
