# DESK Rework Mode: Controlled Repair Execution

**Document ID:** `docs/rework/09_REPAIR_EXECUTION.md`  

---

## 1. Single-Writer Mutex Protocol

To prevent corrupted canvas states and race conditions:
- All live mutations acquire the cross-process lock `state/write.lock` via `desk/ops.py`.
- Windows and POSIX PID liveness checks guarantee that stale locks from dead processes are automatically reclaimed without hanging the CLI.
- No two live writers can ever execute simultaneously.

---

## 2. Mutation Transaction Protocol

Every repair follows a strict 12-step transaction sequence:
```text
1. Check Active Project Binding
2. Check Current Revision Hash
3. Verify Approval Token Validity
4. Validate Preconditions & Dependencies
5. Acquire Single-Writer Mutex Lock
6. Save Pre-Mutation Checkpoint (desk/runtime/checkpoints.py)
7. Apply Surgical Mutation
8. Read Back Physical ECAD Geometry
9. Evaluate Verification Criteria
10. Commit to repair_history.jsonl
11. Update Session State
12. Release Mutex Lock
```

If an error or uncertain outcome occurs, the project is flagged `DIRTY` and further automated writes are halted until reviewed.
