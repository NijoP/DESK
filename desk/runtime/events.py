"""
DESK Event-Driven Supervisor & Execution Event Bus.

Emits structured lifecycle events throughout engineering task execution, enabling
asynchronous event-driven supervision, local mission control streaming (SSE), and
persistent execution telemetry.
"""

from __future__ import annotations

import datetime
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Event:
    """Represents a structured runtime or engineering event."""
    event_type: str
    task_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    execution_id: str = ""
    project_id: str = ""
    stage: str = ""
    task: str = ""
    status: str = ""
    progress: Optional[float] = None
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def __post_init__(self) -> None:
        # Populate convenience fields from payload if provided
        if self.payload:
            if not self.stage and "stage" in self.payload:
                self.stage = str(self.payload["stage"])
            if not self.task and "task" in self.payload:
                self.task = str(self.payload["task"])
            if not self.status and "status" in self.payload:
                self.status = str(self.payload["status"])
            if self.progress is None and "progress" in self.payload:
                try:
                    self.progress = float(self.payload["progress"])
                except (ValueError, TypeError):
                    self.progress = None
            if not self.message and "message" in self.payload:
                self.message = str(self.payload["message"])
            if not self.error and "error" in self.payload:
                self.error = str(self.payload["error"]) if self.payload["error"] else None
            if not self.execution_id and "execution_id" in self.payload:
                self.execution_id = str(self.payload["execution_id"])
            if not self.project_id and "project_id" in self.payload:
                self.project_id = str(self.payload["project_id"])
            if not self.task_id and "task_id" in self.payload:
                self.task_id = str(self.payload["task_id"])
            if not self.metrics and "metrics" in self.payload:
                self.metrics = dict(self.payload["metrics"])
            if not self.artifacts and "artifacts" in self.payload:
                self.artifacts = list(self.payload["artifacts"])

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the event into a standard dictionary with ISO timestamp."""
        iso_ts = datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc).isoformat()
        return {
            "event_id": self.event_id,
            "execution_id": self.execution_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "iso_timestamp": iso_ts,
            "event_type": self.event_type,
            "stage": self.stage,
            "task": self.task or self.task_id,
            "task_id": self.task_id or self.task,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "error": self.error,
            "payload": self.payload,
        }


class EventBus:
    """Thread-safe event bus with bounded replay history and subscriber dispatch."""

    def __init__(self, max_history: int = 1000) -> None:
        self.max_history = max_history
        self._listeners: Dict[str, List[Callable[[Event], None]]] = {}
        self._history: List[Event] = []
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """Subscribes a callback to an event type (or '*' for all events)."""
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            if callback not in self._listeners[event_type]:
                self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Event], None]) -> bool:
        """Unsubscribes a callback from an event type."""
        with self._lock:
            if event_type in self._listeners and callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)
                return True
            return False

    def emit(
        self,
        event_type: str,
        task_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
        execution_id: str = "",
        project_id: str = "",
        stage: str = "",
        task: str = "",
        status: str = "",
        progress: Optional[float] = None,
        message: str = "",
        metrics: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Event:
        """Creates, records, and dispatches a structured event."""
        with self._lock:
            event = Event(
                event_type=event_type,
                task_id=task_id,
                payload=payload or {},
                timestamp=timestamp or time.time(),
                execution_id=execution_id,
                project_id=project_id,
                stage=stage,
                task=task or task_id,
                status=status,
                progress=progress,
                message=message,
                metrics=metrics or {},
                artifacts=artifacts or [],
                error=error,
            )

            self._history.append(event)
            if len(self._history) > self.max_history:
                self._history.pop(0)

            # Copy listener lists to avoid holding lock during execution
            specific_listeners = list(self._listeners.get(event_type, []))
            wildcard_listeners = list(self._listeners.get("*", []))

        # Notify specific listeners
        for listener in specific_listeners:
            try:
                listener(event)
            except Exception:
                pass

        # Notify wildcard listeners
        for listener in wildcard_listeners:
            try:
                listener(event)
            except Exception:
                pass

        return event

    def get_history(self, task_id: Optional[str] = None, limit: Optional[int] = None) -> List[Event]:
        """Returns recorded events, optionally filtered by task ID and bounded by limit."""
        with self._lock:
            if task_id is None:
                res = list(self._history)
            else:
                res = [e for e in self._history if e.task_id == task_id or e.task == task_id]
            if limit and limit > 0:
                return res[-limit:]
            return res

    def get_events_since(self, last_event_id: Optional[str] = None, limit: int = 200) -> List[Event]:
        """Returns events emitted strictly after last_event_id, for SSE replay."""
        with self._lock:
            if not last_event_id:
                return list(self._history[-limit:])

            found_idx = -1
            for idx, ev in enumerate(self._history):
                if ev.event_id == last_event_id:
                    found_idx = idx
                    break

            if found_idx == -1:
                # If last_event_id is unknown or has rolled out of history, return recent bounded history
                return list(self._history[-limit:])

            return list(self._history[found_idx + 1:found_idx + 1 + limit])

    def clear(self) -> None:
        """Clears recorded event history."""
        with self._lock:
            self._history.clear()


# Global event bus singleton
_GLOBAL_EVENT_BUS: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Returns or initializes the global event bus."""
    global _GLOBAL_EVENT_BUS
    if _GLOBAL_EVENT_BUS is None:
        _GLOBAL_EVENT_BUS = EventBus()
    return _GLOBAL_EVENT_BUS
