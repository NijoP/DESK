"""Deterministic failure classification: exceptions, engine results and log text -> FailureCategory + ExecutionState.

Classification is a lookup over typed errors and measured signatures (desk.reliability.registry), never a guess from a
model. Where the facts do not decide, the result is UNKNOWN_FAILURE / UNKNOWN and the diagnosis layer says what is
missing. Zero external dependencies.
"""
from __future__ import annotations

import re
import socket
from typing import Any, Dict, Optional, Tuple

from desk import errors as E
from desk.reliability.models import ExecutionState as X, FailureCategory as C, FailureRecord


# ------------------------------------------------------------------------------------------------ text signatures
_TEXT_RULES = (
    (re.compile(r"UnsupportedClassVersionError|class file version", re.I), C.JAVA_RUNTIME_INCOMPATIBLE),
    (re.compile(r"OutOfMemoryError|Java heap space|GC overhead", re.I), C.ROUTER_RESOURCE_EXHAUSTION),
    (re.compile(r"maze search algorithm could not be created|no legal escape", re.I), C.ROUTER_NO_LEGAL_ESCAPE),
    (re.compile(r"No compatible Freerouting engine|Java executable not found|FREEROUTING_JAR", re.I), C.EXTERNAL_TOOL_UNSUPPORTED),
    (re.compile(r"no longer connected|not connected|unknown window", re.I), C.WINDOW_ID_ROTATED),
    (re.compile(r"WRONG SHEET", re.I), C.DOCUMENT_CONTEXT_LOST),
    (re.compile(r"another writer holds the lock", re.I), C.LOCK_CONFLICT),
    (re.compile(r"unfinished .* on .* \(op", re.I), C.UNKNOWN_MUTATION_OUTCOME),
    (re.compile(r"is not a function|is not iterable|Cannot read propert|undefined is not", re.I), C.API_SCHEMA_MISMATCH),
    (re.compile(r"timed out|timeout", re.I), C.API_TIMEOUT),
    (re.compile(r"Connection refused|WinError 10061|Errno 111|Bridge not reachable", re.I), C.API_UNAVAILABLE),
    (re.compile(r"Exception in thread|java\.lang\.\w+Exception|Error while loading|could not be parsed", re.I), C.ROUTER_ENGINE_CRASH),
)


def classify_text(text: str) -> Optional[C]:
    for rx, cat in _TEXT_RULES:
        if rx.search(text or ""):
            return cat
    return None


# ------------------------------------------------------------------------------------------------ exceptions
def classify_exception(exc: BaseException, mutating: bool = False) -> Tuple[C, X]:
    """(category, execution state) for a raised error. Typed DESK errors decide first; text is the fallback."""
    if isinstance(exc, E.BridgeWindowRotated):
        return C.WINDOW_ID_ROTATED, X.GATEWAY_NOT_EXECUTED
    if isinstance(exc, E.IdentityUnverified):
        return C.WRONG_PROJECT_CONTEXT, X.NOT_EXECUTED
    if isinstance(exc, E.BridgeDocumentMismatch):
        return C.DOCUMENT_CONTEXT_LOST, X.GATEWAY_NOT_EXECUTED     # the guard refused before touching anything
    if isinstance(exc, E.BridgeMutationTimeout):
        return C.UNKNOWN_MUTATION_OUTCOME, X.EXECUTED_RESPONSE_LOST
    if isinstance(exc, E.BridgeUnreachable):
        return C.API_UNAVAILABLE, X.NOT_EXECUTED
    if isinstance(exc, E.CircuitOpen):
        return C.API_UNAVAILABLE, X.NOT_EXECUTED
    if isinstance(exc, E.BridgeScriptError):
        cat = classify_text(str(exc)) or C.API_SCHEMA_MISMATCH
        if cat in (C.API_TIMEOUT,):
            return cat, (X.EXECUTED_RESPONSE_LOST if mutating else X.UNKNOWN)
        if cat == C.WINDOW_ID_ROTATED:
            return cat, X.GATEWAY_NOT_EXECUTED
        return cat, (X.UNKNOWN if mutating else X.NOT_EXECUTED)
    if isinstance(exc, E.WriteLockHeld):
        return C.LOCK_CONFLICT, X.NOT_EXECUTED
    if isinstance(exc, E.PendingOperationError):
        return C.UNKNOWN_MUTATION_OUTCOME, X.UNKNOWN
    if isinstance(exc, E.DesignProfileInvalid):
        return C.DESIGN_PROFILE_INVALID, X.NOT_EXECUTED
    if isinstance(exc, E.EngineeringDecisionRequired):
        cat = exc.context.get("category") if hasattr(exc, "context") else None
        try:
            return C(cat), X.NOT_EXECUTED
        except Exception:
            return C.ROUTER_RULE_CONFLICT, X.NOT_EXECUTED
    if isinstance(exc, (E.ApprovalRequired, E.RecoveryRefused)):
        return C.REQUIREMENT_CONFLICT, X.NOT_EXECUTED
    if isinstance(exc, E.ProjectError):
        return C.WRONG_PROJECT_CONTEXT, X.NOT_EXECUTED
    if isinstance(exc, MemoryError):
        return C.RESOURCE_LIMIT, X.UNKNOWN
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return C.API_TIMEOUT, (X.EXECUTED_RESPONSE_LOST if mutating else X.UNKNOWN)
    if isinstance(exc, ConnectionRefusedError):
        return C.API_UNAVAILABLE, X.NOT_EXECUTED
    if isinstance(exc, FileNotFoundError):
        return C.EXTERNAL_TOOL_UNSUPPORTED, X.NOT_EXECUTED
    if isinstance(exc, OSError):
        return C.TRANSIENT_NETWORK, X.NOT_EXECUTED
    cat = classify_text(str(exc))
    if cat is not None:
        return cat, X.UNKNOWN
    return C.UNKNOWN_FAILURE, X.UNKNOWN


