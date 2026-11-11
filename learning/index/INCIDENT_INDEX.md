# Incident Index

Chronological index of all documented engineering incidents.

---

## 2025-11-11

| ID | Title | Subsystem | Severity | Status | Lessons |
|----|-------|-----------|----------|--------|---------|
| INC-20251111-001 | Bridge Monolithic Script Failure | easyeda-integration / pcb-panelisation | HIGH | RECOVERED | LSN-20251111-001 |
| INC-20251111-002 | Document Type Primitive Restriction | easyeda-integration / pcb-panelisation | HIGH | RECOVERED | LSN-20251111-002 |
| INC-20251111-003 | Bridge Window Disconnection | easyeda-integration / bridge-reliability | CRITICAL | RECOVERED | LSN-20251111-003 |
| INC-20251111-004 | Window Rotation Document Context Loss | easyeda-integration / bridge-reliability / pcb-panelisation | CRITICAL | OPEN | PENDING |
| INC-20261111-005 | 6-up panelisation recovered via native PANELIZE record + SR Gerber; onlyOutline trap; desktop-automation focus hazard | easyeda-integration / panelisation / desktop-automation | HIGH | RESOLVED | in incident file |
| INC-20261111-006 | Rework session bound to the wrong EasyEDA window (0-component baseline) | rework / bridge-reliability | HIGH | RESOLVED | LSN-20261111-004 |
| INC-20261111-007 | Routing engine missing; DSN without planes; placement keep-outs swallowed 20 pads; Freerouting 2.1.0 ignores stop settings | routing / easyeda-integration | MEDIUM | RESOLVED (engine stop still open) | LSN-20261111-004 |
| INC-20261111-008 | DSN export needs one closed outline; polyline creation froze EasyEDA twice | easyeda-integration / outline | HIGH | OPEN (workaround) | LSN-20261111-004 |

---

## By Subsystem

### easyeda-integration
- INC-20251111-001
- INC-20251111-002
- INC-20251111-003
- INC-20251111-004

### pcb-panelisation
- INC-20251111-001
- INC-20251111-002
- INC-20251111-004

### bridge-reliability
- INC-20251111-003
- INC-20251111-004

---

## By Severity

### CRITICAL
- INC-20251111-003
- INC-20251111-004

### HIGH
- INC-20251111-001
- INC-20251111-002

---

## By Status

### RECOVERED
- INC-20251111-001
- INC-20251111-002
- INC-20251111-003

### OPEN
- INC-20251111-004