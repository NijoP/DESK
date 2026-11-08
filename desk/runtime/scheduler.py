"""Resource-Aware Task Scheduler and Execution Queue for DESK.
Enforces task classification, bounded queues, single-writer mutation safety,
priority-aware dispatch, bounded concurrency pools, dependency resolution,
backpressure, and adaptive execution budgets.
Zero external dependencies.
"""
from __future__ import annotations

import enum
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from desk.runtime.budget import BudgetManager, ExecutionBudget

# Central Task Classifications
TASK_PURE_CPU = "PURE_CPU"
TASK_READ_ONLY_IO = "READ_ONLY_IO"
TASK_EDA_MUTATION = "EDA_MUTATION"
TASK_EXTERNAL_PROCESS = "EXTERNAL_PROCESS"
TASK_AI_TASK = "AI_TASK"
TASK_VALIDATION = "VALIDATION"


class TaskPriority(int, enum.Enum):
    URGENT = 1
    HIGH = 3
    NORMAL = 5
    LOW = 10


@dataclass(order=True)
class PrioritizedTask:
    priority: int
    created_at: float = field(compare=True)
    task_id: str = field(compare=False)
    task_type: str = field(compare=False)
    fn: Callable[[], Any] = field(compare=False)
    dependencies: List[str] = field(default_factory=list, compare=False)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class TaskExecutionRecord:
    task_id: str
    task_type: str
    priority: int
    state: str  # "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None
    wait_time_ms: Optional[float] = None
    completion_event: threading.Event = field(default_factory=threading.Event)


class QueueBackpressureError(RuntimeError):
    """Raised when scheduler task queue is at capacity."""
    pass


class TaskDependencyError(RuntimeError):
    """Raised when a task dependency fails or is cancelled."""
    pass


