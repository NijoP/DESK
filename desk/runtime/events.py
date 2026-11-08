"""
DESK Event-Driven Supervisor & Event Bus.

Emits structured lifecycle events throughout task execution, enabling asynchronous
event-driven supervision and alerting AI models only when human decisions or
stage transitions occur.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Event:
    """Represents a structured runtime or engineering event."""
    event_type: str
    task_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the event into a dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class EventBus:
    """In-memory event bus with subscriber notifications and audit history."""

    def __init__(self) -> None:
        self._listeners: Dict[str, List[Callable[[Event], None]]] = {}
        self._history: List[Event] = []

    def subscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """Subscribes a callback to an event type (or '*' for all events)."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def emit(self, event_type: str, task_id: str, payload: Optional[Dict[str, Any]] = None) -> Event:
        """Creates, records, and dispatches an event to all interested subscribers."""
        event = Event(
            event_type=event_type,
            task_id=task_id,
            payload=payload or {},
        )
        self._history.append(event)

        # Notify specific listeners
        for listener in self._listeners.get(event_type, []):
            try:
                listener(event)
            except Exception:
                pass

        # Notify wildcard listeners
        for listener in self._listeners.get("*", []):
            try:
                listener(event)
            except Exception:
                pass

        return event

    def get_history(self, task_id: Optional[str] = None) -> List[Event]:
        """Returns recorded events, optionally filtered by task ID."""
        if task_id is None:
            return list(self._history)
        return [e for e in self._history if e.task_id == task_id]

    def clear(self) -> None:
        """Clears recorded event history."""
        self._history.clear()


# Global event bus singleton
_GLOBAL_EVENT_BUS: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Returns or initializes the global event bus."""
    global _GLOBAL_EVENT_BUS
    if _GLOBAL_EVENT_BUS is None:
        _GLOBAL_EVENT_BUS = EventBus()
    return _GLOBAL_EVENT_BUS
