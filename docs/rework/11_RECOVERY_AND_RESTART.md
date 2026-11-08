# DESK Rework Mode: Session Recovery & Interruption Resilience

**Document ID:** `docs/rework/11_RECOVERY_AND_RESTART.md`  

---

## 1. Resilience to Restarts

If an engineer closes their terminal, restarts EasyEDA Pro, or experiences a power loss during a rework session:
- The session state is preserved under `projects/<P>/state/rework/<SESSION_ID>/`.
- Running `python tools/desk.py rework status projects/<P>` automatically reloads the active session.

---

## 2. Recovery Protocol

When recovering an interrupted session:
1. Reconnect to EasyEDA Pro and re-verify window identity.
2. Read the operation journal (`state/ops.jsonl`).
3. Check if an interrupted non-idempotent write occurred.
4. Load the latest checkpoint from `desk/runtime/checkpoints.py`.
5. Read back current board geometry to detect partial writes.
6. Reconcile verified vs incomplete repairs.
7. **Never blindly re-execute an interrupted non-idempotent write without inspection.**
