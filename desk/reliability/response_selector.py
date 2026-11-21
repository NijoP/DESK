"""Deterministic recovery-response selector (study report section 7.4): which of the seven responses DESK takes next.

    1 RETRY_SAME            operational, idempotent, known not executed (or a transient the RetryPolicy retries)
    2 CHANGE_STRATEGY       router stagnation / timeout / missing SES / engine issues
    3 RECALCULATE           the root cause is a calculated value; a deterministic engine recomputes it
    4 ALTERNATIVE_PARTS     DFM / footprint unsuitability, part unavailable (execution needs engineer approval)
    5 RETURN_UPSTREAM       the root cause sits in an earlier stage (opens a child task; at most 2 hops)
    6 REQUEST_CLARIFICATION the requirement itself is contradictory or missing (task BLOCKED)
    7 REQUEST_APPROVAL      APPROVAL-class action, unknown cause, or the ladder is exhausted (terminal for automation)

The table is DESK's; a model may only re-rank the candidates the table allows (`ranking`), never add one.
The ladder is monotone (rank 1 -> 2 -> 3/4/5 -> 6/7) and a response never repeats for the same (task, evidence
signature). The same signature twice escalates (no blind retry). Hard caps: `max_executions` (2, AGENTS.md section F)
non-terminal responses per task and `max_hops` (2) back-edges, so any failure sequence reaches 6 or 7 within
max_executions + 1 selections. The ladder state is persisted as `recovery` events on the task record (desk/tasks.py).

Zero external dependencies.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from desk.reliability.models import ExecutionState as X, FailureCategory as C
from desk.reliability.retry_policy import RETRYABLE_CATEGORIES, SAFE_STATES


class Response(str, enum.Enum):
    RETRY_SAME = "RETRY_SAME"
    CHANGE_STRATEGY = "CHANGE_STRATEGY"
    RECALCULATE = "RECALCULATE"
    ALTERNATIVE_PARTS = "ALTERNATIVE_PARTS"
    RETURN_UPSTREAM = "RETURN_UPSTREAM"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"


RANK = {Response.RETRY_SAME: 0, Response.CHANGE_STRATEGY: 1, Response.RECALCULATE: 2, Response.ALTERNATIVE_PARTS: 2,
        Response.RETURN_UPSTREAM: 2, Response.REQUEST_CLARIFICATION: 3, Response.REQUEST_APPROVAL: 3}
TERMINAL = {Response.REQUEST_CLARIFICATION, Response.REQUEST_APPROVAL}
NEEDS_APPROVAL = {Response.ALTERNATIVE_PARTS, Response.REQUEST_APPROVAL}

STRATEGY_CATEGORIES = {C.ROUTER_STAGNATION, C.ROUTER_ENGINE_TIMEOUT, C.ROUTER_SES_MISSING, C.ROUTER_SES_INVALID,
                       C.ROUTER_ENGINE_CRASH, C.ROUTER_RESOURCE_EXHAUSTION, C.EXTERNAL_TOOL_UNSUPPORTED,
                       C.JAVA_RUNTIME_INCOMPATIBLE, C.RESOURCE_LIMIT}
# root-cause kinds an engine or validator established (never a model alone) -> the mid-ladder response
CAUSE_RESPONSE = {"calculated_value": Response.RECALCULATE, "component": Response.ALTERNATIVE_PARTS,
                  "upstream": Response.RETURN_UPSTREAM}


@dataclass(frozen=True)
class FailureContext:
    category: C
    signature: str                                  # evidence signature of this failure
    execution_state: X = X.UNKNOWN
    layer: str = "ENGINEERING"                      # OPERATIONAL | ENGINEERING
    idempotent: bool = False
    root_cause_kinds: Tuple[str, ...] = ()          # subset of CAUSE_RESPONSE keys, or ("requirement",)
    approval_class: bool = False                    # the fix is an APPROVAL-class action (spacing, stackup, DRC override...)

    @property
    def requirement_issue(self) -> bool:
        return self.category == C.REQUIREMENT_CONFLICT or "requirement" in self.root_cause_kinds


@dataclass
class LadderState:
    max_executions: int = 2
    max_hops: int = 2
    executions: int = 0
    hops: int = 0
    rank: int = 0
    used: Set[Tuple[str, str]] = field(default_factory=set)        # (response, signature)
    last_signature: Optional[str] = None
    terminal: Optional[Response] = None

    @classmethod
    def from_events(cls, events: Iterable[Dict[str, Any]], max_executions: int = 2, max_hops: int = 2) -> "LadderState":
        s = cls(max_executions=max_executions, max_hops=max_hops)
        for e in events:
            try:
                s.record(Response(e["response"]), str(e.get("signature") or ""))
            except (KeyError, ValueError, TypeError):
                continue
        return s

    def record(self, response: Response, signature: str) -> None:
        """Account for a selected response (DESK computes this; nothing else writes the ladder)."""
        self.rank = max(self.rank, RANK[response])
        self.last_signature = signature
        if response in TERMINAL:
            self.terminal = response
            return
        self.executions += 1
        self.used.add((response.value, signature))
        if response == Response.RETURN_UPSTREAM:
            self.hops += 1


def table(ctx: FailureContext) -> List[Response]:
    """The deterministic table: the responses this failure allows, in table order."""
    if ctx.requirement_issue:
        return [Response.REQUEST_CLARIFICATION]
    if ctx.approval_class:
        return [Response.REQUEST_APPROVAL]
    mids = [CAUSE_RESPONSE[k] for k in ("calculated_value", "component", "upstream") if k in ctx.root_cause_kinds]
    if mids:
        return mids
    safe = ctx.execution_state in SAFE_STATES
    if ctx.layer == "OPERATIONAL" and safe and (ctx.idempotent or ctx.category in RETRYABLE_CATEGORIES):
        return [Response.RETRY_SAME]
    if ctx.category in STRATEGY_CATEGORIES:
        return [Response.CHANGE_STRATEGY]
    return [Response.REQUEST_APPROVAL]          # DRC / ERC / connectivity without an established cause, or unknown


def candidates(ctx: FailureContext, state: LadderState) -> List[Response]:
    """Responses allowed now, after the ladder rules; never empty."""
    escalate = Response.REQUEST_CLARIFICATION if ctx.requirement_issue else Response.REQUEST_APPROVAL
    if state.terminal is not None:
        return [state.terminal]
    if state.executions >= state.max_executions or (state.last_signature is not None and ctx.signature == state.last_signature):
        return [escalate]                        # budget spent, or the same signature twice: no blind retry
    out = []
    for r in table(ctx):
        if r not in TERMINAL:
            if RANK[r] < state.rank or (r.value, ctx.signature) in state.used:
                continue                         # monotone; never the same response for the same signature
            if r == Response.RETURN_UPSTREAM and state.hops >= state.max_hops:
                continue
        out.append(r)
    return out or [escalate]


def select(ctx: FailureContext, state: LadderState, ranking: Optional[Sequence[str]] = None) -> Response:
    """Deterministic choice; `ranking` (e.g. from a model) only orders the allowed candidates."""
    allowed = candidates(ctx, state)
    for name in ranking or ():
        for r in allowed:
            if r.value == name:
                return r
    return allowed[0]


def select_for_task(store: Any, task_id: str, ctx: FailureContext, ranking: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Rebuild the ladder from the task's persisted recovery events, select, and persist the step."""
    rec = store.get(task_id)
    state = LadderState.from_events(rec.get("recovery", []), max_executions=int(rec["attempts"].get("max") or 2))
    r = select(ctx, state, ranking)
    state.record(r, ctx.signature)
    store.append(task_id, "recovery", response=r.value, signature=ctx.signature, rank=RANK[r], terminal=r in TERMINAL,
                 needs_approval=r in NEEDS_APPROVAL, category=ctx.category.value)
    if r == Response.REQUEST_CLARIFICATION:
        store.append(task_id, "blocked", failure={"category": ctx.category.value, "layer": ctx.layer,
                                                  "signature": ctx.signature})
    return {"response": r.value, "terminal": r in TERMINAL, "needs_approval": r in NEEDS_APPROVAL,
            "executions": state.executions, "hops": state.hops}
