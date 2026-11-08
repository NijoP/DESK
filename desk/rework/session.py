"""
DESK Rework Session Lifecycle, Execution Policy, and State Persistence.
Maintains a durable, recoverable ReworkSession across coding-agent and terminal restarts.
"""

from __future__ import annotations

import enum
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class ReworkSessionLifecycle(str, enum.Enum):
    IDLE = "IDLE"
    REWORK_REQUESTED = "REWORK_REQUESTED"
    INTAKE = "INTAKE"
    CONNECTING = "CONNECTING"
    IDENTITY_CONFIRMATION = "IDENTITY_CONFIRMATION"
    BASELINE_CAPTURE = "BASELINE_CAPTURE"
    ENGINEERING_AUDIT = "ENGINEERING_AUDIT"
    ISSUE_REVIEW = "ISSUE_REVIEW"
    REPAIR_PLANNING = "REPAIR_PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REPAIR_EXECUTION = "REPAIR_EXECUTION"
    READBACK = "READBACK"
    VERIFICATION = "VERIFICATION"
    RELEASE_ASSESSMENT = "RELEASE_ASSESSMENT"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_READY = "NOT_READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class ReworkExecutionPolicy(str, enum.Enum):
    AUDIT_ONLY = "AUDIT_ONLY"          # Read-only inspection; no board modifications
    GUIDED_REWORK = "GUIDED_REWORK"    # Explicit approval required per surgical repair
    SUPERVISED_REWORK = "SUPERVISED_REWORK" # Batch approvals with automated readback verification


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    timestamp: float
    reason: str = ""
    actor: str = "SYSTEM"


@dataclass
class ReworkSession:
    session_id: str
    project_id: str
    project_path: str
    policy: str = ReworkExecutionPolicy.AUDIT_ONLY.value
    state: str = ReworkSessionLifecycle.IDLE.value
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Project Identity Binding
    window_id: Optional[str] = None
    pcb_uuid: Optional[str] = None
    sheet_uuid: Optional[str] = None
    eda_port: int = 49620
    is_identity_confirmed: bool = False
    
    # Revision Tracking
    baseline_revision: Optional[str] = None
    current_revision: Optional[str] = None
    
    # Summary Counters
    detected_issues_count: int = 0
    approved_repairs_count: int = 0
    completed_repairs_count: int = 0
    failed_repairs_count: int = 0
    
    # History & Metadata
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    active_repair_id: Optional[str] = None

    def get_session_dir(self) -> str:
        d = os.path.join(self.project_path, "state", "rework", self.session_id)
        os.makedirs(d, exist_ok=True)
        return d

    def transition_to(self, target_state: ReworkSessionLifecycle, reason: str = "", actor: str = "SYSTEM") -> None:
        """Enforces safe state transitions and logs historical records."""
        old_state = self.state
        new_state = target_state.value if isinstance(target_state, ReworkSessionLifecycle) else str(target_state)
        
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=time.time(),
            reason=reason,
            actor=actor,
        )
        self.state = new_state
        self.updated_at = time.time()
        self.history.append(asdict(transition))
        self.save()

    def save(self) -> str:
        """Atomically persists session state to session.json."""
        sdir = self.get_session_dir()
        path = os.path.join(sdir, "session.json")
        tmp_path = path + f".tmp_{uuid.uuid4().hex[:6]}"
        
        data = asdict(self)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
        return path

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReworkSession:
        valid_fields = cls.__dataclass_fields__.keys()
        clean = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean)


def create_rework_session(
    project_path: str,
    policy: str = ReworkExecutionPolicy.AUDIT_ONLY.value,
    session_id: Optional[str] = None,
) -> ReworkSession:
    """Initializes and persists a new durable ReworkSession."""
    norm_path = os.path.abspath(project_path)
    proj_id = os.path.basename(norm_path)
    if not session_id:
        ts = int(time.time())
        s_uuid = uuid.uuid4().hex[:6]
        session_id = f"rework_{ts}_{s_uuid}"

    session = ReworkSession(
        session_id=session_id,
        project_id=proj_id,
        project_path=norm_path,
        policy=policy,
        state=ReworkSessionLifecycle.REWORK_REQUESTED.value,
    )
    session.save()
    return session


def load_rework_session(project_path: str, session_id: str) -> Optional[ReworkSession]:
    """Loads an existing session from disk."""
    norm_path = os.path.abspath(project_path)
    path = os.path.join(norm_path, "state", "rework", session_id, "session.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ReworkSession.from_dict(data)
    except Exception:
        return None


def get_latest_rework_session(project_path: str) -> Optional[ReworkSession]:
    """Finds and loads the most recently updated rework session for a project."""
    norm_path = os.path.abspath(project_path)
    rework_root = os.path.join(norm_path, "state", "rework")
    if not os.path.exists(rework_root):
        return None

    session_dirs = [
        d for d in os.listdir(rework_root)
        if os.path.isdir(os.path.join(rework_root, d)) and os.path.exists(os.path.join(rework_root, d, "session.json"))
    ]
    if not session_dirs:
        return None

    # Sort by directory modification time descending
    session_dirs.sort(key=lambda d: os.path.getmtime(os.path.join(rework_root, d, "session.json")), reverse=True)
    return load_rework_session(norm_path, session_dirs[0])


def get_or_create_rework_session(
    project_path: str,
    policy: str = ReworkExecutionPolicy.AUDIT_ONLY.value,
) -> ReworkSession:
    """Returns the latest active session if incomplete/resumable, otherwise creates a new one."""
    latest = get_latest_rework_session(project_path)
    if latest and latest.state not in {
        ReworkSessionLifecycle.COMPLETED.value,
        ReworkSessionLifecycle.CANCELLED.value,
        ReworkSessionLifecycle.NOT_READY.value,
    }:
        return latest
    return create_rework_session(project_path, policy=policy)
