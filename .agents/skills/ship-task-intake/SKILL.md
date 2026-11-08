---
name: ship-task-intake
description: Intake and mission contract preparation for concrete Ship Tasks resulting in design changes or deliverables.
triggers:
  - "ship task"
  - "deliverable"
  - "build"
  - "implement"
  - "modify"
  - "create"
inputs:
  user_intent: string
  target_board: string
outputs:
  task_contract: dict
  required_locks: list
  admitted: boolean
authoritative_pipeline: M0
replay_safety: SAFE_IDEMPOTENT
---

# Ship Task Intake Skill

## Purpose
Formats and validates requests that produce concrete engineering modifications, schematics, placements, routes, or copper pours.

## Procedural Execution Checklist

1. **Mission Contract Specification**:
   - Define input parameters, expected deliverables, and success criteria.
   - Bind current `DesignProfile` revision.
2. **Resource & Lock Admission**:
   - Request atomic cross-process writer lock (`desk/ops.py`).
   - Check host resource availability (scheduler admission).
3. **Enqueue to Durable Inbox**:
   - Assign monotonic sequence ID.
   - Transition task state: `QUEUED` $\rightarrow$ `PREPARING`.
4. **Delegate to Authoritative Crew**:
   - Spawn targeted worker with relevant domain skill.
