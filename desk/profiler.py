"""High-precision performance profiling and telemetry framework for DESK.
Measures wall-clock time, CPU time, memory allocations, and domain-specific counters.
Zero external dependencies.
"""
import time
import tracemalloc
import os
import json
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict

@dataclass
class ProfileRecord:
    operation: str
    wall_ms: float
    cpu_ms: float
    memory_delta_kb: float
    peak_traced_kb: float = 0.0
    operation_id: str = ""
    task_id: str = ""
    board_revision: str = ""
    profile_hash: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    bridge_calls: int = 0
    components_processed: int = 0
    pads_processed: int = 0
    nets_processed: int = 0
    tracks_processed: int = 0
    vias_processed: int = 0
    polygons_processed: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    subprocess_duration_ms: float = 0.0
    exit_status: str = "OK"
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

    def clear(self):
        self.records.clear()
        self.bridge_calls_count = 0
        self.cache_hits_count = 0
        self.cache_misses_count = 0

    def summary(self) -> Dict[str, Any]:
        total_wall = sum(r.wall_ms for r in self.records)
        total_cpu = sum(r.cpu_ms for r in self.records)
        by_op: Dict[str, Dict[str, Any]] = {}
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

        sorted_ops = sorted(by_op.items(), key=lambda x: x[1]["total_wall_ms"], reverse=True)
        return {
            "total_wall_ms": round(total_wall, 2),
            "total_cpu_ms": round(total_cpu, 2),
            "operations": {k: {k2: round(v2, 2) if isinstance(v2, float) else v2 for k2, v2 in v.items()} for k, v in sorted_ops},
            "top_bottlenecks": [k for k, _ in sorted_ops[:5]],
            "total_records": len(self.records)
        }

class ProfileScope:
    """Context manager for profiling a single operation safely."""

    def __init__(self, operation: str, components: int = 0, pads: int = 0, nets: int = 0,
                 tracks: int = 0, vias: int = 0, polygons: int = 0, task_id: str = "",
                 board_revision: str = "", profile_hash: str = "", **meta):
        self.operation = operation
        self.components = components
        self.pads = pads
        self.nets = nets
        self.tracks = tracks
        self.vias = vias
        self.polygons = polygons
        self.task_id = task_id
        self.board_revision = board_revision
        self.profile_hash = profile_hash
        self.meta = meta
        self.collector = TelemetryCollector.get_instance()
        self.operation_id = uuid.uuid4().hex[:8]
        self.start_wall = 0.0
        self.start_cpu = 0.0
        self.start_time = 0.0
        self.b0_calls = 0
        self.h0_hits = 0
        self.m0_misses = 0
        self._was_tracing = False
        self._start_mem = 0

    def __enter__(self):
        self._was_tracing = tracemalloc.is_tracing()
        if not self._was_tracing:
            tracemalloc.start()
        self._start_mem, _ = tracemalloc.get_traced_memory()

        self.b0_calls = self.collector.bridge_calls_count
        self.h0_hits = self.collector.cache_hits_count
        self.m0_misses = self.collector.cache_misses_count
        self.start_time = time.time()
        self.start_cpu = time.process_time()
        self.start_wall = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_wall = time.perf_counter()
        end_cpu = time.process_time()
        end_time = time.time()
        curr_mem, peak_mem = tracemalloc.get_traced_memory()

        if not self._was_tracing:
            tracemalloc.stop()

        wall_ms = (end_wall - self.start_wall) * 1000.0
        cpu_ms = (end_cpu - self.start_cpu) * 1000.0
        mem_delta_kb = (curr_mem - self._start_mem) / 1024.0
        peak_kb = peak_mem / 1024.0

        rec = ProfileRecord(
            operation=self.operation,
            wall_ms=round(wall_ms, 3),
            cpu_ms=round(cpu_ms, 3),
            memory_delta_kb=round(mem_delta_kb, 1),
            peak_traced_kb=round(peak_kb, 1),
            operation_id=self.operation_id,
            task_id=self.task_id,
            board_revision=self.board_revision,
            profile_hash=self.profile_hash,
            start_time=self.start_time,
            end_time=end_time,
            bridge_calls=self.collector.bridge_calls_count - self.b0_calls,
            components_processed=self.components,
            pads_processed=self.pads,
            nets_processed=self.nets,
            tracks_processed=self.tracks,
            vias_processed=self.vias,
            polygons_processed=self.polygons,
            cache_hits=self.collector.cache_hits_count - self.h0_hits,
            cache_misses=self.collector.cache_misses_count - self.m0_misses,
            exit_status="ERROR" if exc_type is not None else "OK",
            metadata=self.meta
        )
        self.collector.add_record(rec)
