"""DESK Weft node handlers and the executor that enforces each contract.

A handler is a thin adapter: it loads DESK records, calls one deterministic DESK engine and returns
(outputs, blocking_issues, evidence_refs). It holds no engineering logic of its own.

The executor adds what Weft does not provide per node: input and output validation against the contract,
timeout, retry of retryable errors, idempotent replay of identical calls, and a DESK-side trace line that
links the Weft run to the DESK records it produced.

`passed` is the engineering verdict. A successful call (`ok`) with `passed: false` closes the gate downstream;
a graph that compiles, or a call that returns, never authorizes a design by itself.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

from desk.weft import INTEGRATION_VERSION
from desk.weft import contracts as C
from desk.weft.store import RecordStore, StoreError, canonical, sha256_text

Result = Tuple[Dict[str, Any], List[str], List[str]]          # outputs, blocking issues, evidence refs
APPROVAL_STAGES = ("profile", "bom", "schematic", "manufacturing", "exception")


class NodeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Context:
    """What a handler may touch: the project's record store and, for model nodes, a provider callable."""

    def __init__(self, store: RecordStore, run_id: str, provider: Optional[Callable[[str, str], Dict[str, Any]]] = None):
        self.store = store
        self.run_id = run_id
        self.provider = provider


# ---- handlers -----------------------------------------------------------------------------------------------

def _source(text: str) -> Any:
    """Requirements are free text, or a JSON object of structured fields (which DESK's extractor prefers:
    declared rails and current limits come only from structured input, never from a guess)."""
    stripped = text.lstrip()
    if stripped.startswith("{"):
        import json
        try:
            doc = json.loads(stripped)
            if isinstance(doc, dict):
                return doc
        except ValueError:
            pass
    return text


def _intake(ctx: Context, i: Dict[str, Any]) -> Result:
    text = i["requirements"]
    if not text.strip():
        return {"requirementsHash": "", "charCount": 0}, ["requirement text is empty"], []
    h = ctx.store.put_requirements(text)
    return {"requirementsHash": h, "charCount": len(text)}, [], [ctx.store.ref("requirements", h)]


