---
name: execution-recovery
description: Procedural workflow for handling pipeline failures, checkpoint rollback, and safe re-execution.
triggers:
  - "recover"
  - "rollback"
  - "checkpoint"
  - "restore"
  - "retry"
  - "abort"
inputs:
  failed_task_id: string
  error_details: dict
outputs:
  recovered: boolean
  restored_checkpoint_id: string
  next_action: string
authoritative_pipeline: Runtime
replay_safety: SAFE_IDEMPOTENT
---

# Execution Recovery Skill

## Purpose
Safely restores project state to a known-good checkpoint after a bridge failure, DRC violation, or execution abort.

## Procedural Execution Checklist

1. **Isolate Failure Cause**:
   - Determine whether failure is transient (EDA socket timeout, lock contention) or deterministic (DRC violation, physical clearance overlap).
2. **Checkpoint Rollback**:
   - Locate the most recent valid snapshot checkpoint via `desk/runtime/checkpoints.py`.
   - Restore internal snapshot geometry and state ledger.
3. **External Reconciliation**:
   - If writing to EasyEDA Pro, issue `reconcile` command to read back canvas primitives and remove phantom tracks/vias.
4. **Transition Task State**:
   - Transition task through `RECOVERING`. If retry budget remains, set to `RUNNING`; otherwise set to `FAILED` and notify Captain.
