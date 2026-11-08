# 05 — Phased Implementation Roadmap

This document outlines the sequenced implementation plan for universal performance, resource efficiency, and correctness in DESK.

---

## 1. Prioritized Implementation Sequence

```
P0: Correctness & Verification Foundation
    ├── 5-State Evidence Lifecycle (PASS, FAIL, UNKNOWN, NOT_RUN, STALE)
    ├── Atomic Single-Writer Mutex & Process Liveness Detection
    └── Complete PCB Snapshot Fingerprint & Domain Revisions
         │
         ▼
P1: Adaptive Resource Management
    ├── Hardware Detection (CPU Cores, RAM, Memory Pressure, OS Detection)
    ├── Execution Budgets (LOW_RESOURCE, NORMAL_RESOURCE, HIGH_RESOURCE)
    └── Task-Classified Scheduler (Bounded Queues, Single Serialized Writer)
         │
         ▼
P2: Spatial Geometry & Incremental Optimization
    ├── 2D Spatial Grid Indexing for Clearance & Keepout Queries
    ├── Incremental Snapshot Updating (Incremental Equivalence to Full Rebuild)
    └── Bounded Subprocess Execution with Ring Buffer Output
         │
         ▼
P3: Testing, Benchmarking & Rust/TypeScript Decision
    ├── Differential & Property-Based Verification
    ├── Multi-Resource Mode Simulation Tests
    └── Empirical Evaluation of Selective Rust Acceleration & TypeScript
```

---

## 2. Detailed Task Breakdown & Target Files

| Phase | Subsystem | Action Items | Primary Files |
|---|---|---|---|
| **P0** | **Quality Gates** | Implement 5-state gate lifecycle; unknown/stale fail-closed; exception tracking | `desk/quality.py` |
| **P0** | **Mutation Safety** | Atomic `O_CREAT \| O_EXCL` lock; PID liveness detection; op classifications | `desk/ops.py` |
| **P0** | **Snapshot** | Full fingerprint (tracks, vias, zones, stackup, rules); domain revision invalidation | `desk/snapshot.py` |
| **P1** | **Resource Detection** | CPU logical cores, available RAM, memory pressure, OS detection | `desk/runtime/resource_profile.py` |
| **P1** | **Execution Budgets** | Dynamic sizing for workers, cache, batch size, checkpoints | `desk/runtime/budget.py` |
| **P1** | **Task Scheduler** | Bounded queues; PURE_CPU, READ_ONLY_IO, EDA_MUTATION, VALIDATION | `desk/runtime/scheduler.py` |
| **P2** | **Spatial Index** | Spatial grid partitioning for clearance and obstacle intersection | `desk/spatial.py` or `desk/snapshot.py` |
| **P2** | **Subprocess Safety** | Bounded output buffer, timeouts, graceful termination | `desk/runtime/process_guard.py` |
| **P3** | **Validation** | Resource simulation tests, differential tests, property tests | `tests/test_resource_management.py`, `tests/test_spatial_index.py` |

---

## 3. Policy on Rust and TypeScript

### Rust Evaluation
- **Principle**: Optimize Python algorithms and data structures first.
- **Criteria**: Introduce Rust via PyO3 only if a CPU-bound hotspot demonstrates $\ge 3\times$ speedup and $\ge 15\text{--}20\%$ end-to-end workflow acceleration without requiring end-users to install Rust tools.
- **Current Observation**: Python standard library executes 10 benchmark scenarios in 9.0 ms and 5 complete engineering pipelines in 1.2 ms. Pure Python remains the reference platform until large-scale geometric clearance bottlenecks in 5,000+ pad boards justify native compilation.

### TypeScript Evaluation
- **Principle**: Do not duplicate core engineering logic into TypeScript.
- **Decision**: Keep Python as the single authoritative engineering plane. TypeScript is reserved for future browser/React desktop UI or MCP transport layers where native Node.js environments are natural, but engineering rules remain in Python.
