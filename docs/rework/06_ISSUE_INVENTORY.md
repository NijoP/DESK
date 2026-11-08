# DESK Rework Mode: Issue Inventory Schema

**Document ID:** `docs/rework/06_ISSUE_INVENTORY.md`  

---

## 1. Issue Schema

Every detected defect is assigned a structured record:

```json
{
  "issue_id": "RW-0008",
  "session_id": "rework_1794167405_147b15",
  "category": "routing",
  "severity": "CRITICAL",
  "title": "Unrouted Net '3V3' (39 pads)",
  "description": "Net '3V3' has 39 connected endpoints but 0 routed track segments on the PCB.",
  "affected_objects": {
    "net": "3V3",
    "pads_count": 39
  },
  "evidence": [
    {
      "net": "3V3",
      "endpoints": ["U1.1", "U2.1", "C1.1"]
    }
  ],
  "source_revision": "732025a1f8ce04ab",
  "root_cause_status": "UNKNOWN",
  "proposed_repair": {
    "action": "route_net",
    "net": "3V3"
  },
  "verification_method": "All pads connected with zero open airwires",
  "status": "DETECTED"
}
```

---

## 2. Severity Classification

- **`CRITICAL`**: Electrical shorts, unrouted power rails, duplicate pad numbers, schematic net discrepancies.
- **`HIGH`**: Hard DRC clearance violations, missing bypass caps, unpoured ground planes.
- **`MEDIUM`**: Undersized power traces, stale zones, missing design profile.
- **`LOW`**: Single-pad nets, unassigned test points, documentation notes.
- **`INFORMATIONAL`**: Intentional no-connects, approved DNI parts.
