# Lesson Index

Chronological index of all reusable engineering lessons.

---

## 2025-11-11

| ID | Title | Domain | Confidence | Originating Incident |
|----|-------|--------|------------|---------------------|
| LSN-20251111-001 | Decompose Large Bridge Scripts | EasyEDA API Integration | CONFIRMED | INC-20251111-001 |
| LSN-20251111-002 | Match Document Type to Task | EasyEDA API Integration / Manufacturing | CONFIRMED | INC-20251111-002 |
| LSN-20251111-003 | Bridge Executor Window Resilience | EasyEDA API Integration / Bridge Reliability | CONFIRMED | INC-20251111-003 |

---

## By Domain

### EasyEDA API Integration
- LSN-20251111-001
- LSN-20251111-002
- LSN-20251111-003

### Manufacturing / Panelisation
- LSN-20251111-002

### Bridge Reliability
- LSN-20251111-003

---

## By Confidence

### CONFIRMED
- LSN-20251111-001
- LSN-20251111-002
- LSN-20251111-003

---

## Prevention Rules Summary

| Rule ID | Lesson | Rule Statement |
|---------|--------|----------------|
| BRIDGE_ATOMIC_OPERATIONS | LSN-20251111-001 | Every bridge execution targets one primitive type. Max 100 lines, 15s timeout, 5KB payload. |
| DOCUMENT_TYPE_MATCHING | LSN-20251111-002 | Panelisation → `dmt_Panel.createPanel()`, Single PCB → `dmt_Pcb.createPcb()`, Schematic → `dmt_Schematic.createSchematic()`. |
| BRIDGE_WINDOW_RESILIENCE | LSN-20251111-003 | No global window ID caching. Auto-retry on disconnect (max 2). Log rotation events. |

---

## Applicability Matrix

| Lesson | Panelisation | Placement | Routing | Copper | DRC | Gerber | Batch Ops |
|--------|--------------|-----------|---------|--------|-----|--------|-----------|
| LSN-20251111-001 | YES | YES | YES | YES | YES | YES | YES |
| LSN-20251111-002 | YES | NO | NO | NO | NO | NO | NO |
| LSN-20251111-003 | YES | YES | YES | YES | YES | YES | YES |