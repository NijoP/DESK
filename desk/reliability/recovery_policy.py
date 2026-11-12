"""Risk-based recovery policy: what the self-healing layer may do by itself, what needs the Captain, what it never does.

AUTO      reconnect a read-only session, rebind a rotated window after verifying the project identity, retry a
          transient read, restart an isolated helper, recreate a disposable routing workspace, resume from a validated
          SES checkpoint, re-plan a chunk, select a compatible engine / bundled JDK, reconcile by readback.
APPROVAL  change clearance / creepage / voltage / current assumptions, move critical components, modify the switching
          loop, delete tracks or copper, change the stackup, override DRC / ERC, modify customer requirements, repeat a
          non-idempotent mutation whose outcome is uncertain, pour power polygons, rip up routes.
REFUSE    bypass a quality gate, weaken a safety rule automatically, mutate another project, mark a failed manufacturing
          gate as passed, anything the registry does not know.

Attempt limits: at most `max_attempts` recoveries per failure, and the same action is not proposed twice for the same
failure while the evidence signature is unchanged (UPS_1000: six engine runs with the same configuration).
DESK_RELIABILITY_AUTORECOVER=0 demotes every AUTO action to APPROVAL (proposal only).

Zero external dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from desk.reliability.models import RecoveryAction, RiskClass

AUTO_KINDS = {
    "rebind_session", "verify_identity", "bind_project", "retry_read", "reconnect_gateway", "restart_helper_process",
    "recreate_temp_workspace", "resume_from_checkpoint", "adaptive_chunk", "select_compatible_engine", "use_bundled_jdk",
    "switch_engine_version", "reconcile_readback", "poll_until_stable", "wait_for_lock", "reclaim_stale_lock",
    "reexport_dsn_without_pours", "adjust_routing_priority", "adjust_via_cost", "open_circuit_breaker", "collect_more_evidence",
    "declare_planes", "fix_route_keepouts",
}
APPROVAL_KINDS = {
    "change_spacing_rule", "change_creepage_assumption", "change_voltage_or_current_limits", "move_critical_components",
    "modify_switching_loop", "delete_tracks_or_copper", "ripup_routes", "change_stackup", "override_drc_erc", "modify_requirements",
    "repeat_uncertain_mutation", "resume_from_verified_state", "power_to_polygon", "placement_refine", "corridor_reserve",
    "add_escape_vias", "change_layer_assignment", "adjust_trace_width", "engineering_decision", "human_apply_then_readback",
    "detach_net_then_delete", "recreate_pour", "fix_outline", "extend_budget", "escalate",
}
REFUSE_KINDS = {"bypass_quality_gate", "weaken_safety_rule", "mutate_other_project", "force_release", "mark_gate_passed"}

SAFETY_RELATED = {"change_spacing_rule", "change_creepage_assumption", "change_voltage_or_current_limits", "override_drc_erc",
                  "change_stackup", "modify_requirements"}


def risk_for(kind: str, autorecover: bool = True) -> RiskClass:
    if kind in REFUSE_KINDS:
        return RiskClass.REFUSE
    if kind in APPROVAL_KINDS:
        return RiskClass.APPROVAL
    if kind in AUTO_KINDS:
        return RiskClass.AUTO if autorecover else RiskClass.APPROVAL
    return RiskClass.REFUSE     # unknown actions are never performed


@dataclass
class PolicyDecision:
    allowed: bool
    risk: RiskClass
    reason: str
    needs_approval: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {"allowed": self.allowed, "risk": self.risk.value, "reason": self.reason, "needs_approval": self.needs_approval}


@dataclass
class RecoveryPolicy:
    max_attempts: int = 3
    autorecover: Optional[bool] = None            # None -> read DESK_RELIABILITY_AUTORECOVER
    attempts: Dict[str, int] = field(default_factory=dict)           # failure_id -> executed attempts
    seen: Dict[str, set] = field(default_factory=dict)               # failure_id -> {(kind, evidence_signature)}

    def _auto(self) -> bool:
        if self.autorecover is not None:
            return self.autorecover
        try:
            from desk import config as deskcfg
            return deskcfg.get_bool("DESK_RELIABILITY_AUTORECOVER", True)
        except Exception:
            return True

    def classify(self, action: RecoveryAction) -> RiskClass:
        return risk_for(action.kind, self._auto())

    def decide(self, failure_id: str, action: RecoveryAction, evidence_signature: str,
               approvals: Iterable[str] = ()) -> PolicyDecision:
        """May `action` run now for `failure_id`? `approvals` are approval ids / tokens recorded for this failure."""
        risk = self.classify(action)
        if risk == RiskClass.REFUSE:
            return PolicyDecision(False, risk, f"{action.kind} is never performed by the self-healing layer")
        if self.attempts.get(failure_id, 0) >= self.max_attempts:
            return PolicyDecision(False, risk, f"recovery attempts exhausted ({self.max_attempts}); escalate to the Captain")
        key = (action.kind, evidence_signature)
        if key in self.seen.get(failure_id, set()):
            return PolicyDecision(False, risk, f"{action.kind} was already tried for this failure with unchanged evidence; "
                                               "new evidence is required before it is proposed again")
        if risk == RiskClass.APPROVAL:
            ok = bool(approvals) and any(a for a in approvals)
            return PolicyDecision(ok, risk, "approved" if ok else f"{action.kind} needs a recorded Captain approval",
                                  needs_approval=not ok)
        return PolicyDecision(True, risk, "automatic recovery allowed")

    def record_attempt(self, failure_id: str, action: RecoveryAction, evidence_signature: str) -> None:
        self.attempts[failure_id] = self.attempts.get(failure_id, 0) + 1
        self.seen.setdefault(failure_id, set()).add((action.kind, evidence_signature))

    def remaining(self, failure_id: str) -> int:
        return max(0, self.max_attempts - self.attempts.get(failure_id, 0))
