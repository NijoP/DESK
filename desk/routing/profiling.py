"""Subsystem Seven: Execution Time Optimization and Phase Instrumentation.
Measures wall-clock time across all 20 canonical routing phases, distinguishing CPU time
from IPC latency, external process startup, file I/O, and wait time.
Zero external dependencies.
"""
from __future__ import annotations
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


PHASE_NAMES = [
    "1. Board snapshot acquisition",
    "2. Netlist and geometry extraction",
    "3. Geometry normalization",
    "4. Constraint compilation",
    "5. Pad escape analysis",
    "6. Congestion analysis",
    "7. Routing-plan generation",
    "8. DSN export",
    "9. DSN parsing and transformation",
    "10. External engine startup",
    "11. Fanout execution",
    "12. Autorouting passes",
    "13. Route optimization",
    "14. SES output",
    "15. SES import",
    "16. Power-trace width transition",
    "17. EasyEDA readback",
    "18. DRC",
    "19. Connectivity verification",
    "20. Final report generation"
]


@dataclass
class PhaseTimingRecord:
    phase_id: int
    name: str
    start_ts: float
    end_ts: float = 0.0
    duration_ms: float = 0.0
    category: str = "CPU"  # "CPU", "IPC", "PROCESS", "IO", "DRC"


@dataclass
class RoutingExecutionProfile:
    """Complete wall-clock execution profile across all phases."""
    total_wall_clock_sec: float
    phase_timings: List[PhaseTimingRecord]
    category_breakdown_ms: Dict[str, float]
    slowest_phase: str
    target_180s_met: bool
    summary_report: str


class RoutingProfiler:
    """Context-managed stopwatch for fine-grained routing phase measurements."""

    def __init__(self):
        self.t_start = time.time()
        self.records: List[PhaseTimingRecord] = []
        self._current_phase: Optional[PhaseTimingRecord] = None

    def start_phase(self, phase_id: int, category: str = "CPU") -> None:
        """Starts timing a specific phase."""
        if self._current_phase:
            self.end_phase()
        name = PHASE_NAMES[phase_id - 1] if 1 <= phase_id <= len(PHASE_NAMES) else f"Phase {phase_id}"
        self._current_phase = PhaseTimingRecord(
            phase_id=phase_id,
            name=name,
            start_ts=time.time(),
            category=category
        )

    def end_phase(self) -> None:
        """Stops timing current phase and appends record."""
        if not self._current_phase:
            return
        end_t = time.time()
        self._current_phase.end_ts = end_t
        self._current_phase.duration_ms = round((end_t - self._current_phase.start_ts) * 1000.0, 2)
        self.records.append(self._current_phase)
        self._current_phase = None

    def finish(self) -> RoutingExecutionProfile:
        """Finalizes profile and generates metrics breakdown."""
        if self._current_phase:
            self.end_phase()
        total_sec = round(time.time() - self.t_start, 3)

        breakdown: Dict[str, float] = {}
        for r in self.records:
            breakdown[r.category] = round(breakdown.get(r.category, 0.0) + r.duration_ms, 2)

        slowest = max(self.records, key=lambda r: r.duration_ms) if self.records else None
        slowest_name = f"{slowest.name} ({slowest.duration_ms:.1f}ms)" if slowest else "None"
        target_met = total_sec <= 180.0

        lines = [
            f"=== ROUTING EXECUTION PROFILE ({total_sec:.2f}s total) ===",
            f"Target 180s Met: {'YES' if target_met else 'NO'}",
            f"Slowest Phase: {slowest_name}",
            "Category Breakdown:",
        ]
        for cat, ms in breakdown.items():
            pct = round((ms / max(1.0, total_sec * 1000.0)) * 100.0, 1)
            lines.append(f"  - {cat:10s}: {ms:8.1f} ms ({pct:4.1f}%)")
        lines.append("Phase Timings:")
        for r in self.records:
            lines.append(f"  [{r.phase_id:02d}] {r.name:36s} | {r.category:7s} | {r.duration_ms:8.1f} ms")

        return RoutingExecutionProfile(
            total_wall_clock_sec=total_sec,
            phase_timings=self.records,
            category_breakdown_ms=breakdown,
            slowest_phase=slowest_name,
            target_180s_met=target_met,
            summary_report="\n".join(lines)
        )