# ------------------------------------------------------------------------------------------------ engine results
_STATUS_MAP = {
    "TIMEOUT": C.ROUTER_ENGINE_TIMEOUT, "TIMEOUT_PARTIAL": C.ROUTER_ENGINE_TIMEOUT, "STAGNATED": C.ROUTER_STAGNATION,
    "PLATEAU_PARTIAL": C.ROUTER_STAGNATION, "CRASHED": C.ROUTER_ENGINE_CRASH, "NO_SES": C.ROUTER_SES_MISSING,
    "SMOKE_NO_SES": C.ROUTER_SES_MISSING, "INCOMPATIBLE": C.JAVA_RUNTIME_INCOMPATIBLE,
    "ENGINE_UNBOUNDABLE": C.EXTERNAL_TOOL_UNSUPPORTED, "NO_RUN": C.EXTERNAL_TOOL_UNSUPPORTED,
}


def classify_engine_result(status: str, engine_config: Optional[Dict[str, Any]] = None, stdout: str = "", stderr: str = "",
                           ses_generated: bool = False, final_unrouted: Optional[int] = None) -> Optional[C]:
    """Category for a routing engine result; None when the run is a routing success (valid SES, 0 unrouted)."""
    cfg = engine_config or {}
    if cfg.get("failure_category"):
        try:
            return C(cfg["failure_category"])
        except ValueError:
            pass
    text_cat = classify_text((stderr or "") + "\n" + (stdout or ""))
    if text_cat in (C.JAVA_RUNTIME_INCOMPATIBLE, C.ROUTER_RESOURCE_EXHAUSTION, C.ROUTER_NO_LEGAL_ESCAPE, C.ROUTER_ENGINE_CRASH):
        return text_cat
    if status == "SUCCESS" and ses_generated and (final_unrouted or 0) == 0:
        return None
    if status == "SUCCESS" and ses_generated:
        return C.ROUTER_STAGNATION      # the engine ended, copper exists, connections remain: not a success
    return _STATUS_MAP.get(status, C.UNKNOWN_FAILURE)


# ------------------------------------------------------------------------------------------------ signatures
_NOISE = re.compile(r"(0x[0-9a-f]+|\b\d+(\.\d+)?\b|[\"'][^\"']{0,80}[\"']|[A-Za-z]:\\[^\s]+|/[^\s]+)")


def signature(category: C, message: str, module: str = "") -> str:
    """Stable key of a failure: category + module + message with numbers, paths and quoted values removed."""
    text = _NOISE.sub("#", message or "").lower()
    text = re.sub(r"\s+", " ", text).strip()[:120]
    return f"{category.value}|{module}|{text}"


def classify_record(rec: FailureRecord) -> FailureRecord:
    """Fill a record's signature (and category when it is UNKNOWN_FAILURE but the text decides)."""
    if rec.category == C.UNKNOWN_FAILURE:
        cat = classify_text(" ".join([rec.message, rec.stderr_tail, rec.stdout_tail]))
        if cat is not None:
            rec.category = cat
    rec.signature = signature(rec.category, rec.message, rec.module)
    return rec
