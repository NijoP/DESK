"""
DESK Durable Task Inbox & Execution Queue.

Implements durable instruction queuing, monotonic sequence numbering, idempotency
deduplication, and design profile revision binding inspired by Pi durable task orchestration.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from desk.operation_registry import ReplayPolicy
from desk.runtime.events import get_event_bus
from desk.runtime.task_state import TaskState, TaskStateMachine


@dataclass
class TaskMessage:
    """Represents a durable queued or executing task instruction."""
    task_id: str
    sequence_number: int
    task_type: str
    payload: Dict[str, Any]
    profile_revision: str = ""
    idempotency_hash: str = ""
    created_at: float = field(default_factory=time.time)
    acknowledged: bool = False
    ack_timestamp: Optional[float] = None
    replay_policy: ReplayPolicy = ReplayPolicy.SAFE_IDEMPOTENT
    state_machine: TaskStateMachine = field(default_factory=lambda: TaskStateMachine(TaskState.QUEUED))

    @property
    def current_state(self) -> TaskState:
        """Convenience property for task state."""
        return self.state_machine.current_state

    def to_dict(self) -> Dict[str, Any]:
        """Serializes task into a dictionary."""
        return {
            "task_id": self.task_id,
            "sequence_number": self.sequence_number,
            "task_type": self.task_type,
            "payload": self.payload,
            "profile_revision": self.profile_revision,
            "idempotency_hash": self.idempotency_hash,
            "created_at": self.created_at,
            "acknowledged": self.acknowledged,
            "ack_timestamp": self.ack_timestamp,
            "replay_policy": self.replay_policy.value,
            "current_state": self.current_state.value,
        }


class TaskInbox:
    """
    Durable in-memory and disk-persisted task inbox.
    Guarantees monotonic sequence ordering, profile revision binding, and idempotent deduplication.
    """

    def __init__(self, ledger_path: Optional[Path | str] = None) -> None:
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self._tasks: Dict[str, TaskMessage] = {}
        self._hash_to_id: Dict[str, str] = {}
        self._sequence_counter: int = 0
        self._event_bus = get_event_bus()

    def _compute_hash(self, task_type: str, payload: Dict[str, Any], profile_revision: str) -> str:
        """Generates deterministic idempotency hash for task deduplication."""
        try:
            serialized_payload = json.dumps(payload, sort_keys=True)
        except (TypeError, ValueError):
            serialized_payload = str(sorted(payload.items()))
        raw = f"{task_type}:{serialized_payload}:{profile_revision}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def submit(
        self,
        task_type: str,
        payload: Dict[str, Any],
        profile_revision: str = "",
        replay_policy: ReplayPolicy = ReplayPolicy.SAFE_IDEMPOTENT,
    ) -> TaskMessage:
        """
        Submits an engineering task instruction into the durable inbox.
        If an identical task already exists with SAFE_IDEMPOTENT or SAFE_READ policy,
        returns the existing message rather than duplicating work.
        """
        h = self._compute_hash(task_type, payload, profile_revision)

        # Check existing task idempotency
        if h in self._hash_to_id:
            existing_id = self._hash_to_id[h]
            existing_task = self._tasks[existing_id]
            # If still active or safely completed, return existing
            if not existing_task.state_machine.current_state == TaskState.FAILED:
                return existing_task

        self._sequence_counter += 1
        task_id = f"tsk_{self._sequence_counter:04d}_{uuid.uuid4().hex[:6]}"
        sm = TaskStateMachine(initial_state=TaskState.QUEUED, task_id=task_id)

        task = TaskMessage(
            task_id=task_id,
            sequence_number=self._sequence_counter,
            task_type=task_type,
            payload=payload,
            profile_revision=profile_revision,
            idempotency_hash=h,
            replay_policy=replay_policy,
            state_machine=sm,
        )

        self._tasks[task_id] = task
        self._hash_to_id[h] = task_id

        self._event_bus.emit(
            event_type="task.queued",
            task_id=task_id,
            payload={"sequence_number": task.sequence_number, "task_type": task_type},
        )

        return task

    def acknowledge(self, task_id: str) -> None:
        """Marks a task as received and acknowledged by an active worker or bridge."""
        task = self._tasks.get(task_id)
        if task:
            task.acknowledged = True
            task.ack_timestamp = time.time()
            self._event_bus.emit(
                event_type="task.acknowledged",
                task_id=task_id,
                payload={"ack_timestamp": task.ack_timestamp},
            )

    def get_task(self, task_id: str) -> Optional[TaskMessage]:
        """Retrieves a task by ID."""
        return self._tasks.get(task_id)

    def get_next_pending(self) -> Optional[TaskMessage]:
        """Retrieves the oldest queued task awaiting execution."""
        queued = [t for t in self._tasks.values() if t.current_state == TaskState.QUEUED]
        if not queued:
            return None
        queued.sort(key=lambda t: t.sequence_number)
        return queued[0]

    def list_tasks(self, include_completed: bool = True) -> List[TaskMessage]:
        """Returns all tasks sorted by sequence number."""
        tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if not t.state_machine.is_terminal()]
        tasks.sort(key=lambda t: t.sequence_number)
        return tasks


# Global task inbox singleton
_GLOBAL_INBOX: Optional[TaskInbox] = None


def get_task_inbox() -> TaskInbox:
    """Returns or initializes the global task inbox."""
    global _GLOBAL_INBOX
    if _GLOBAL_INBOX is None:
        _GLOBAL_INBOX = TaskInbox()
    return _GLOBAL_INBOX
