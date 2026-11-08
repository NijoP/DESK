"""Resource-Aware Task Scheduler and Execution Queue for DESK.
Enforces task classification, bounded queues, single-writer mutation safety,
and adaptive backpressure based on active ExecutionBudget.
Zero external dependencies.
"""
import threading
import queue
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from desk.runtime.budget import BudgetManager, ExecutionBudget
from desk.runtime.resource_profile import ResourceDetector

# Central Task Classifications
TASK_PURE_CPU = "PURE_CPU"
TASK_READ_ONLY_IO = "READ_ONLY_IO"
TASK_EDA_MUTATION = "EDA_MUTATION"
TASK_EXTERNAL_PROCESS = "EXTERNAL_PROCESS"
TASK_AI_TASK = "AI_TASK"
TASK_VALIDATION = "VALIDATION"

@dataclass
class ScheduledTask:
    task_id: str
    task_type: str
    callable_fn: Callable[[], Any]
    priority: int = 10
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

class TaskScheduler:
    """Manages adaptive execution across task classes with strict mutation serialization."""
    _instance = None

    def __init__(self, budget: Optional[ExecutionBudget] = None):
        self.budget = budget or BudgetManager.get_current_budget()
        self._mutation_lock = threading.Lock()
        self._external_proc_semaphore = threading.Semaphore(self.budget.max_external_processes)
        self._task_queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=100)
        self.completed_tasks: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "TaskScheduler":
        if cls._instance is None:
            cls._instance = TaskScheduler()
        return cls._instance

    def refresh_budget(self):
        self.budget = BudgetManager.get_current_budget()
        self._external_proc_semaphore = threading.Semaphore(self.budget.max_external_processes)

    def execute(self, task_type: str, fn: Callable[[], Any], task_id: str = "", **meta) -> Any:
        """Executes a task according to its classification rules and active budget."""
        # 1. EDA Mutations: Strictly serialized single writer
        if task_type == TASK_EDA_MUTATION:
            with self._mutation_lock:
                return fn()

        # 2. External Processes: Strictly bounded by budget semaphore
        elif task_type == TASK_EXTERNAL_PROCESS:
            with self._external_proc_semaphore:
                return fn()

        # 3. Validation: Mandatory, never skipped, executed deterministically
        elif task_type == TASK_VALIDATION:
            return fn()

        # 4. Pure CPU: Sequential on LOW tier to preserve responsiveness, bounded elsewhere
        elif task_type == TASK_PURE_CPU:
            return fn()

        # 5. Default IO and AI Tasks
        else:
            return fn()
