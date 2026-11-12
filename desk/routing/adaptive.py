"""Adaptive chunk planning for supervised routing runs.

UPS_1000 attempts 5 and 6 (live-test/ups-1000/builder-records/route_run5.txt, route_run6.txt) lost every pass
they routed because the chunk size was static: at least four passes inside a 300 s window on a board whose passes
took 84-185 s. The planner below sizes each chunk from the pass durations the previous chunks measured, so a slow
board gets one-pass chunks with a window long enough to finish, and a fast board gets up to `max_passes` passes
per chunk. A chunk is only bounded when the engine profile says the engine honours `max_passes` (or the first
chunk proved it); otherwise the plan says so instead of pretending.

Zero external dependencies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from desk.routing.engine_profiles import EngineProfile, UNKNOWN


@dataclass
class PassStats:
    durations_s: List[float] = field(default_factory=list)

    def add(self, seconds: Optional[float]) -> None:
        if seconds is not None and seconds > 0:
            self.durations_s.append(float(seconds))

    def extend_from_history(self, history: Sequence[Dict[str, object]]) -> None:
        for rec in history:
            self.add(rec.get("seconds") if isinstance(rec, dict) else None)   # type: ignore[arg-type]

    @property
    def n(self) -> int:
        return len(self.durations_s)

    @property
    def mean(self) -> Optional[float]:
        return sum(self.durations_s) / self.n if self.n else None

    @property
    def max(self) -> Optional[float]:
        return max(self.durations_s) if self.n else None

    def p95(self) -> Optional[float]:
        """Upper estimate of one pass: the maximum until three samples exist, then the larger of the nearest-rank
        95th percentile and the slowest of the last three passes (a late slow pass must still fit the window)."""
        if not self.n:
            return None
        if self.n < 3:
            return self.max
        d = sorted(self.durations_s)
        p95 = d[min(self.n - 1, int(math.ceil(0.95 * self.n)) - 1)]
        return max(p95, max(self.durations_s[-3:]))


@dataclass
class ChunkPlan:
    passes: int
    timeout_s: float
    bounded: bool
    reason: str
    per_pass_estimate_s: Optional[float] = None
    confidence: str = "UNVERIFIED"       # UNVERIFIED (no measurement) | MEASURED

    def to_dict(self) -> Dict[str, object]:
        return {"passes": self.passes, "timeout_s": round(self.timeout_s, 1), "bounded": self.bounded, "reason": self.reason,
                "per_pass_estimate_s": self.per_pass_estimate_s, "confidence": self.confidence}


class ChunkPlanner:
    """Plans the next chunk from measured pass durations.

    window_s        the nominal time a chunk may take (the caller's chunk timeout)
    safety          fraction of the window the planner fills with estimated pass time (0.3-0.9)
    min_passes      never below 1
    max_passes      upper bound per chunk (the caller's chunk_passes)
    first_passes    passes for the first chunk when nothing was measured (small: it is the measurement)
    """

    def __init__(self, window_s: float, safety: float = 0.6, min_passes: int = 1, max_passes: int = 6,
                 first_passes: int = 2, profile: EngineProfile = UNKNOWN):
        self.window_s = max(30.0, float(window_s))
        self.safety = min(0.9, max(0.3, float(safety)))
        self.min_passes = max(1, int(min_passes))
        self.max_passes = max(self.min_passes, int(max_passes))
        self.first_passes = max(self.min_passes, min(self.max_passes, int(first_passes)))
        self.profile = profile

    def plan(self, stats: PassStats, remaining_s: float) -> ChunkPlan:
        remaining = max(0.0, float(remaining_s))
        boundable = self.profile.boundable
        if boundable is False:
            return ChunkPlan(passes=self.max_passes, timeout_s=min(self.window_s, remaining) if remaining else self.window_s,
                             bounded=False,
                             reason=f"engine profile {self.profile.name} ignores max_passes/job_timeout; a chunk cannot end "
                                    "by itself and a terminated JVM writes no SES",
                             per_pass_estimate_s=stats.p95(), confidence="MEASURED" if stats.n else "UNVERIFIED")
        est = stats.p95()
        if est is None:
            timeout = min(self.window_s, remaining) if remaining else self.window_s
            return ChunkPlan(passes=self.first_passes, timeout_s=timeout, bounded=boundable is not False,
                             reason=f"no pass measured yet: {self.first_passes} pass(es) to measure the board",
                             per_pass_estimate_s=None, confidence="UNVERIFIED")
        usable = self.window_s * self.safety
        passes = int(usable // est)
        if passes >= self.min_passes:
            passes = min(self.max_passes, passes)
            timeout = self.window_s
            reason = f"{passes} pass(es) of about {est:.0f} s fit {self.safety:.0%} of a {self.window_s:.0f} s window"
        else:
            passes = self.min_passes
            timeout = passes * est / self.safety
            reason = (f"one pass takes about {est:.0f} s, longer than {usable:.0f} s usable: "
                      f"{passes} pass(es) with a {timeout:.0f} s window")
        if remaining and timeout > remaining:
            if remaining < est / self.safety:
                return ChunkPlan(passes=0, timeout_s=0.0, bounded=True,
                                 reason=f"remaining budget {remaining:.0f} s cannot fit one pass of about {est:.0f} s",
                                 per_pass_estimate_s=est, confidence="MEASURED")
            timeout = remaining
            passes = max(self.min_passes, min(passes, int(remaining * self.safety // est) or self.min_passes))
            reason += f"; capped by remaining budget {remaining:.0f} s"
        return ChunkPlan(passes=passes, timeout_s=timeout, bounded=True, reason=reason, per_pass_estimate_s=est,
                         confidence="MEASURED")


def chunk_outcome(timed_out: bool, passes: int, ses_generated: bool, ses_valid: Optional[bool], returncode: int,
                  planned_passes: Optional[int], unrouted_final: Optional[int], improved: Optional[bool],
                  status: str = "") -> str:
    """Name the outcome of one chunk from facts alone (the vocabulary of the recovery supervisor).

    ENGINE_TIMEOUT          the engine stopped at its own job_timeout and wrote a SES (TIMEOUT_PARTIAL)
    ENGINE_CRASH            non-zero exit without a SES after 0 passes, or an exception before any pass
    CHUNK_TIMEOUT           DESK's window elapsed, passes ran, no SES (the JVM was stopped before writing)
    ZERO_PASSES_TIMEOUT     the window elapsed with no pass at all (DSN load failure or far too small a window)
    SES_NOT_GENERATED       the engine ended by itself without writing a SES
    SES_CORRUPTED           a SES was written but does not parse / carries no routes
    SES_NOT_IMPROVED        a valid SES that is not better than the checkpoint
    FULL_ROUTING_SUCCESS    0 unrouted
    PARTIAL_ROUTING_SUCCESS a valid, improved SES with unrouted connections left
    ENGINE_IGNORES_LIMITS   more passes ran than planned and no SES: the engine does not honour max_passes
    """
    if status == "TIMEOUT_PARTIAL":
        return "ENGINE_TIMEOUT"
    if ses_generated and ses_valid is False:
        return "SES_CORRUPTED"
    if ses_generated:
        if unrouted_final == 0:
            return "FULL_ROUTING_SUCCESS"
        return "PARTIAL_ROUTING_SUCCESS" if improved else "SES_NOT_IMPROVED"
    if timed_out:
        if passes == 0:
            return "ZERO_PASSES_TIMEOUT"
        if planned_passes is not None and passes > planned_passes:
            return "ENGINE_IGNORES_LIMITS"
        return "CHUNK_TIMEOUT"
    if returncode != 0 and passes == 0:
        return "ENGINE_CRASH"
    if passes == 0:
        return "ENGINE_CRASH"
    return "SES_NOT_GENERATED"
