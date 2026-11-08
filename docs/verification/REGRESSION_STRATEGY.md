# Regression Test Strategy & Quality Assurance Framework

## 1. Principles of Verification

The DESK test and regression strategy guarantees engineering correctness, cross-platform portability, and runtime reliability across all supported hardware configurations without external dependencies:

1. **Zero External Dependencies**: All core tests run via Python's standard `unittest` framework without requiring third-party packages.
2. **Offline Safety**: No live EasyEDA Pro API calls are permitted during standard test execution. All EDA interactions are validated against offline mock adapters, serialized JSON fixtures, and synthetic boards.
3. **Hardware Independence**: Tests must pass deterministically whether executed on a dual-core 8 GB laptop or a 64 GB workstation.
4. **Performance Regression Gates**: Benchmarks run continuously to catch algorithmic regressions ($O(N^2)$ distance checks, unnecessary snapshot deepcopies, or unindexed polygon intersections).

---

## 2. Test Suite Organization

```
tests/
├── test_01_profile.py               # IPC-2152 trace calculations, net classes
├── test_02_mental_model.py          # Functional partitioning, cluster rules
├── test_03_schematic_compiler.py    # Pin mapping, schematic syntax validation
├── test_04_bridge_mock.py           # Mock EasyEDA bridge socket communication
├── test_05_capability_router.py     # Task routing to M1-M6 engines
├── test_06_placement_planner.py     # Decoupling cap & thermal cluster placement
├── test_07_copper_engine.py         # Power polygons, ground planes, void checks
├── test_08_quality_gates.py         # 5-state gate engine, fail-closed evidence
├── test_09_decision_memory.py       # Engineering decision memory & recall
├── test_10_offline_copper_ops.py    # Polygon decomposition, island pruning
├── test_11_easyeda_pcb_adapter.py   # Batch readback & mutation payload building
├── test_runtime_platform.py         # Hardware detection, scheduler, checkpoints
├── test_skills_system.py            # Frontmatter parsing, conditional loader
├── test_operation_registry.py       # Operation validation, safety policies
├── test_durable_inbox_and_tasks.py  # 12-state task machine, inbox deduplication
└── test_captain_firstmate_personality.py # Greeting filter, Captain approval boundaries
```

---

## 3. Benchmark Gates & Metrics

DESK maintains reproducible benchmarks executed via `tools/benchmarks.py`:

- **Spatial Grid Query**: $\le 1.0$ ms for 1,000 components.
- **Trace Width Calculation**: $\le 0.05$ ms per net.
- **Multi-Domain Fingerprinting**: $\le 0.5$ ms for full PCB snapshot.
- **Full Pipeline Verification (M1–M6)**: $\le 10$ ms offline for standard mixed-signal boards.
- **Memory Footprint**: Memory delta $\le 25$ MB during end-to-end routing and copper synthesis on mainstream hardware.
