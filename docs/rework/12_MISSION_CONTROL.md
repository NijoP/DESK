# DESK Rework Mode: Local Mission Control Integration

**Document ID:** `docs/rework/12_MISSION_CONTROL.md`  

---

## 1. Local Mission Control Dashboard

Rework Mode seamlessly projects live telemetry to DESK's built-in cockpit at:
```text
http://127.0.0.1:49630
```

---

## 2. Rework Dashboard Panels

- **Project Identity:** Active project name, window ID, PCB UUID, bridge port.
- **Audit Summary:** Real-time counts of issues across Critical, High, Medium, Low, and Informational tiers.
- **Surgical Repair Queue:** Dependency-ordered actions showing `[PENDING]`, `[APPROVED]`, `[VERIFIED]`.
- **Active Repair Cockpit:** Current surgical operation, affected objects, elapsed time, and readback status.
- **Manufacturing Readiness:** Real-time pass/fail indicators for all 8 hard quality gates.

---

## 3. Dedicated REST Endpoints

| Endpoint | Method | Scope |
|---|---|---|
| `/api/rework/session` | `GET` | Active session metadata, lifecycle state, policy, issue counts |
| `/api/rework/issues` | `GET` | Complete 8-domain issue inventory with evidence |
| `/api/rework/plan` | `GET` | Dependency-ordered surgical repair plan |
| `/api/rework/history` | `GET` | Append-only execution history and readback logs |
