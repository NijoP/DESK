"""
DESK Rework Mode Repair Planner, Dependency Analysis & Approval Engine.
Formulates minimal-change surgical repair plans, establishes dependency ordering,
protects accepted design elements, and manages cryptographically bound approval tokens.
Zero external dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from desk.rework.audit import Issue, IssueCategory, IssueSeverity


class ObjectProtectionClass:
    PROTECTED = "PROTECTED"    # Locked anchors, approved critical routes, mechanical keepouts
    ACCEPTED = "ACCEPTED"      # Verified working geometry; must be preserved
    MODIFIABLE = "MODIFIABLE"  # Authorized target for surgical mutation
    INVALID = "INVALID"        # Confirmed defective primitives designated for removal/rip-up
    UNKNOWN = "UNKNOWN"        # Unverified intent requiring engineer escalation


@dataclass
class ApprovalToken:
    token: str
    repair_id: str
    session_id: str
    project_id: str
    revision_hash: str
    action_type: str
    granted_at: float
    granted_by: str = "CAPTAIN"
    is_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ApprovalToken:
        return cls(**data)


@dataclass
class RepairAction:
    repair_id: str
    issue_id: str
    sequence_number: int
    action_type: str
    description: str
    affected_objects: Dict[str, Any]
    protected_objects: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    verification_method: str = ""
    requires_approval: bool = True
    approval_status: str = "PENDING"  # PENDING, APPROVED, REJECTED, SUPERSEDED
    approval_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RepairAction:
        valid_fields = cls.__dataclass_fields__.keys()
        clean = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean)


@dataclass
class RepairPlan:
    session_id: str
    project_id: str
    project_path: str
    baseline_revision: str
    created_at: float
    repairs: List[RepairAction] = field(default_factory=list)
    protected_summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RepairPlan:
        repairs_raw = data.get("repairs", [])
        repairs = [RepairAction.from_dict(r) for r in repairs_raw]
        return cls(
            session_id=data["session_id"],
            project_id=data["project_id"],
            project_path=data["project_path"],
            baseline_revision=data["baseline_revision"],
            created_at=data["created_at"],
            repairs=repairs,
            protected_summary=data.get("protected_summary", {}),
        )


class RepairPlanner:
    """Derives dependency-ordered, surgical repair plans from an audit issue inventory."""

    @staticmethod
    def _category_priority(category: str) -> int:
        """Determines strict engineering dependency sequence."""
        order = {
            IssueCategory.REQUIREMENTS: 1,
            IssueCategory.SCHEMATIC: 2,
            IssueCategory.COMPONENT: 3,
            IssueCategory.PLACEMENT: 4,
            IssueCategory.POWER_THERMAL: 5,
            IssueCategory.ROUTING: 6,
            IssueCategory.COPPER: 7,
            IssueCategory.DRC: 8,
        }
        return order.get(category, 99)

    @staticmethod
    def generate_approval_token(
        repair: RepairAction,
        session_id: str,
        project_id: str,
        revision_hash: str,
        actor: str = "CAPTAIN",
    ) -> ApprovalToken:
        """Generates a cryptographically bound approval token."""
        raw_seed = f"{session_id}:{project_id}:{revision_hash}:{repair.repair_id}:{repair.action_type}:{time.time()}"
        tok_str = f"RW-APR-{hashlib.sha1(raw_seed.encode('utf-8')).hexdigest()[:12].upper()}"
        
        return ApprovalToken(
            token=tok_str,
            repair_id=repair.repair_id,
            session_id=session_id,
            project_id=project_id,
            revision_hash=revision_hash,
            action_type=repair.action_type,
            granted_at=time.time(),
            granted_by=actor,
            is_valid=True,
        )

    @classmethod
    def create_plan(
        cls,
        session_id: str,
        project_path: str,
        baseline_revision: str,
        issues: List[Issue],
        existing_tracks_count: int = 0,
        existing_components_count: int = 0,
    ) -> RepairPlan:
        """Constructs a minimal-change surgical repair plan with dependency chains."""
        norm_path = os.path.abspath(project_path)
        proj_id = os.path.basename(norm_path)

        # Sort issues strictly by engineering category hierarchy then severity
        severity_rank = {
            IssueSeverity.CRITICAL: 1,
            IssueSeverity.HIGH: 2,
            IssueSeverity.MEDIUM: 3,
            IssueSeverity.LOW: 4,
            IssueSeverity.INFORMATIONAL: 5,
        }
        sorted_issues = sorted(
            issues,
            key=lambda i: (cls._category_priority(i.category), severity_rank.get(i.severity, 99))
        )

        repairs: List[RepairAction] = []
        action_counter = 0
        previous_repair_id_by_category: Dict[str, str] = {}

        for iss in sorted_issues:
            # Skip purely informational or unresolvable issues without proposed repairs
            if iss.severity == IssueSeverity.INFORMATIONAL:
                continue

            action_counter += 1
            r_id = f"RP-{action_counter:04d}"
            
            # Map action type
            action_type = "SURGICAL_REPAIR"
            if iss.category == IssueCategory.SCHEMATIC:
                action_type = "UPDATE_PAD_NET"
            elif iss.category == IssueCategory.PLACEMENT:
                action_type = "NUDGE_COMPONENT"
            elif iss.category == IssueCategory.ROUTING:
                action_type = "ROUTE_NET"
            elif iss.category == IssueCategory.POWER_THERMAL:
                action_type = "WIDEN_POWER_TRACK"
            elif iss.category == IssueCategory.COPPER:
                action_type = "REPOUR_COPPER_ZONE"
            elif iss.category == IssueCategory.DRC:
                action_type = "RESOLVE_DRC_VIOLATION"

            # Establish dependencies
            deps: List[str] = []
            cat_p = cls._category_priority(iss.category)
            if cat_p > 2 and IssueCategory.SCHEMATIC in previous_repair_id_by_category:
                deps.append(previous_repair_id_by_category[IssueCategory.SCHEMATIC])
            if cat_p > 4 and IssueCategory.PLACEMENT in previous_repair_id_by_category:
                deps.append(previous_repair_id_by_category[IssueCategory.PLACEMENT])

            repair = RepairAction(
                repair_id=r_id,
                issue_id=iss.issue_id,
                sequence_number=action_counter,
                action_type=action_type,
                description=f"Repair for {iss.title}: {iss.description}",
                affected_objects=iss.affected_objects,
                protected_objects={
                    "protected_tracks_count": max(0, existing_tracks_count - 1),
                    "protected_components_count": max(0, existing_components_count - 1),
                },
                dependencies=deps,
                preconditions=[f"Baseline revision matches '{baseline_revision}'"],
                verification_method=iss.verification_method or "Readback and DRC verification",
                requires_approval=True,
                approval_status="PENDING",
            )
            repairs.append(repair)
            previous_repair_id_by_category[iss.category] = r_id

        plan = RepairPlan(
            session_id=session_id,
            project_id=proj_id,
            project_path=norm_path,
            baseline_revision=baseline_revision,
            created_at=time.time(),
            repairs=repairs,
            protected_summary={
                "accepted_tracks": existing_tracks_count,
                "accepted_components": existing_components_count,
            },
        )

        # Save to projects/<P>/state/rework/<SESSION_ID>/repair_plan.json
        sdir = os.path.join(norm_path, "state", "rework", session_id)
        os.makedirs(sdir, exist_ok=True)
        plan_path = os.path.join(sdir, "repair_plan.json")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, indent=2)

        return plan

    @classmethod
    def load_plan(cls, project_path: str, session_id: str) -> Optional[RepairPlan]:
        path = os.path.join(project_path, "state", "rework", session_id, "repair_plan.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return RepairPlan.from_dict(data)
        except Exception:
            return None

    @classmethod
    def save_approval(cls, project_path: str, session_id: str, token: ApprovalToken) -> None:
        sdir = os.path.join(project_path, "state", "rework", session_id)
        os.makedirs(sdir, exist_ok=True)
        path = os.path.join(sdir, "approvals.json")
        approvals = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    approvals = json.load(f)
            except Exception:
                approvals = []
        approvals.append(token.to_dict())
        with open(path, "w", encoding="utf-8") as f:
            json.dump(approvals, f, indent=2)
