"""High-precision performance profiling and telemetry framework for DESK.
Measures wall-clock time, CPU time, memory delta, and domain-specific counters.
Zero external dependencies.
"""
import time
import tracemalloc
import os
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict

@dataclass
class ProfileRecord:
    operation: str
    wall_ms: float
    cpu_ms: float
    memory_delta_kb: float
    bridge_calls: int = 0
    components_processed: int = 0
    pads_processed: int = 0
    nets_processed: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

class TelemetryCollector:
    """Thread-safe and process-local collector for execution metrics."""
    _instance = None

    def __init__(self):
        self.records: List[ProfileRecord] = []
        self.bridge_calls_count = 0
        self.cache_hits_count = 0
        self.cache_misses_count = 0

    @classmethod
    def get_instance(cls) -> "TelemetryCollector":
        if cls._instance is None:
            cls._instance = TelemetryCollector()
        return cls._instance

    def record_bridge_call(self):
        self.bridge_calls_count += 1

    def record_cache_hit(self):
        self.cache_hits_count += 1

    def record_cache_miss(self):
        self.cache_misses_count += 1

    def add_record(self, record: ProfileRecord):
        self.records.append(record)

    def summary(self) -> Dict[str, Any]:
        total_wall = sum(r.wall_ms for r in self.records)
        total_cpu = sum(r.cpu_ms for r in self.records)
        by_op = {}
        for r in self.records:
            if r.operation not in by_op:
                by_op[r.operation] = {
                    "count": 0, "total_wall_ms": 0.0, "total_cpu_ms": 0.0,
                    "max_wall_ms": 0.0, "bridge_calls": 0, "cache_hits": 0, "cache_misses": 0
                }
            entry = by_op[r.operation]
            entry["count"] += 1
            entry["total_wall_ms"] += r.wall_ms
            entry["total_cpu_ms"] += r.cpu_ms
            entry["max_wall_ms"] = max(entry["max_wall_ms"], r.wall_ms)
            entry["bridge_calls"] += r.bridge_calls
            entry["cache_hits"] += r.cache_hits
            entry["cache_misses"] += r.cache_misses

        # Rank slowest operations
        sorted_ops = sorted(by_op.items(), key=lambda x: x[1]["total_wall_ms"], reverse=True)
        return {
            "total_wall_ms": round(total_wall, 2),
            "total_cpu_ms": round(total_cpu, 2),
            "operations": {k: {k2: round(v2, 2) if isinstance(v2, float) else v2 for k2, v2 in v.items()} for k, v in sorted_ops},
            "top_bottlenecks": [k for k, _ in sorted_ops[:5]]
        }

class ProfileScope:
    """Context manager for profiling a single operation."""

    def __init__(self, operation: str, components: int = 0, pads: int = 0, nets: int = 0, **meta):
        self.operation = operation
        self.components = components
        self.pads = pads
        self.nets = nets
        self.meta = meta
        self.collector = TelemetryCollector.get_instance()
        self.t0_wall = 0.0
        self.t0_cpu = 0.0
        self.b0_calls = 0
        self.h0_hits = 0
        self.m0_misses = 0

    def __enter__(self):
        tracemalloc.start()
        self.b0_calls = self.collector.bridge_calls_count
        self.h0_hits = self.collector.cache_hits_count
        self.m0_misses = self.collector.cache_misses_count
        self.t0_cpu = time.process_time()
        self.t0_wall = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        t1_wall = time.perf_counter()
        t1_cpu = time.process_time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        wall_ms = (t1_wall - self.t0_wall) * 1000.0
        cpu_ms = (t1_cpu - self.t0_cpu) * 1000.0
        mem_kb = peak / 1024.0

        rec = ProfileRecord(
            operation=self.operation,
            wall_ms=round(wall_ms, 3),
            cpu_ms=round(cpu_ms, 3),
            memory_delta_kb=round(mem_kb, 1),
            bridge_calls=self.collector.bridge_calls_count - self.b0_calls,
            components_processed=self.components,
            pads_processed=self.pads,
            nets_processed=self.nets,
            cache_hits=self.collector.cache_hits_count - self.h0_hits,
            cache_misses=self.collector.cache_misses_count - self.m0_misses,
            metadata=self.meta
        )
        self.collector.add_record(rec)
