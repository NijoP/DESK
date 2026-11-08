# 05 — DESK Engineering Skills Architecture

This document specifies the standard schema, catalog, and execution constraints for specialized agent skills in `.agents/skills/`.

---

## 1. Canonical Skill Schema

Every DESK skill must adhere to the 10-point engineering schema with standardized YAML frontmatter:

```markdown
---
name: <kebab-case-name>
description: <Concise trigger condition explaining exactly when to load this skill (<= 40 tokens)>
triggers:
  - "<keyword1>"
  - "<keyword2>"
inputs:
  <input_name>: <data_type>
outputs:
  <output_name>: <data_type>
authoritative_pipeline: <M1|M2|M3|M4|M5|M6|INFRA>
replay_safety: <SAFE_IDEMPOTENT|MUTATING_LOCK_REQUIRED|READ_ONLY>
---

# <Title> Skill

## Purpose
<High-level objective and engineering boundary>

## When to Use
<Precise trigger scenarios and prerequisite stages>

## Required Inputs
<Input arguments, formats, files, or state keys>

## Relevant DESK Modules
<Python modules, scripts, or adapters invoked>

## Required Engineering Constraints
<Physical, electrical, or architectural invariants that must never be violated>

## Recommended Workflow
<Numbered, deterministic procedural execution steps>

## Validation Steps
<Tools and commands required to verify completion>

## Failure Conditions & Recovery
<Specific error states, rollback protocols, and retry limits>

## Expected Output
<Final deliverables, logs, or state transitions>

## Documentation References
<Links to docs/*.md and external engineering standards>
```

---

## 2. Core Specialized Skills Catalog

The 10 foundational skills required for autonomous DESK development:

| # | Skill Name | Directory | Pipeline Stage | Primary Purpose |
|---|---|---|---|---|
| **1** | **DESK Architecture** | `desk-architecture` | `INFRA` | Navigating module boundaries, Context Engine (`tools/ctx.py`), and task flow. |
| **2** | **PCB Engineering** | `pcb-engineering` | `M1/M5` | Enforcing IPC-2152/2221 electrical correctness, layer stackups, and copper weights. |
| **3** | **PCB Routing** | `pcb-routing` | `M3` | 6-stage net priority scheduling, trace widths, clearances, and via transitions. |
| **4** | **PCB Placement** | `pcb-placement` | `M2` | Mechanical envelope anchors, connector orientation, and thermal dissipation clusters. |
| **5** | **DRC & Verification** | `drc-validation` | `M6` | 8 fail-closed acceptance gates, connectivity validation, and copper zone continuity. |
| **6** | **EasyEDA Integration** | `easyeda-integration` | `INFRA` | Sub-millisecond socket bridge discovery, project mutation locks, and drawing commands. |
| **7** | **KiCad Integration** | `kicad-integration` | `INFRA` | Netlist import/export, PCB translation, and CLI footprint verification. |
| **8** | **Component Intelligence** | `component-intelligence`| `M1` | Canonical component identity, MPN resolution, datasheet pinouts, and footprint mapping. |
| **9** | **Supplier Integration** | `supplier-integration` | `M1` | LCSC supplier querying, stock snapshots, pricing tiers, and procurement provenance. |
| **10**| **Runtime Performance** | `runtime-performance` | `INFRA` | Resource-aware execution, memory safety, caching, and low-latency benchmarks. |
| **11**| **Repository Maintenance**| `repository-maintenance` | `INFRA` | Test suite execution, linting, Git commit discipline, and Backpass memory tuning. |

---

## 3. Skill Integration with Backpass

1. **Token Cost:** Only the `description` field is loaded into the model's base context window (~25 tokens per skill).
2. **Dynamic Body Injection:** The agent only loads the skill body (`SKILL.md`) when matching user prompt keywords trigger the skill.
3. **Automated Tuning:** When an agent repeatedly fails or rediscovers a procedure across $\ge 2$ sessions, Backpass can propose either:
   - Updating the skill's `description` (if agents failed to trigger it).
   - Refining procedural checklist steps in the skill body.
   - Extracting a new skill from `AGENTS.md` to prevent instruction bloat.
