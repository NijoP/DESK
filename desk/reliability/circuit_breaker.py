"""Circuit breaker for persistently unavailable services (gateway endpoint, routing engine, model provider).

CLOSED  calls flow; consecutive failures are counted
OPEN    calls are refused (CircuitOpen) until `recovery_timeout_s` has elapsed
HALF_OPEN one probe call is allowed; success closes the breaker, failure re-opens it

Breakers are keyed by name so one failed subsystem (a routing engine) never opens the breaker of another (the
bridge of a different project). Zero external dependencies.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from desk.errors import CircuitOpen


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    recovery_timeout_s: float = 30.0
    now: Callable[[], float] = time.time
    state: str = "CLOSED"
    failures: int = 0
    opened_at: float = 0.0
    last_error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            if self.state == "OPEN":
                if self.now() - self.opened_at >= self.recovery_timeout_s:
                    self.state = "HALF_OPEN"
                    return True
                return False
            return True   # HALF_OPEN: one probe

    def check(self) -> None:
        """Raise CircuitOpen instead of returning False."""
        if not self.allow():
            wait = max(0.0, self.recovery_timeout_s - (self.now() - self.opened_at))
            raise CircuitOpen(f"STOP: {self.name} circuit is open after {self.failures} failures "
                              f"({self.last_error}); retry in {wait:.0f}s", breaker=self.name, retry_in_s=wait)

    def record_success(self) -> None:
        with self._lock:
            self.state = "CLOSED"
            self.failures = 0
            self.last_error = ""

    def record_failure(self, error: str = "") -> None:
        with self._lock:
            self.failures += 1
            self.last_error = str(error)[:200]
            if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
                self.state = "OPEN"
                self.opened_at = self.now()

    def to_dict(self) -> Dict[str, object]:
        return {"name": self.name, "state": self.state, "failures": self.failures, "opened_at": self.opened_at,
                "last_error": self.last_error}


class BreakerRegistry:
    """Process-wide breakers by name (e.g. "gateway:49620", "engine:freerouting-2.1.0", "provider:nvidia")."""
    _breakers: Dict[str, CircuitBreaker] = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, name: str, failure_threshold: int = 3, recovery_timeout_s: float = 30.0,
            now: Optional[Callable[[], float]] = None) -> CircuitBreaker:
        with cls._lock:
            b = cls._breakers.get(name)
            if b is None:
                b = CircuitBreaker(name, failure_threshold, recovery_timeout_s, now or time.time)
                cls._breakers[name] = b
            return b

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._breakers.clear()

    @classmethod
    def snapshot(cls) -> Dict[str, Dict[str, object]]:
        with cls._lock:
            return {k: v.to_dict() for k, v in cls._breakers.items()}
