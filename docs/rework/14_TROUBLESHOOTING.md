# DESK Rework Mode: Troubleshooting Guide

**Document ID:** `docs/rework/14_TROUBLESHOOTING.md`  

---

## Common Issues & Resolutions

### 1. "No active EasyEDA Pro windows detected"
- **Cause:** EasyEDA Pro is not running, or the API Gateway extension is not active.
- **Resolution:** Launch EasyEDA Pro, open the target project, and ensure the local API server is listening on port `49620`.

### 2. "Active ECAD window no longer matches bound project"
- **Cause:** The engineer focused a different window or opened a new project tab.
- **Resolution:** Switch back to the original project window in EasyEDA Pro, or run `python tools/desk.py rework start` to rebind.

### 3. "External modifications detected"
- **Cause:** The PCB was modified outside DESK after baseline capture.
- **Resolution:** Re-run `python tools/desk.py rework audit` to synchronize the baseline fingerprint and regenerate the repair plan.

### 4. "STOP: Repair requires explicit approval before execution"
- **Cause:** Attempting to execute a repair without granting an approval token.
- **Resolution:** Review the repair in `tools/desk.py rework plan` and approve it with `python tools/desk.py rework approve <RP-XXXX>`.

### 5. "Another writer holds the lock"
- **Cause:** A previous process crashed or an active mutation is running.
- **Resolution:** Check process liveness. Stale locks are automatically reclaimed after TTL; or run `python tools/desk.py recover <PROJECT>`.
