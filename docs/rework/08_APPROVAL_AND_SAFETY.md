# DESK Rework Mode: Human Approval & Safety Gating

**Document ID:** `docs/rework/08_APPROVAL_AND_SAFETY.md`  

---

## 1. Approval Token Architecture (`ApprovalToken`)

No automated mutation may be executed without a cryptographically bound approval token:

```json
{
  "token": "RW-APR-ADC566865D66",
  "repair_id": "RP-0006",
  "session_id": "rework_1794167405_147b15",
  "project_id": "WATCH",
  "revision_hash": "732025a1f8ce04ab",
  "action_type": "NUDGE_COMPONENT",
  "granted_at": 1794167433.0,
  "granted_by": "CAPTAIN",
  "is_valid": true
}
```

### Invariants
1. **Revision Binding:** The token is tied to the exact PCB revision hash. If the PCB is changed, the token is permanently invalidated.
2. **Project Isolation:** An approval token from one project cannot be reused on another project.
3. **Action-Specific:** A token authorizing a track nudge cannot be applied to a net reassignment.

---

## 2. High-Risk Operations Requiring Explicit Sign-Off

The following operations strictly require human approval:
- Netlist or topology modifications.
- Component footprint replacement.
- Moving locked mechanical connectors.
- Ripping up existing traces.
- Modifying power or protection circuits.
- Changing dielectric stackup.
- Waiving or suppressing DRC violations.
- Manufacturing release sign-off.
