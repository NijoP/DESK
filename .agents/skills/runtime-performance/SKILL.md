---
name: runtime-performance
description: Resource-aware execution, sub-10ms pipeline benchmarks, bounded concurrency, and memory safety.
triggers:
  - "performance"
  - "benchmark"
  - "latency"
  - "memory usage"
  - "profiling"
  - "sub-10ms"
inputs:
  pipeline_stage: string
  concurrency_limit: integer
outputs:
  execution_time_ms: float
  memory_peak_mb: float
  benchmark_passed: boolean
authoritative_pipeline: INFRA
replay_safety: READ_ONLY
---

# Runtime Performance Skill

## Purpose
Enforces sub-10ms execution budgets, bounded memory consumption, efficient caching, and low-latency performance across DESK algorithms on resource-constrained hardware.

## When to Use
- Profiling and optimizing placement, routing, or polygon synthesis engines.
- Benchmarking tool runtime against regression thresholds.
- Investigating memory leaks, excessive GC pressure, or unbounded concurrency.

## Required Inputs
- Target module or pipeline function to profile.
- Hardware baseline limits (e.g. single-threaded budget $< 10\,\text{ms}$).

## Relevant DESK Modules
- `tools/benchmarks.py`: Automated performance regression harness.
- `desk/profile.py`, `desk/router.py`, `desk/copper.py`.

## Required Engineering Constraints
- Latency Budget: Core routing and placement calculations must execute in under $10\,\text{ms}$ on commodity hardware.
- Measured Over Estimated: Never report estimated benchmarks as measured benchmarks; record physical wall-clock timings.
- Zero Memory Leaks: Ensure transient calculation buffers (grids, raycast caches) are deallocated promptly.
- Low-End Hardware Compatibility: Algorithms must not assume GPU acceleration or massive RAM availability.

## Recommended Workflow
1. Isolate target algorithm in benchmark harness.
2. Warm up JIT/bytecode compilation passes.
3. Measure wall-clock execution time across 100 iterations.
4. Profile memory allocation peaks and object counts.
5. If latency $> 10\,\text{ms}$, optimize critical inner loops (e.g. spatial indexing, spatial hashing).

## Validation Steps
- Execute automated benchmarks: `python tools/benchmarks.py`.
- Run performance test suite: `python -m unittest tests/test_benchmark_performance.py`.

## Failure Conditions & Recovery
- Benchmark regression: Revert speculative code; optimize memory allocations and vector operations.
- Socket discovery latency spike: Ensure socket timeouts are capped at 50ms per port.

## Expected Output
- Empirical performance profile certifying execution latency $< 10\,\text{ms}$ and peak memory within bounds.

## Documentation References
- [Performance Architecture](file:///docs/performance/00_PERFORMANCE_SPEC.md)