class TaskScheduler:
    """Manages adaptive execution across task classes with strict concurrency bounds."""
    _instance: Optional["TaskScheduler"] = None

    def __init__(self, budget: Optional[ExecutionBudget] = None, max_queue_depth: Optional[int] = None):
        self.budget: ExecutionBudget = budget or BudgetManager.get_current_budget()
        self.max_queue_depth: int = max_queue_depth or self.budget.max_queue_depth or 100

        self._task_queue: queue.PriorityQueue[PrioritizedTask] = queue.PriorityQueue(maxsize=self.max_queue_depth)
        self._records: Dict[str, TaskExecutionRecord] = {}
        self._records_lock = threading.Lock()

        # Concurrency bounds
        self._mutation_lock = threading.Lock()
        self._cpu_semaphore = threading.Semaphore(max(1, self.budget.concurrency_limit))
        self._io_semaphore = threading.Semaphore(max(2, self.budget.concurrency_limit * 2))
        self._external_proc_semaphore = threading.Semaphore(max(1, self.budget.max_external_processes))

        # Worker threadpool
        self._running = True
        self._num_workers = max(1, self.budget.concurrency_limit)
        self._workers: List[threading.Thread] = []
        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker_loop, name=f"DESK-Worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    @classmethod
    def get_instance(cls) -> "TaskScheduler":
        if cls._instance is None:
            cls._instance = TaskScheduler()
        return cls._instance

    def refresh_budget(self) -> None:
        """Refreshes concurrency semaphores based on current system resource tier."""
        self.budget = BudgetManager.get_current_budget()
        self._cpu_semaphore = threading.Semaphore(max(1, self.budget.concurrency_limit))
        self._io_semaphore = threading.Semaphore(max(2, self.budget.concurrency_limit * 2))
        self._external_proc_semaphore = threading.Semaphore(max(1, self.budget.max_external_processes))

    def submit(
        self,
        task_type: str,
        fn: Callable[[], Any],
        task_id: str = "",
        priority: int = TaskPriority.NORMAL,
        dependencies: Optional[List[str]] = None,
        **meta,
    ) -> str:
        """Submits a task into the bounded priority queue. Raises QueueBackpressureError if full."""
        tid = task_id or f"tsk_{uuid.uuid4().hex[:8]}"
        deps = dependencies or []

        record = TaskExecutionRecord(
            task_id=tid,
            task_type=task_type,
            priority=priority,
            state="QUEUED",
        )
        with self._records_lock:
            self._records[tid] = record

        item = PrioritizedTask(
            priority=priority,
            created_at=time.time(),
            task_id=tid,
            task_type=task_type,
            fn=fn,
            dependencies=deps,
            metadata=meta,
        )

        try:
            self._task_queue.put_nowait(item)
        except queue.Full:
            with self._records_lock:
                record.state = "FAILED"
                record.error = "Queue capacity reached (backpressure)"
            raise QueueBackpressureError(f"Task queue depth {self.max_queue_depth} exceeded. Backpressure active.")

        return tid

    def execute(
        self,
        task_type: str,
        fn: Callable[[], Any],
        task_id: str = "",
        priority: int = TaskPriority.NORMAL,
        dependencies: Optional[List[str]] = None,
        timeout_s: float = 60.0,
        **meta,
    ) -> Any:
        """Synchronously executes or awaits a submitted task, adhering to all bounds and dependencies."""
        # Validation tasks MUST ALWAYS execute unconditionally
        if task_type == TASK_VALIDATION and not dependencies:
            return fn()

        tid = self.submit(task_type, fn, task_id=task_id, priority=priority, dependencies=dependencies, **meta)
        rec = self.get_record(tid)
        if not rec:
            raise RuntimeError(f"Record for task {tid} vanished.")

        completed = rec.completion_event.wait(timeout=timeout_s)
        if not completed:
            self.cancel_task(tid)
            raise TimeoutError(f"Task '{tid}' timed out after {timeout_s}s waiting for execution.")

        if rec.state == "COMPLETED":
            return rec.result
        elif rec.state == "CANCELLED":
            raise RuntimeError(f"Task '{tid}' was cancelled.")
        else:
            raise RuntimeError(f"Task '{tid}' failed: {rec.error}")

    def cancel_task(self, task_id: str) -> bool:
        """Cancels a queued task."""
        with self._records_lock:
            rec = self._records.get(task_id)
            if rec and rec.state == "QUEUED":
                rec.state = "CANCELLED"
                rec.completion_event.set()
                return True
        return False

    def get_record(self, task_id: str) -> Optional[TaskExecutionRecord]:
        with self._records_lock:
            return self._records.get(task_id)

    def _worker_loop(self) -> None:
        while self._running:
            try:
                task = self._task_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            rec = self.get_record(task.task_id)
            if not rec or rec.state == "CANCELLED":
                self._task_queue.task_done()
                continue

            # Check dependencies
            dep_failed = False
            for dep_id in task.dependencies:
                dep_rec = self.get_record(dep_id)
                if not dep_rec:
                    continue
                # Wait for dependency to finish
                dep_rec.completion_event.wait(timeout=30.0)
                if dep_rec.state != "COMPLETED":
                    dep_failed = True
                    break

            if dep_failed:
                with self._records_lock:
                    rec.state = "FAILED"
                    rec.error = f"Dependency failure on task {task.task_id}"
                rec.completion_event.set()
                self._task_queue.task_done()
                continue

            # Mark running
            now = time.time()
            with self._records_lock:
                rec.state = "RUNNING"
                rec.started_at = now
                rec.wait_time_ms = round((now - rec.created_at) * 1000.0, 2)

            t0 = time.perf_counter()
            result = None
            err_msg = None

            try:
                # Concurrency bound gating
                if task.task_type == TASK_EDA_MUTATION:
                    with self._mutation_lock:
                        result = task.fn()
                elif task.task_type == TASK_EXTERNAL_PROCESS:
                    with self._external_proc_semaphore:
                        result = task.fn()
                elif task.task_type == TASK_PURE_CPU:
                    with self._cpu_semaphore:
                        result = task.fn()
                elif task.task_type == TASK_READ_ONLY_IO:
                    with self._io_semaphore:
                        result = task.fn()
                else:
                    result = task.fn()

                with self._records_lock:
                    rec.state = "COMPLETED"
                    rec.result = result
            except BaseException as e:
                err_msg = str(e)
                with self._records_lock:
                    rec.state = "FAILED"
                    rec.error = err_msg
            finally:
                t1 = time.perf_counter()
                with self._records_lock:
                    rec.completed_at = time.time()
                    rec.duration_ms = round((t1 - t0) * 1000.0, 2)
                rec.completion_event.set()
                self._task_queue.task_done()

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides structured scheduler telemetry for auditing and diagnostics."""
        with self._records_lock:
            all_records = list(self._records.values())

        completed = [r for r in all_records if r.state == "COMPLETED" and r.duration_ms is not None]
        durations = sorted([r.duration_ms for r in completed if r.duration_ms is not None])
        wait_times = sorted([r.wait_time_ms for r in completed if r.wait_time_ms is not None])

        def _p50(data): return data[len(data) // 2] if data else 0.0
        def _p95(data): return data[int(len(data) * 0.95)] if data else 0.0

        return {
            "total_submitted": len(all_records),
            "completed_count": len(completed),
            "failed_count": sum(1 for r in all_records if r.state == "FAILED"),
            "cancelled_count": sum(1 for r in all_records if r.state == "CANCELLED"),
            "current_queue_depth": self._task_queue.qsize(),
            "max_queue_depth": self.max_queue_depth,
            "concurrency_limit": self.budget.concurrency_limit,
            "duration_p50_ms": _p50(durations),
            "duration_p95_ms": _p95(durations),
            "wait_time_p50_ms": _p50(wait_times),
            "wait_time_p95_ms": _p95(wait_times),
        }

    def shutdown(self, wait: bool = True) -> None:
        self._running = False
        if wait:
            for t in self._workers:
                t.join(timeout=1.0)
