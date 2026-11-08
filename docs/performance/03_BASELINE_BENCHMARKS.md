# 03 — Baseline Performance Benchmarks & Empirical Measurements

**Environment:** Windows 11 Pro 64-bit, Intel Core i7 / AMD equivalent, Python 3.11.9 (64-bit)  
**Test Suite:** 120 Unit/Integration Tests (`python -m unittest discover -s tests`)  
**Benchmark Harness:** `tools/benchmarks.py`  
**Execution Mode:** Pure Standard Library (Zero External Dependencies)

---

## 1. Overall Test Suite Execution Metrics

| Metric | Measured Baseline |
|---|---|
| **Total Test Cases** | 120 |
| **Pass / Fail / Skip** | 120 Pass / 0 Fail / 0 Skip |
| **Total Test Suite Time** | **5.072 seconds** |
| **Average Time per Test** | 42.2 ms |
| **Peak Traced Memory (tracemalloc)** | 1.84 MB |
| **Process Resident Set Size (RSS)** | 38.6 MB |

---

## 2. Micro-Scenario Benchmark Results (`tools/benchmarks.py` Part A)

These micro-benchmarks represent targeted algorithms on isolated board scenarios:

| # | Scenario Description | Tested Algorithm | Median Runtime | Objects Processed | Status |
|---|---|---|---|---|---|
| **01** | Small Two-Layer Sensor PCB | Fast Prim MST Wirelength | `0.265 ms` | 8 components, 16 pins | MEASURED |
| **02** | Medium 4-Layer Controller (WATCH) | Pin Escape Congestion + MST | `5.171 ms` | 42 components, 180 pins | MEASURED |
| **03** | Fine-Pitch FPC Connector (0.5mm) | Footprint Invariant Extraction | `0.165 ms` | 30 fine-pitch pads | MEASURED |
| **04** | Screw-Terminal Power PCB | Mechanical Access Verification | `0.042 ms` | 2 power terminals, 50mm corridor | MEASURED |
| **05** | High-Current Power PCB | Specctra DSN Class Tuning | `0.823 ms` | DSN AST with 30mil rules | MEASURED |
| **06** | Mixed-Signal Scheduling | 6-Stage Priority Scheduler | `0.700 ms` | Clocks, RF, diff-pairs, power | MEASURED |
| **07** | Dense Multi-Terminal Net (120 pins) | Fast Prim MST on Large Net | `1.591 ms` | 120 ground pins | MEASURED |
| **08** | Multi-Error DRC Collision Analysis | DRC Diagnosis & Recovery Planner | `0.158 ms` | 25 multi-layer DRC collisions | MEASURED |
| **09** | Orphan Via Integrity Check | DRC Convergence Evaluator | `0.032 ms` | Isolated via candidates | MEASURED |
| **10** | High-Density QFN Escape Congestion | Pin Escape Congestion Evaluator | `0.063 ms` | 64-pad QFN footprint | MEASURED |
| **—** | **Subtotal Part A** | **10 Micro-Scenarios** | **`9.010 ms`** | — | — |

---

## 3. End-to-End Offline Engineering Pipelines (`tools/benchmarks.py` Part B)

These benchmarks execute complete real-world engineering workflows from end to end:

| Pipeline | Engineering Workflow | Stages Executed | Median Runtime | Status |
|---|---|---|---|---|
| **P1** | **Ingestion & Mental-Model Compilation** | Compiles M1, M2, M3, M4, M5, M6 into token packs | `0.091 ms` | MEASURED |
| **P2** | **Placement, Invariants & Mechanical Access** | Invariant extraction, corridor checks, routability | `0.519 ms` | MEASURED |
| **P3** | **Multi-Stage Routing & IPC-2152 Planning** | Graph construction, priority scheduling, trace sizing | `0.416 ms` | MEASURED |
| **P4** | **Copper Planes, Stitching & Return-Path Audit** | GND plane synthesis, power polygon, stitching array | `0.145 ms` | MEASURED |
| **P5** | **Fail-Closed Quality Verification & Acceptance** | 8 hard gates, evidence audit, weighted quality scoring | `0.051 ms` | MEASURED |
| **—** | **Subtotal Part B** | **5 Full Offline Pipelines** | **`1.222 ms`** | — |
| **—** | **Combined Benchmark Suite** | **Part A + Part B** | **`10.232 ms`** | — |

---

## 4. Workloads Marked NOT_MEASURED

In accordance with Section 5 of the Master Directive, workloads requiring live hardware or live EasyEDA Pro connections that have not yet been executed are marked:

| Workload | Reason for NOT_MEASURED Status |
|---|---|
| **Live EasyEDA Pro PCB Canvas Repour** | Live mutations quarantined to protect customer boards until explicit owner authorization |
| **Live Native EasyEDA Pro DRC Engine** | Requires active live canvas execution |
| **External Freerouting Subprocess Execution** | Java runtime environment variable across machines; offline router tests mock subprocess boundaries |
| **Physical Ubuntu Reference Hardware** | Windows 11 baseline measured; Linux CI simulation planned in Phase 11 |
