"""Execution Budgets and Adaptive Concurrency Limits for DESK.
Dynamically sets worker counts, queue bounds, and memory limits based on HardwareProfile.
Zero external dependencies.
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any
from desk.runtime.resource_profile import HardwareProfile, ResourceDetector

@dataclass
class ExecutionBudget:
    tier: str
    max_parallel_pure_cpu: int
    max_parallel_io: int
    max_external_processes: int
    max_cache_entries: int
    max_stdout_buffer_bytes: int
    checkpoint_interval_ops: int
    batch_size_components: int
    throttle_on_memory_pressure: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class BudgetManager:
    """Computes and adapts execution budgets dynamically."""

    @staticmethod
    def derive_budget(profile: HardwareProfile) -> ExecutionBudget:
        if profile.resource_tier == "LOW" or profile.memory_pressure:
            return ExecutionBudget(
                tier="LOW",
                max_parallel_pure_cpu=1,
                max_parallel_io=2,
                max_external_processes=1,
                max_cache_entries=100,
                max_stdout_buffer_bytes=1 * 1024 * 1024,      # 1 MB
                checkpoint_interval_ops=5,
                batch_size_components=20,
                throttle_on_memory_pressure=True
            )
        elif profile.resource_tier == "HIGH":
            return ExecutionBudget(
                tier="HIGH",
                max_parallel_pure_cpu=min(8, max(2, profile.logical_cores // 2)),
                max_parallel_io=8,
                max_external_processes=2,
                max_cache_entries=2000,
                max_stdout_buffer_bytes=8 * 1024 * 1024,      # 8 MB
                checkpoint_interval_ops=50,
                batch_size_components=100,
                throttle_on_memory_pressure=True
            )
        else:  # NORMAL
            return ExecutionBudget(
                tier="NORMAL",
                max_parallel_pure_cpu=min(4, max(1, profile.logical_cores // 2)),
                max_parallel_io=4,
                max_external_processes=1,
                max_cache_entries=500,
                max_stdout_buffer_bytes=2 * 1024 * 1024,      # 2 MB
                checkpoint_interval_ops=20,
                batch_size_components=50,
                throttle_on_memory_pressure=True
            )

    @classmethod
    def get_current_budget(cls) -> ExecutionBudget:
        profile = ResourceDetector.detect()
        return cls.derive_budget(profile)
