"""Bounded retries with exponential backoff and jitter, gated by what is known about execution.

A retry is only allowed when the first attempt is known not to have executed (or the operation is idempotent and
the outcome is known). A non-idempotent mutation with an UNKNOWN or PARTIAL outcome is never retried by this
policy: the caller must read the document back and reconcile (desk.reliability.mutation).

Zero external dependencies.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional, Set

from desk.reliability.models import ExecutionState, FailureCategory

RETRYABLE_CATEGORIES: Set[FailureCategory] = {
    FailureCategory.TRANSIENT_NETWORK, FailureCategory.API_UNAVAILABLE, FailureCategory.API_TIMEOUT,
    FailureCategory.WINDOW_ID_ROTATED, FailureCategory.WINDOW_DISCONNECTED, FailureCategory.LOCK_CONFLICT,
}
SAFE_STATES: Set[ExecutionState] = {ExecutionState.NOT_EXECUTED, ExecutionState.GATEWAY_NOT_EXECUTED}


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    multiplier: float = 2.0
    jitter: float = 0.25                # fraction of the delay added/subtracted at random
    retry_on: Set[FailureCategory] = field(default_factory=lambda: set(RETRYABLE_CATEGORIES))
    rng: Callable[[], float] = random.random

    def delays(self) -> Iterator[float]:
        d = self.base_delay_s
        for _ in range(max(0, self.max_attempts - 1)):
            j = 1.0 + (self.rng() * 2.0 - 1.0) * self.jitter
            yield max(0.0, min(self.max_delay_s, d * j))
            d = min(self.max_delay_s, d * self.multiplier)

    def should_retry(self, attempt: int, category: FailureCategory, state: ExecutionState, idempotent: bool) -> bool:
        """`attempt` is 1-based (the attempt that just failed)."""
        if attempt >= self.max_attempts:
            return False
        if category not in self.retry_on:
            return False
        if state in SAFE_STATES:
            return True
        if idempotent and state in (ExecutionState.EXECUTED_RESPONSE_LOST, ExecutionState.EXECUTED_STALE_READBACK):
            return True
        return False   # UNKNOWN / PARTIAL / FALSE_SUCCESS on a non-idempotent op: reconcile, never repeat

    @classmethod
    def for_reads(cls) -> "RetryPolicy":
        return cls(max_attempts=3, base_delay_s=0.5, max_delay_s=5.0)

    @classmethod
    def none(cls) -> "RetryPolicy":
        return cls(max_attempts=1)
