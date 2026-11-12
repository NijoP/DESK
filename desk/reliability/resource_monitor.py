"""Resource budgets and monitoring without external dependencies.

A `ResourceBudget` bounds one operation or project run: a deadline, a maximum process RSS, a maximum number of child
processes. `ResourceMonitor.sample()` reads what the OS offers (ctypes on Windows, `resource` on POSIX) and never
raises; `check(budget)` says whether the budget is still respected so a supervisor can cancel a run instead of letting
it consume the host. Zero external dependencies.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


def process_rss_mb(pid: Optional[int] = None) -> Optional[float]:
    """Resident set size of this process in MB, or None when the platform offers no cheap way to read it."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            h = ctypes.windll.kernel32.GetCurrentProcess() if pid is None else ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
            if pid is not None:
                ctypes.windll.kernel32.CloseHandle(h)
            return round(pmc.WorkingSetSize / (1024 * 1024), 1) if ok else None
        import resource
        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(ru / 1024.0, 1) if sys.platform != "darwin" else round(ru / (1024 * 1024), 1)
    except Exception:
        return None


@dataclass
class ResourceBudget:
    name: str
    deadline_s: Optional[float] = None          # seconds from `started`
    max_rss_mb: Optional[float] = None
    max_children: Optional[int] = None
    max_recovery_attempts: int = 3
    started: float = field(default_factory=time.time)

    def remaining_s(self, now: Optional[float] = None) -> Optional[float]:
        if self.deadline_s is None:
            return None
        return max(0.0, self.deadline_s - ((now or time.time()) - self.started))


@dataclass
class ResourceSample:
    ts: float
    rss_mb: Optional[float]
    cpu_count: int
    children: int
    load: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"ts": self.ts, "rss_mb": self.rss_mb, "cpu_count": self.cpu_count, "children": self.children, "load": self.load}


class ResourceMonitor:
    def __init__(self, children: Optional[Callable[[], int]] = None, now: Callable[[], float] = time.time):
        self._children = children or (lambda: 0)
        self.now = now
        self.samples: List[ResourceSample] = []

    def sample(self) -> ResourceSample:
        load = None
        try:
            load = os.getloadavg()[0]   # POSIX only
        except Exception:
            pass
        s = ResourceSample(self.now(), process_rss_mb(), os.cpu_count() or 1, int(self._children()), load)
        self.samples.append(s)
        if len(self.samples) > 200:
            del self.samples[:-200]
        return s

    def check(self, budget: ResourceBudget) -> Dict[str, Any]:
        s = self.sample()
        problems: List[str] = []
        rem = budget.remaining_s(s.ts)
        if rem is not None and rem <= 0:
            problems.append(f"deadline of {budget.deadline_s:.0f}s exceeded")
        if budget.max_rss_mb is not None and s.rss_mb is not None and s.rss_mb > budget.max_rss_mb:
            problems.append(f"rss {s.rss_mb} MB > {budget.max_rss_mb} MB")
        if budget.max_children is not None and s.children > budget.max_children:
            problems.append(f"{s.children} child processes > {budget.max_children}")
        return {"within_budget": not problems, "problems": problems, "sample": s.to_dict(), "remaining_s": rem}


class ChildProcessRegistry:
    """Tracks the child processes a run started so a cancelled run can clean up only its own tree."""
    def __init__(self) -> None:
        self.pids: Dict[int, str] = {}

    def register(self, pid: int, label: str) -> None:
        self.pids[int(pid)] = label

    def forget(self, pid: int) -> None:
        self.pids.pop(int(pid), None)

    def alive(self) -> List[int]:
        from desk.ops import is_process_alive
        return [p for p in self.pids if is_process_alive(p)]

    def terminate_all(self) -> List[int]:
        from desk.runtime.process_guard import kill_process_tree
        killed = []
        for p in list(self.pids):
            try:
                kill_process_tree(p)
                killed.append(p)
            except Exception:
                pass
            self.pids.pop(p, None)
        return killed
