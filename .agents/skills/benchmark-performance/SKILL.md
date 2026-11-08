---
name: benchmark-performance
description: Procedural workflow for running latency, memory, and spatial indexing benchmarks across hardware tiers.
triggers:
  - "benchmark"
  - "performance"
  - "profiling"
  - "latency"
  - "throughput"
  - "speed"
inputs:
  suite_name: string
  iterations: integer
outputs:
  benchmark_metrics: dict
  hardware_tier: string
  regressions_detected: boolean
authoritative_pipeline: Runtime
replay_safety: SAFE_READ
---

# Benchmark Performance Skill

## Purpose
Benchmarks core computational algorithms (spatial indexing, trace width calculation, snapshot fingerprinting, full pipeline) to verify compliance with latency budgets.

## Procedural Execution Checklist

1. **Hardware Tier Identification**:
   - Query `desk.runtime.resource_profile.detect_resource_profile()`.
2. **Execute Benchmark Scenarios**:
   - Micro-scenarios: spatial grid indexing, trace calculation, fingerprint hashing, snapshot deepcopy.
   - Macro-scenarios: full end-to-end M1–M6 synthetic pipeline.
3. **Compare Against SLA Thresholds**:
   - Ensure spatial query $\le 1.0\,\text{ms}$, trace calc $\le 0.05\,\text{ms}$, pipeline $\le 10\,\text{ms}$.
   - Flag any regression $> 20\%$ as an engineering concern.
4. **Log Benchmark Manifest**:
   - Store results in `docs/performance/` or task evidence log.
