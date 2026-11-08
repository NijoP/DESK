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
    get_or_create_rework_session,
    load_rework_session,
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
    "get_or_create_rework_session",
    "load_rework_session",
]
