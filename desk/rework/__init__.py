"""
DESK Rework Mode Engine Package.
Existing PCB Recovery, Engineering Audit, Controlled Repair & Manufacturing Readiness.
Zero external dependencies (pure Python standard library).
"""

from desk.rework.mode import (
    DESK_MODE_DESIGN,
    DESK_MODE_REWORK,
    DESK_MODE_AUDIT,
    detect_mode_intent,
    is_rework_intent,
)
from desk.rework.session import (
    ReworkSession,
    ReworkSessionLifecycle,
    ReworkExecutionPolicy,
    create_rework_session,
    load_rework_session,
    get_latest_rework_session,
    get_or_create_rework_session,
)
from desk.rework.connection import (
    ProjectBinding,
    ECADConnectionManager,
    ConnectionDiscoveryError,
    ProjectMismatchError,
)
from desk.rework.baseline import (
    BaselineSnapshot,
    BaselineCaptureEngine,
)
from desk.rework.audit import (
    Issue,
    IssueCategory,
    IssueSeverity,
    ReworkAuditEngine,
)
from desk.rework.planner import (
    RepairAction,
    RepairPlan,
    ApprovalToken,
    RepairPlanner,
    ObjectProtectionClass,
)
from desk.rework.executor import (
    RepairExecutor,
    RepairExecutionResult,
)
from desk.rework.readiness import (
    ReadinessOutcome,
    ReadinessAssessment,
    ManufacturingReadinessEngine,
)

__all__ = [
    "DESK_MODE_DESIGN",
    "DESK_MODE_REWORK",
    "DESK_MODE_AUDIT",
    "detect_mode_intent",
    "is_rework_intent",
    "ReworkSession",
    "ReworkSessionLifecycle",
    "ReworkExecutionPolicy",
    "create_rework_session",
    "load_rework_session",
    "get_latest_rework_session",
    "get_or_create_rework_session",
    "ProjectBinding",
    "ECADConnectionManager",
    "ConnectionDiscoveryError",
    "ProjectMismatchError",
    "BaselineSnapshot",
    "BaselineCaptureEngine",
    "Issue",
    "IssueCategory",
    "IssueSeverity",
    "ReworkAuditEngine",
    "RepairAction",
    "RepairPlan",
    "ApprovalToken",
    "RepairPlanner",
    "ObjectProtectionClass",
    "RepairExecutor",
    "RepairExecutionResult",
    "ReadinessOutcome",
    "ReadinessAssessment",
    "ManufacturingReadinessEngine",
]
