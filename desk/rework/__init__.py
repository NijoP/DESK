"""
DESK Rework Mode Engine Package.
Existing PCB Recovery, Engineering Audit, Controlled Repair & Manufacturing Readiness.
Zero external dependencies (pure Python standard library).

Lazy facade (T-19): submodules load on first attribute access, so `import desk.rework` is
cheap and `from desk.rework import ReworkSession` only loads `session`.
"""
import importlib

# name -> submodule (no `typing` import here: it alone costs ~20 ms in a fresh interpreter)
_EXPORTS = {
    "DESK_MODE_DESIGN": "mode", "DESK_MODE_REWORK": "mode", "DESK_MODE_AUDIT": "mode",
    "detect_mode_intent": "mode", "is_rework_intent": "mode",
    "ReworkSession": "session", "ReworkSessionLifecycle": "session", "ReworkExecutionPolicy": "session",
    "create_rework_session": "session", "load_rework_session": "session",
    "get_latest_rework_session": "session", "get_or_create_rework_session": "session",
    "ProjectBinding": "connection", "ECADConnectionManager": "connection",
    "ConnectionDiscoveryError": "connection", "ProjectMismatchError": "connection",
    "BaselineSnapshot": "baseline", "BaselineCaptureEngine": "baseline",
    "Issue": "audit", "IssueCategory": "audit", "IssueSeverity": "audit", "ReworkAuditEngine": "audit",
    "RepairAction": "planner", "RepairPlan": "planner", "ApprovalToken": "planner",
    "RepairPlanner": "planner", "ObjectProtectionClass": "planner",
    "RepairExecutor": "executor", "RepairExecutionResult": "executor",
    "ReadinessOutcome": "readiness", "ReadinessAssessment": "readiness", "ManufacturingReadinessEngine": "readiness",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    mod = _EXPORTS.get(name)
    if mod is None:
        raise AttributeError(f"module 'desk.rework' has no attribute {name!r}")
    value = getattr(importlib.import_module(f"desk.rework.{mod}"), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
