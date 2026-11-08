---
name: desk-architecture
description: Guidance on DESK core architecture, subsystem boundaries, runtime scheduler, and decision ledgers.
triggers:
  - "architecture"
  - "subsystem"
  - "scheduler"
  - "mental model"
  - "context engine"
inputs:
  subsystem_name: string
  task_type: string
outputs:
  architecture_alignment: boolean
  module_targets: list
authoritative_pipeline: INFRA
replay_safety: READ_ONLY
---

# DESK Architecture Skill

## Purpose
Teaches agents how DESK structures its deterministic engineering engines, runtime scheduler, task inbox, and durable decision persistence.

## When to Use
- Navigating the codebase or adding new modules to `desk/`.
- Integrating between schematic intelligence (M1), placement (M2), routing (M3), copper (M4), manufacturing (M5), and verification (M6).
- Interfacing with the single-writer task queue or Context Engine.

## Required Inputs
- Task description or hardware requirement.
- Target project path (`projects/<P>`).

## Relevant DESK Modules
- `desk/profile.py`: Physical and electrical layer stackup contract.
- `desk/mental/compiler.py`: Compact mental-model policy compiler.
- `tools/ctx.py`: Dynamic context engine.
- `tools/ledger.py`: Durable engineering decision log.

## Required Engineering Constraints
- Preserve single-writer serialized mutation lock on all project files.
- Knowledge must precede geometry: electrical parameters must be derived before layout generation.
- Never bypass mental-model boundaries or hardcode fabricator limits into algorithmic cores.

## Recommended Workflow
1. Query Context Engine: `python tools/ctx.py projects/<P> brief`.
2. Inspect target block or subsystem dependencies.
3. Validate architecture decisions against existing records in `projects/<P>/LEDGER.md`.
4. Implement changes within the appropriate pipeline boundary (`M1` through `M6`).
5. Record architectural decisions: `python tools/ledger.py projects/<P> add decision "<what + why>"`.

## Validation Steps
- Verify context engine output: `python tools/ctx.py projects/<P> delta`.
- Run architecture integrity checks: `python -m unittest discover -s tests -p "test_mental*.py"`.

## Failure Conditions & Recovery
- Concurrent writer collisions: Recover lock via `python tools/desk.py recover projects/<P>`.
- Broken mental-model compiles: Inspect compiler output via `desk/mental/compiler.py`.

## Expected Output
- Modally isolated, test-covered code changes adhering to DESK subsystem contracts.

## Documentation References
- [Mental Model Guide](file:///docs/01_MENTAL_MODEL.md)
- [Context Engine Guide](file:///docs/07_CONTEXT_ENGINE.md)
