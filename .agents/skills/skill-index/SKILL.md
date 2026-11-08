---
name: skill-index
description: Central trigger index and routing matrix for conditional skill loading in DESK.
triggers:
  - "index"
  - "skills"
  - "catalog"
  - "capabilities"
authoritative_pipeline: M0
replay_safety: SAFE_READ
---

# DESK Skill Trigger Index

This index is the single source of truth for conditional skill resolution in DESK. When the Captain or First Mate processes an instruction, the deterministic skill loader (`desk/skills.py`) matches keywords, regex patterns, and engineering domains against this matrix to load only the necessary procedural skills into the agent context.

## Skill Routing Matrix

| Skill Name | Path | Authoritative Pipeline | Triggers / Keywords | Mission Type |
| :--- | :--- | :--- | :--- | :--- |
| **ship-task-intake** | `.agents/skills/ship-task-intake/SKILL.md` | M0 | `ship task`, `deliverable`, `build`, `implement`, `modify`, `create` | Ship Task |
| **scout-task-intake** | `.agents/skills/scout-task-intake/SKILL.md` | M0 | `scout`, `investigate`, `audit`, `query`, `explain`, `inspect` | Scout Task |
| **schematic-engineering** | `.agents/skills/schematic-engineering/SKILL.md` | M1 | `schematic`, `netlist`, `symbol`, `pinout`, `connectivity`, `port` | Ship / Scout |
| **component-selection** | `.agents/skills/component-selection/SKILL.md` | M1 | `component`, `part`, `footprint`, `package`, `bom`, `datasheet`, `lcsc` | Ship / Scout |
| **placement-engineering** | `.agents/skills/placement-engineering/SKILL.md` | M2 | `place`, `placement`, `cluster`, `thermal`, `decoupling`, `orientation` | Ship Task |
| **pcb-routing** | `.agents/skills/pcb-routing/SKILL.md` | M3 | `route`, `routing`, `track`, `trace`, `via`, `fanout`, `clearance` | Ship Task |
| **differential-pair-engineering** | `.agents/skills/differential-pair-engineering/SKILL.md` | M3 | `diff pair`, `differential`, `usb`, `can`, `ethernet`, `skew`, `length match` | Ship Task |
| **high-current-design** | `.agents/skills/high-current-design/SKILL.md` | M3/M4 | `high current`, `power trace`, `ampere`, `copper weight`, `mosfet`, `buck` | Ship Task |
| **copper-ground-engineering** | `.agents/skills/copper-ground-engineering/SKILL.md` | M4 | `copper`, `pour`, `plane`, `ground`, `gnd`, `polygon`, `thermal relief`, `stitch` | Ship Task |
| **engineering-diagnostics** | `.agents/skills/engineering-diagnostics/SKILL.md` | M5 | `diagnostics`, `drc`, `violation`, `short circuit`, `airwire`, `unrouted` | Scout / Ship |
| **manufacturing-verification** | `.agents/skills/manufacturing-verification/SKILL.md` | M5/M6 | `manufacturing`, `gerber`, `drc check`, `fab`, `drill`, `soldermask`, `release` | Scout / Ship |
| **quality-gate-supervision** | `.agents/skills/quality-gate-supervision/SKILL.md` | M6 | `gate`, `quality`, `pass`, `fail`, `evidence`, `audit`, `sign-off` | Scout / Ship |
| **execution-recovery** | `.agents/skills/execution-recovery/SKILL.md` | Runtime | `recover`, `rollback`, `checkpoint`, `restore`, `retry`, `abort` | Ship Task |
| **benchmark-performance** | `.agents/skills/benchmark-performance/SKILL.md` | Runtime | `benchmark`, `performance`, `profiling`, `latency`, `throughput`, `speed` | Scout Task |

---

## Skill Invocation Protocol

1. Match incoming command or user intent against triggers.
2. Load only the highest-ranking domain skill into the active worker context.
3. Verify that the skill adheres to the authoritative pipeline constraints (M1–M6).
4. Perform task execution through `desk/operation_registry.py` operations.
5. Invalidate or unload skill upon task completion.
