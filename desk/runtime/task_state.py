"""
DESK Task Lifecycle State Machine.

Implements the formal 12-state task lifecycle inspired by Pi durable task orchestration,
preventing invalid state transitions and maintaining an immutable audit ledger of all
state changes.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


class TaskState(str, enum.Enum):
    """The 12 formal states of an engineering task."""
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    PAUSED_RESOURCE = "PAUSED_RESOURCE"
    PAUSED_EXTERNAL = "PAUSED_EXTERNAL"
    NEEDS_DECISION = "NEEDS_DECISION"
    RECOVERING = "RECOVERING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"


# Allowed transitions map: CurrentState -> Set of Allowed Next States
VALID_TRANSITIONS: Dict[TaskState, Set[TaskState]] = {
    TaskState.QUEUED: {TaskState.PREPARING, TaskState.CANCELLED, TaskState.UNKNOWN},
    TaskState.PREPARING: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED, TaskState.UNKNOWN},
    TaskState.RUNNING: {
        TaskState.PAUSED_RESOURCE,
        TaskState.PAUSED_EXTERNAL,
        TaskState.NEEDS_DECISION,
        TaskState.RECOVERING,
        TaskState.VALIDATING,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.UNKNOWN,
    },
    TaskState.PAUSED_RESOURCE: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED, TaskState.UNKNOWN},
    TaskState.PAUSED_EXTERNAL: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED, TaskState.UNKNOWN},
    TaskState.NEEDS_DECISION: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED, TaskState.UNKNOWN},
    TaskState.RECOVERING: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED, TaskState.UNKNOWN},
    TaskState.VALIDATING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.UNKNOWN},
    TaskState.UNKNOWN: {TaskState.RECOVERING, TaskState.FAILED, TaskState.CANCELLED},
    # Terminal states have no valid transitions
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}


@dataclass
class StateTransitionRecord:
    """Record of an individual state transition for auditability."""
    from_state: TaskState
    to_state: TaskState
    timestamp: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskStateMachine:
    """
    Finite state machine enforcing valid transitions across the 12 task states
    and recording transition history.
    """

    def __init__(self, initial_state: TaskState = TaskState.QUEUED, task_id: str = "") -> None:
        self.task_id = task_id
        self._current_state = initial_state
        self._history: List[StateTransitionRecord] = [
            StateTransitionRecord(
                from_state=initial_state,
                to_state=initial_state,
                timestamp=time.time(),
                reason="Task initialized",
            )
        ]

    @property
    def current_state(self) -> TaskState:
        """Returns the current task state."""
        return self._current_state

    @property
    def history(self) -> List[StateTransitionRecord]:
        """Returns the transition history list."""
        return list(self._history)

    def is_terminal(self) -> bool:
        """Returns True if the task has reached a terminal state."""
        return self._current_state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}

    def transition_to(
        self,
        new_state: TaskState,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Transitions the task to a new state if valid.
        Raises ValueError if the transition is prohibited.
        """
        if new_state == self._current_state:
            return  # No-op re-entry

        allowed = VALID_TRANSITIONS.get(self._current_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal state transition for task '{self.task_id}': "
                f"Cannot move from {self._current_state.value} to {new_state.value}."
            )

        record = StateTransitionRecord(
            from_state=self._current_state,
            to_state=new_state,
            timestamp=time.time(),
            reason=reason,
            metadata=metadata or {},
        )
        self._current_state = new_state
        self._history.append(record)