def _validate_requirements(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.domain_intelligence import api
    from desk.domain_intelligence.classifier import extract_requirements
    text = ctx.store.get_requirements(i["requirementsHash"])
    req = extract_requirements(_source(text))
    names = sorted(k for k, v in req.features.items() if v not in (None, [], {}, "", False))
    missing = list(api.classify(_source(text)).missing_information)
    blocking = [] if names else ["no engineering feature could be extracted from the requirements"]
    return {"featureNames": names, "missingInformation": missing}, blocking, [ctx.store.ref("requirements", i["requirementsHash"])]


def _classify(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.domain_intelligence import api
    cls = api.classify(_source(ctx.store.get_requirements(i["requirementsHash"])))
    blocking = []
    if cls.classification_status != "CLASSIFIED":
        blocking.append(f"classification is {cls.classification_status}; a hardware engineer has to resolve it")
    blocking.extend(f"conflict: {c}" for c in cls.conflicts)
    out = {"primaryArchetype": cls.primary_archetype or "", "classificationStatus": cls.classification_status,
           "confidence": float(cls.confidence), "overlays": list(cls.required_overlays),
           "missingInformation": list(cls.missing_information)}
    return out, blocking, list(cls.evidence)


def _compile_profile(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.domain_intelligence import api
    from desk.domain_intelligence.profile_compiler import compile_profile
    cls = api.classify(_source(ctx.store.get_requirements(i["requirementsHash"])))
    if not cls.primary_archetype:
        return ({"profileHash": "", "profileStatus": "NOT_COMPILED", "enforcedRuleCount": 0, "advisoryRuleCount": 0},
                ["requirements are unclassified; no profile can be compiled"], [])
    compiled = compile_profile(cls, project_id=ctx.store.project_id).to_dict()
    profile_hash = str(compiled.get("design_profile", {}).get("profile_hash") or "")
    if not profile_hash:
        raise NodeError("ENGINE_ERROR", "compiled profile carries no profile_hash")
    ctx.store.put_profile(profile_hash, compiled, i["requirementsHash"])
    out = {"profileHash": profile_hash, "profileStatus": str(compiled.get("status", "")),
           "enforcedRuleCount": len(compiled.get("enforced_rule_ids", [])), "advisoryRuleCount": len(compiled.get("advisory_rule_ids", []))}
    return out, [str(b) for b in compiled.get("blocking_issues", [])], [ctx.store.ref("profiles", profile_hash)]


def _families(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.domain_intelligence import get_library
    compiled = ctx.store.get_profile(i["profileHash"])["compiled"]
    lib = get_library()
    known, unknown = [], []
    for fam in compiled.get("component_families", []):
        try:
            lib.family(fam)
            known.append(fam)
        except Exception:
            unknown.append(fam)
    blocking = [f"component family '{f}' is not in the DESK ontology" for f in unknown]
    return {"families": known, "unknownFamilies": unknown}, blocking, [ctx.store.ref("profiles", i["profileHash"])]


def _power(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk import ipc
    profile = ctx.store.get_profile(i["profileHash"])["compiled"].get("design_profile", {})
    limits = profile.get("current_limits_A") or {}
    report: Dict[str, Any] = {}
    blocking: List[str] = []
    for net, amps in sorted(limits.items()):
        try:
            report[net] = {"currentA": float(amps), "minWidthMil": ipc.trace_width_mil(float(amps)), "method": "IPC-2221 outer layer, 1 oz, 10 C rise"}
        except Exception as e:
            blocking.append(f"{net}: {e}")
    if not limits:
        blocking.append("the profile declares no current limit; DESK never sizes a trace for an unknown current")
    widest = max((r["minWidthMil"] for r in report.values()), default=0.0)
    return {"netCount": len(report), "widestTraceMil": float(widest), "report": report}, blocking, [ctx.store.ref("profiles", i["profileHash"])]


def _quality(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.quality import QualityGateEvaluator
    ctx.store.get_profile(i["profileHash"])
    ev = ctx.store.get_evidence(i["evidenceRef"])
    drc = ev.get("drc_violations")
    report = QualityGateEvaluator.evaluate(
        drc_violations=None if drc is None else [SimpleNamespace(error_type=str(v.get("error_type", "")), rule_name=str(v.get("rule_name", ""))) for v in drc],
        unconnected_nets=ev.get("unconnected_nets"),
        critical_nets=ev.get("critical_nets"),
        routability_score=float(ev.get("routability_score", 0.0)),
        discontinuities_count=ev.get("discontinuities_count"),
        board_revision=ev.get("board_revision"),
        evidence_revision=ev.get("evidence_revision"),
        profile_hash=i["profileHash"],
        evidence_profile_hash=ev.get("profile_hash"),
    ).to_dict()
    failures = [str(f) for f in report.get("failures", [])]
    approved = bool(report.get("approved"))
    blocking = failures if not approved else []
    if not approved and not blocking:
        blocking = ["quality gate not approved"]
    return ({"approved": approved, "totalScore": float(report.get("total_score", 0.0)), "failures": failures},
            blocking, [ctx.store.ref("evidence", i["evidenceRef"])])


def _approval(ctx: Context, i: Dict[str, Any]) -> Result:
    if i["stage"] not in APPROVAL_STAGES:
        raise NodeError("INVALID_INPUT", f"stage must be one of {', '.join(APPROVAL_STAGES)}")
    if i["decision"] not in ("approved", "rejected"):
        raise NodeError("INVALID_INPUT", "decision must be approved or rejected")
    if not i["subjectHash"]:
        raise NodeError("INVALID_INPUT", "an approval is bound to a subject hash")
    ref = ctx.store.put_approval(i["stage"], i["decision"], i["subjectHash"], ctx.run_id, i.get("note") or "")
    approved = i["decision"] == "approved"
    return ({"approvalRef": ref, "approved": approved}, [] if approved else [f"{i['stage']} was rejected by the approver"],
            [ctx.store.ref("approvals", ref)])


def _release_gate(ctx: Context, i: Dict[str, Any]) -> Result:
    try:
        approval = ctx.store.get_approval(i["approvalRef"])
    except StoreError:
        raise NodeError("APPROVAL_REQUIRED", "no recorded manufacturing approval with that reference")
    if approval.get("stage") != "manufacturing" or approval.get("decision") != "approved":
        raise NodeError("APPROVAL_REQUIRED", "the referenced record is not an approved manufacturing decision")
    if approval.get("subject_hash") != i["profileHash"]:
        raise NodeError("APPROVAL_REQUIRED", "the manufacturing approval was given for a different profile")
    out, blocking, evidence = _quality(ctx, {"profileHash": i["profileHash"], "evidenceRef": i["evidenceRef"]})
    allowed = bool(out["approved"])
    return ({"releaseAllowed": allowed, "approvalRef": i["approvalRef"]}, blocking,
            evidence + [ctx.store.ref("approvals", i["approvalRef"])])


_EXTRACT_SYSTEM = ("You restate hardware requirements as short structured notes. Answer with one JSON object with the keys "
                   "summary (string), open_questions (list of strings) and assumptions (list of strings). "
                   "Do not choose components and do not state electrical limits that the text does not give.")


def _extract(ctx: Context, i: Dict[str, Any]) -> Result:
    if ctx.provider is None:
        raise NodeError("PROVIDER_UNAVAILABLE", "no model provider is configured for the node service")
    text = ctx.store.get_requirements(i["requirementsHash"])
    # Scoped context: the model receives the fixed instruction and this one requirement text, nothing else.
    answer = ctx.provider(_EXTRACT_SYSTEM, text)
    if not isinstance(answer, dict) or answer.get("error"):
        raise NodeError("PROVIDER_UNAVAILABLE", str((answer or {}).get("error") or "provider gave no answer"))
    notes = answer.get("json")
    if not isinstance(notes, dict) or not isinstance(notes.get("summary"), str) \
            or not all(isinstance(notes.get(k, []), list) and all(isinstance(x, str) for x in notes.get(k, []))
                       for k in ("open_questions", "assumptions")):
        raise NodeError("PROVIDER_OUTPUT_INVALID", "model notes are not {summary, open_questions[], assumptions[]}")
    doc = {"requirements_hash": i["requirementsHash"], "advisory": True,
           "notes": {"summary": notes["summary"], "open_questions": notes.get("open_questions", []), "assumptions": notes.get("assumptions", [])},
           "provider": str(answer.get("provider", "")), "model": str(answer.get("model", ""))}
    ref = ctx.store.put_notes(doc)
    return {"notesRef": ref, "provider": doc["provider"], "model": doc["model"]}, [], [ctx.store.ref("notes", ref)]


def _failure_record(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.reliability.models import FailureRecord, FailureCategory, ExecutionState
    from desk.reliability.failure_classifier import classify_record
    try:
        cat = FailureCategory(i["category"])
    except ValueError:
        raise NodeError("INVALID_INPUT", f"unknown failure category {i['category']!r}")
    state = ExecutionState.UNKNOWN
    if i.get("executionState"):
        try:
            state = ExecutionState(i["executionState"])
        except ValueError:
            raise NodeError("INVALID_INPUT", f"unknown execution state {i['executionState']!r}")
    rec = FailureRecord.new(cat, i["module"], i["operation"], i["message"], execution_state=state, project_id=ctx.store.project_id,
                            document_uuid=str(i.get("documentUuid") or ""), window_id=str(i.get("windowId") or ""), run_id=ctx.run_id)
    for e in (i.get("evidence") or {}).get("items", []) or []:
        if isinstance(e, dict):
            rec.add_evidence(str(e.get("kind", "file")), str(e.get("source", "")), str(e.get("summary", "")))
    classify_record(rec)
    name = ctx.store.put_failure(rec.to_dict())
    return {"failureRef": name, "signature": rec.signature, "category": rec.category.value}, [], [ctx.store.ref("failures", name)]


def _diagnose(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.reliability.models import FailureRecord
    from desk.reliability.evidence import EvidenceCollector
    from desk.reliability import root_cause as RCA, registry as KF
    rec = FailureRecord.from_dict(ctx.store.get_failure(i["failureRef"]))
    facts = EvidenceCollector(project_path=ctx.store.project_dir).collect(rec)
    hyps = RCA.diagnose(rec, facts)
    rec.hypotheses = hyps
    rc = rec.root_cause
    rec.confidence = rc.confidence if rc else rec.confidence
    ctx.store.put_failure(rec.to_dict())
    blocking = [] if rc and rc.confidence.value in ("CONFIRMED", "STRONGLY_SUPPORTED") else ["root cause not confirmed by a deterministic rule"]
    return ({"rootCauseCategory": rc.category.value if rc else "", "confidence": rc.confidence.value if rc else "UNVERIFIED",
             "statement": rc.statement if rc else "", "knownFailures": [k.id for k in KF.match(rec)],
             "missingEvidence": list(rc.missing_evidence) if rc else [], "hypothesisCount": len(hyps)},
            blocking, [ctx.store.ref("failures", i["failureRef"])])


def _plan(ctx: Context, i: Dict[str, Any]) -> Result:
    from desk.reliability.models import FailureRecord
    from desk.reliability.evidence import EvidenceCollector
    from desk.reliability import recovery_planner as RP, registry as KF
    from desk.reliability.recovery_policy import RecoveryPolicy
    rec = FailureRecord.from_dict(ctx.store.get_failure(i["failureRef"]))
    facts = EvidenceCollector(project_path=ctx.store.project_dir).collect(rec)
    plan = RP.plan(rec, facts, RecoveryPolicy(), KF.match(rec), facts.get("signature", ""))
    rec.plan = plan
    ctx.store.put_failure(rec.to_dict())
    ref = ctx.store.put_plan(i["failureRef"], plan.to_dict())
    blocking = ["plan needs a Captain approval"] if plan.requires_approval else []
    return ({"planRef": ref, "actionKinds": [a.kind for a in plan.actions], "requiresApproval": plan.requires_approval,
             "refused": list(plan.refused), "verificationCriteria": list(plan.verification_criteria)},
            blocking, [ctx.store.ref("plans", ref)])


def _checkpoint_status(ctx: Context, i: Dict[str, Any]) -> Result:
    import json as _json
    import os as _os
    wd = _os.path.join(ctx.store.project_dir, "state", "route")
    pc_path = _os.path.join(wd, "progress_chunks.json")
    pc: Dict[str, Any] = {}
    if _os.path.exists(pc_path):
        with open(pc_path, encoding="utf-8") as f:
            pc = _json.load(f)
    ck = pc.get("checkpoint") or {}
    rf_path = _os.path.join(wd, "route_failure.json")
    cat = ""
    if _os.path.exists(rf_path):
        with open(rf_path, encoding="utf-8") as f:
            cat = str(_json.load(f).get("category") or "")
    best = ck.get("best_unrouted")
    return ({"hasBest": bool(ck.get("has_best")), "bestUnrouted": int(best) if best is not None else -1,
             "chunkOutcomes": [str(o) for o in pc.get("outcomes", [])], "engineVersion": str(ck.get("engine_version") or ""),
             "failureCategory": cat},
            ["no routing checkpoint"] if not ck.get("has_best") else [],
            [p for p in ("state/route/progress_chunks.json", "state/route/route_failure.json") if _os.path.exists(_os.path.join(ctx.store.project_dir, p))])


HANDLERS: Dict[str, Callable[[Context, Dict[str, Any]], Result]] = {
    "DeskFailureRecorder": _failure_record,
    "DeskFailureDiagnoser": _diagnose,
    "DeskRecoveryPlanner": _plan,
    "DeskRoutingCheckpointStatus": _checkpoint_status,
    "DeskRequirementIntake": _intake,
    "DeskRequirementValidator": _validate_requirements,
    "DeskDomainClassifier": _classify,
    "DeskDesignProfileCompiler": _compile_profile,
    "DeskComponentFamilyResolver": _families,
    "DeskPowerDistributionAnalyzer": _power,
    "DeskQualityGate": _quality,
    "DeskApprovalRecorder": _approval,
    "DeskReleaseGate": _release_gate,
    "DeskRequirementExtractor": _extract,
}

HTTP_STATUS = {"INVALID_INPUT": 400, "UNAUTHORIZED": 401, "APPROVAL_REQUIRED": 403, "MUTATION_NOT_AUTHORIZED": 403,
               "UNKNOWN_NODE": 404, "PROJECT_NOT_FOUND": 404, "RECORD_NOT_FOUND": 404, "NODE_UNAVAILABLE": 501,
               "PROVIDER_UNAVAILABLE": 503, "PROVIDER_OUTPUT_INVALID": 502, "TIMEOUT": 504, "ENGINE_ERROR": 500}


def error_envelope(node_id: str, version: str, code: str, message: str, provenance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"node": node_id, "version": version, "ok": False,
            "error": {"code": code, "message": message, "retryable": code in C.RETRYABLE},
            "provenance": provenance or {}}


def _run_with_timeout(fn: Callable[[], Result], timeout_s: float) -> Result:
    box: Dict[str, Any] = {}

    def target() -> None:
        try:
            box["result"] = fn()
        except BaseException as e:   # carried to the caller thread
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise NodeError("TIMEOUT", f"engine did not finish in {timeout_s:g} s")
    if "error" in box:
        raise box["error"]
    return box["result"]


def execute(node_id: str, payload: Any, projects_root: Optional[str] = None,
            provider: Optional[Callable[[str, str], Dict[str, Any]]] = None,
            sleep: Callable[[float], None] = time.sleep) -> Tuple[int, Dict[str, Any]]:
    """Run one node call. Returns (http_status, envelope). Never raises."""
    contract = C.get(node_id)
    if contract is None:
        return 404, error_envelope(node_id, "", "UNKNOWN_NODE", f"no DESK node '{node_id}'")
    v = contract.version

    def fail(code: str, message: str, prov: Optional[Dict[str, Any]] = None, store: Optional[RecordStore] = None,
             run_id: str = "") -> Tuple[int, Dict[str, Any]]:
        env = error_envelope(node_id, v, code, message, prov)
        if store is not None:
            store.trace(run_id, {"at": time.time(), "node": node_id, "version": v, "ok": False, "passed": False, "error": code,
                                 "inputHash": (prov or {}).get("inputHash", "")})
        return HTTP_STATUS.get(code, 500), env

    problems = contract.validate_inputs(payload)
    if problems:
        return fail("INVALID_INPUT", "; ".join(problems))
    run_id = payload.get("runId", "")
    try:
        store = RecordStore(payload["projectId"], projects_root)
    except StoreError as e:
        return fail(e.code, e.message)

    identity = {k: val for k, val in payload.items() if k != "runId"}
    input_hash = sha256_text(canonical(identity))
    key = sha256_text(canonical([node_id, v, input_hash]))
    prov = {"engine": contract.engine, "inputHash": input_hash, "idempotencyKey": key, "replayed": False, "attempts": 0,
            "deskWeftIntegration": INTEGRATION_VERSION}

    if contract.status != "available":
        return fail("NODE_UNAVAILABLE", contract.unavailable_reason, prov, store, run_id)
    if contract.mutation:
        return fail("MUTATION_NOT_AUTHORIZED", "live design mutation is not available through the node service", prov, store, run_id)

    if contract.idempotency == "input_hash":
        stored = store.get_result(key)
        if stored is not None:
            stored = dict(stored)
            stored["provenance"] = dict(stored.get("provenance", {}), replayed=True)
            store.trace(run_id, {"at": time.time(), "node": node_id, "version": v, "ok": True, "passed": stored.get("passed", False),
                                 "inputHash": input_hash, "replayed": True, "evidence": stored.get("evidence", [])})
            return 200, stored

    handler = HANDLERS[node_id]
    ctx = Context(store, run_id, provider)
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        prov["attempts"] = attempt
        try:
            outputs, blocking, evidence = _run_with_timeout(lambda: handler(ctx, payload), contract.timeout_s)
            break
        except (NodeError, StoreError) as e:
            if e.code in C.RETRYABLE and attempt < contract.max_attempts:
                sleep(min(2.0 * attempt, 10.0))
                continue
            return fail(e.code, e.message, prov, store, run_id)
        except Exception as e:
            return fail("ENGINE_ERROR", f"{type(e).__name__}: {e}", prov, store, run_id)

    bad = contract.validate_outputs(outputs)
    if bad:
        return fail("ENGINE_ERROR", "adapter broke its contract: " + "; ".join(bad), prov, store, run_id)
    prov["durationMs"] = round((time.time() - started) * 1000.0, 2)
    envelope = {"node": node_id, "version": v, "ok": True, "passed": not blocking, "outputs": outputs,
                "blockingIssues": [str(b) for b in blocking], "evidence": [str(e) for e in evidence], "provenance": prov}
    if contract.idempotency == "input_hash":
        store.put_result(key, envelope)
    store.trace(run_id, {"at": time.time(), "node": node_id, "version": v, "ok": True, "passed": envelope["passed"],
                         "inputHash": input_hash, "replayed": False, "evidence": envelope["evidence"],
                         "blocking": envelope["blockingIssues"], "durationMs": prov["durationMs"]})
    return 200, envelope


def desk_provider(timeout_s: float = 110.0) -> Optional[Callable[[str, str], Dict[str, Any]]]:
    """The model provider for model nodes: DESK's existing OpenAI-compatible adapter (NVIDIA NIM by default).

    Returns None when no credential is configured, so a model node reports PROVIDER_UNAVAILABLE instead of guessing.
    """
    import json
    import os
    try:
        from desk.orchestrator.http_adapter import OpenAICompatAdapter
    except Exception:
        return None
    if not (os.environ.get("NVIDIA_API_KEY") or os.environ.get(os.environ.get("DESK_HTTP_API_KEY_ENV", "") or "_")):
        return None
    adapter = OpenAICompatAdapter()
    model = os.environ.get("DESK_WEFT_MODEL") or os.environ.get("DESK_AGENT_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b"

    def call(system: str, user: str) -> Dict[str, Any]:
        r = adapter.chat_completion([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                    model=model, thinking="off", timeout=timeout_s, temperature=0.0)
        if r.get("error"):
            return {"error": str(r["error"])}
        text = (r.get("message") or {}).get("content") or ""
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            return {"json": json.loads(text[start:end]), "provider": "nvidia", "model": model}
        except ValueError:
            return {"json": None, "provider": "nvidia", "model": model}

    return call
