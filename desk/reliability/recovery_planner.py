"""Recovery planning: failure category + evidence + known failures -> an ordered, policy-classified plan.

The planner proposes; the policy classifies (AUTO / APPROVAL / REFUSE); the executor runs; the verifier decides. A
plan never contains an action the policy refuses, and never repeats an action that already failed for the same
failure with unchanged evidence. Routing proposals name the concrete change (nets, pads, hotspots) from the evidence
packet so the Captain can judge them.

Zero external dependencies.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from desk.reliability.models import (ExecutionState as X, FailureCategory as C, FailureRecord, RecoveryAction, RecoveryPlan,
                                     RiskClass, new_id)
from desk.reliability.recovery_policy import RecoveryPolicy, risk_for
from desk.reliability.registry import KnownFailure


def _act(kind: str, description: str, policy: RecoveryPolicy, expected: str = "", verification: str = "",
         idempotent: bool = True, **params: Any) -> RecoveryAction:
    return RecoveryAction(id=new_id("RA"), kind=kind, description=description, risk=risk_for(kind, policy._auto()),
                          idempotent=idempotent, params=params, expected_effect=expected, verification=verification)


def _api_actions(rec: FailureRecord, facts: Dict[str, Any], policy: RecoveryPolicy) -> List[RecoveryAction]:
    cat, state = rec.category, rec.execution_state
    acts: List[RecoveryAction] = []
    if cat in (C.WINDOW_ID_ROTATED, C.WINDOW_DISCONNECTED):
        acts.append(_act("rebind_session", "Rediscover the window that hosts the project uuid and rebind (exactly one match)", policy,
                         expected="session bound to a connected window of the same project",
                         verification="getCurrentProjectInfo().uuid == project uuid and active document == bound document"))
        acts.append(_act("verify_identity", "Read the active document uuid in the rebound window", policy,
                         expected="EXPECTED DOCUMENT UUID == ACTUAL", verification="document_uuid readback"))
        if state in (X.EXECUTED_RESPONSE_LOST, X.UNKNOWN, X.PARTIAL):
            acts.append(_act("reconcile_readback", "Read the document and compare with the intended postcondition before any retry", policy,
                             expected="state known: complete, absent or partial", verification="verification contract of the operation"))
    elif cat == C.WRONG_PROJECT_CONTEXT:
        acts.append(_act("bind_project", "Bind the project to the unique window hosting its uuid (tools/rebind.py)", policy,
                         expected="mutations carry a verified windowId", verification="project uuid readback in the bound window"))
        acts.append(_act("escalate", "If two windows host the same project, the Captain closes one or names the window", policy))
    elif cat == C.DOCUMENT_CONTEXT_LOST:
        acts.append(_act("verify_identity", "Open the bound document in the bound window, then re-read the active uuid", policy,
                         expected="bound document active", verification="document_uuid readback"))
    elif cat == C.API_FALSE_SUCCESS:
        if facts.get("dialog_method"):
            acts.append(_act("human_apply_then_readback", f"{facts['dialog_method']} opened a dialog: the Captain applies it, then DESK reads back",
                             policy, expected="postcondition visible on readback", verification=rec.params.get("verifier", "readback")))
        else:
            acts.append(_act("reconcile_readback", "Poll the document until stable and compare against the postcondition", policy,
                             expected="either the change appears (stale readback) or it is absent (false success)",
                             verification=rec.params.get("verifier", "readback")))
            acts.append(_act("escalate", "A false success with a VERIFIED method is new evidence: record the incident, do not repeat", policy))
    elif cat in (C.UNKNOWN_MUTATION_OUTCOME, C.PARTIAL_MUTATION):
        acts.append(_act("poll_until_stable", "Wait for the gateway script to finish (it keeps running after the 120 s cap)", policy,
                         expected="document state stops changing", verification="two identical fingerprints 2 s apart"))
        acts.append(_act("reconcile_readback", "Compare the document with the intended postcondition", policy,
                         expected="complete / absent / partial known", verification="operation verification contract"))
        acts.append(_act("resume_from_verified_state", "Apply only the missing part of the mutation from the verified state", policy,
                         idempotent=False, expected="postcondition met without duplicating applied parts", verification="operation verification contract"))
    elif cat in (C.TRANSIENT_NETWORK, C.API_TIMEOUT, C.API_UNAVAILABLE):
        if state in (X.NOT_EXECUTED, X.GATEWAY_NOT_EXECUTED) or not facts.get("mutating"):
            acts.append(_act("retry_read", "Bounded retry with exponential backoff and jitter (reads / not-executed requests only)", policy,
                             expected="a response", verification="response received"))
        acts.append(_act("reconnect_gateway", "Re-probe the gateway port and rebuild the session", policy,
                         expected="/eda-windows answers", verification="window list non-empty"))
        if state in (X.EXECUTED_RESPONSE_LOST, X.UNKNOWN):
            acts.append(_act("reconcile_readback", "The request may have executed: read back before anything else", policy))
    elif cat == C.LOCK_CONFLICT:
        acts.append(_act("wait_for_lock", "Wait for the other writer (bounded)", policy, expected="lock released"))
        acts.append(_act("reclaim_stale_lock", "Reclaim only when the holder PID is dead or the TTL elapsed", policy,
                         expected="lock reclaimed without a live holder", verification="holder pid not alive"))
    elif cat == C.CONCURRENT_WRITE_CONFLICT:
        acts.append(_act("escalate", "Two writers targeted one document; the Captain decides which state is authoritative", policy))
    elif cat == C.API_SCHEMA_MISMATCH:
        acts.append(_act("collect_more_evidence", "Record the method, parameters and response shape; mark the capability EXPERIMENTAL", policy))
        acts.append(_act("escalate", "An API method behaved differently from the registry; no automatic workaround", policy))
    return acts


def _router_actions(rec: FailureRecord, facts: Dict[str, Any], policy: RecoveryPolicy) -> List[RecoveryAction]:
    cat = rec.category
    acts: List[RecoveryAction] = []
    ckpt = facts.get("checkpoint") or {}
    if cat == C.JAVA_RUNTIME_INCOMPATIBLE:
        acts.append(_act("use_bundled_jdk", "Run the engine with library/tools/jdk25 (Freerouting >= 2.2 needs Java 25)", policy,
                         expected="engine starts", verification="smoke run writes a SES"))
        acts.append(_act("select_compatible_engine", "Pick the newest JAR whose class version the JVM accepts", policy))
    elif cat == C.EXTERNAL_TOOL_UNSUPPORTED:
        acts.append(_act("switch_engine_version", "Use an engine whose profile honours max_passes (Freerouting 2.5 + JDK 25)", policy,
                         expected="chunks end by themselves with a SES", verification="first chunk writes a valid SES"))
        acts.append(_act("select_compatible_engine", "Resolve FREEROUTING_JAR / DESK_JAVA to existing files", policy))
    elif cat == C.ROUTER_ENGINE_TIMEOUT:
        acts.append(_act("adaptive_chunk", "Re-plan the chunk from the measured pass time (one pass with a long enough window)", policy,
                         expected="a chunk completes and writes a SES", verification="checkpoint accepts a valid SES"))
        if ckpt.get("has_best"):
            acts.append(_act("resume_from_checkpoint", f"Continue from the checkpoint ({ckpt.get('best_unrouted')} unrouted)", policy,
                             expected="fewer unrouted connections", verification="checkpoint best_unrouted decreases"))
        acts.append(_act("extend_budget", "Raise the mode budget for this board (Captain decides the time)", policy))
    elif cat == C.ROUTER_STAGNATION:
        if ckpt.get("has_best"):
            acts.append(_act("resume_from_checkpoint", "Continue from the best SES with a different priority order", policy))
        acts.append(_act("adjust_routing_priority", "Route the problem nets first (priority_net_classes from the engine's problem nets)", policy,
                         nets=facts.get("problem_nets", [])[:10]))
        acts.append(_act("adjust_via_cost", "Lower via cost when more than two signal layers are routable", policy))
        for h in (facts.get("hotspots") or [])[:5]:
            strat = h.get("recommended_strategy", "")
            kind = {"POWER_TO_POLYGON": "power_to_polygon", "PLACEMENT_REFINE_THEN_ROUTE": "placement_refine",
                    "CORRIDOR_RESERVE_LAYER_SPLIT": "corridor_reserve", "ESCAPE_FIRST": "add_escape_vias"}.get(strat)
            if kind:
                acts.append(_act(kind, f"{strat} at {h.get('region_id')} {h.get('bbox_mm')} mm: {', '.join(h.get('causes', []))}", policy,
                                 region=h.get("region_id"), bbox_mm=h.get("bbox_mm")))
        acts.append(_act("ripup_routes", "Selective rip-up of the tracks blocking the unrouted nets (state/recovery_plan.json)", policy))
    elif cat in (C.ROUTER_NO_LEGAL_ESCAPE, C.ROUTER_RULE_CONFLICT):
        for d in (facts.get("decisions") or [])[:5]:
            acts.append(_act("engineering_decision", f"{d.get('decision_id')}: net {d.get('net')} rule {d.get('rule_mm')} mm > pin-field gap "
                                                     f"{d.get('pin_field_mm')} mm; options: " + " | ".join(d.get("options", [])[:2]), policy,
                             decision_id=d.get("decision_id")))
        if not facts.get("decisions"):
            acts.append(_act("placement_refine", "Move the blocked pads' neighbours or fix keep-outs (feasibility.json names them)", policy))
        if any((b.get("classification") == "BLOCKED_BY_KEEP_OUT") for b in (facts.get("blocked_pads") or []) if isinstance(b, dict)):
            acts.append(_act("fix_route_keepouts", "Remove routing keep-outs that cover pads", policy))
    elif cat in (C.ROUTER_SES_MISSING, C.ROUTER_SES_INVALID):
        acts.append(_act("adaptive_chunk", "Run a one-pass chunk to measure whether this engine writes a SES at all", policy))
        acts.append(_act("switch_engine_version", "Use an engine profile known to write a SES at max_passes", policy))
    elif cat == C.ROUTER_ENGINE_CRASH:
        if facts.get("pours_in_dsn"):
            acts.append(_act("reexport_dsn_without_pours", "Remove copper pours before export (they become pseudo-pins) and re-export", policy,
                             expected="engine loads the DSN and completes pass 1"))
        acts.append(_act("collect_more_evidence", "Keep the engine log of the crashed chunk with the DSN hash", policy))
        acts.append(_act("escalate", "Engine exception without a known signature", policy))
    elif cat == C.ROUTER_RESOURCE_EXHAUSTION:
        acts.append(_act("adaptive_chunk", "Smaller chunks and max_threads=1 to bound memory", policy))
        acts.append(_act("escalate", "The board exceeds the host's memory for this engine", policy))
    elif cat == C.DESIGN_PROFILE_INVALID:
        acts.append(_act("escalate", f"Fix design_profile.json: {rec.params.get('key') or rec.message[:120]}", policy))
    elif cat in (C.CONNECTIVITY_VERIFICATION_FAILURE, C.DRC_FAILURE, C.ERC_FAILURE):
        acts.append(_act("ripup_routes", "Targeted rip-up and reroute of the failing nets", policy))
        acts.append(_act("escalate", "Gates stay failed until independently re-verified", policy))
    elif cat == C.REQUIREMENT_CONFLICT:
        acts.append(_act("escalate", "A human decision (approval, spacing, requirement) is outstanding", policy))
    return acts


def _applicable(kind: str, facts: Dict[str, Any]) -> bool:
    """Preconditions for actions a known failure suggests: a resume needs a checkpoint, a pour re-export needs pours."""
    if kind == "resume_from_checkpoint":
        return bool((facts.get("checkpoint") or {}).get("has_best"))
    if kind == "reexport_dsn_without_pours":
        return bool(facts.get("pours_in_dsn"))
    if kind == "human_apply_then_readback":
        return bool(facts.get("dialog_method")) or facts.get("category") == "API_FALSE_SUCCESS"
    return True


def plan(rec: FailureRecord, facts: Dict[str, Any], policy: RecoveryPolicy, known: Sequence[KnownFailure] = (),
         evidence_signature: str = "", approvals: Sequence[str] = ()) -> RecoveryPlan:
    acts = _api_actions(rec, facts, policy) + _router_actions(rec, facts, policy)
    for kf in known:
        for kind in kf.recovery_kinds:
            if kind not in {a.kind for a in acts} and risk_for(kind, policy._auto()) != RiskClass.REFUSE and _applicable(kind, facts):
                acts.append(_act(kind, f"{kf.id}: {kf.title} -> {kind}", policy))
    if not acts:
        acts.append(_act("collect_more_evidence", "No deterministic rule matched: gather the diagnostic packet for the model", policy))
        acts.append(_act("escalate", "Unknown failure: human review", policy))
    kept: List[RecoveryAction] = []
    refused: List[str] = []
    for a in acts:
        d = policy.decide(rec.failure_id, a, evidence_signature, approvals)
        if d.risk == RiskClass.REFUSE or (not d.allowed and not d.needs_approval):
            refused.append(f"{a.kind}: {d.reason}")
            continue
        kept.append(a)
    requires_approval = any(a.risk == RiskClass.APPROVAL for a in kept)
    verification = [a.verification for a in kept if a.verification] or ["independent readback of the target state"]
    rationale = f"{rec.category.value} ({rec.execution_state.value}); known: {', '.join(k.id for k in known) or 'none'}"
    return RecoveryPlan(failure_id=rec.failure_id, actions=kept, rationale=rationale, requires_approval=requires_approval,
                        verification_criteria=verification, refused=refused)
