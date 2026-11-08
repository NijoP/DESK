# Domain A: EasyEDA Pro Integration & Mutation Safety

**Author:** Principal EDA Integration Engineer  
**Scope:** Official `easyeda-pro` CLI Integration, Local IPC Bridge, and Fail-Closed Mutation Safety  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Reference

---

## 1. Architecture Overview

DESK's EasyEDA Pro integration connects two access modes:
1. **The Official EasyEDA Pro CLI (`easyeda-pro`)**: System process discovery, diagnostic health verification (`doctor`), and session enumeration (`session list`).
2. **The Local IPC Bridge (`desk/bridge.py`)**: Sub-millisecond TCP port discovery (ports 49620–49630) for interactive document queries, netlist extraction, and layout readback.

```
                    ┌────────────────────────┐
                    │      DESK Engine       │
                    └───────────┬────────────┘
                                │
         ┌──────────────────────┴──────────────────────┐
         ▼                                             ▼
┌─────────────────────────────┐             ┌─────────────────────────────┐
│  EasyEDA Pro Official CLI   │             │   Fast IPC Bridge / Socket  │
│  (Session list, doctor)     │             │   (Port 49620-49630)        │
└──────────────┬──────────────┘             └──────────────┬──────────────┘
               │                                           │
               └───────────────────┬───────────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │      Safety Barrier         │
                    │  - Customer Pattern Guard   │
                    │  - Pre-mutation Snapshot    │
                    │  - Captain Authorization    │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │  EasyEDA Pro CAD Workspace  │
                    └─────────────────────────────┘
```

---

## 2. Protected Project Patterns & Mutation Safety Gates

### 2.1 The Customer Protection Boundary
Under no circumstances may autonomous AI agents inject writes, modifications, deletions, or placement edits into production customer PCBs.
DESK strictly enforces the following rules in `EasyEDAProManager.assert_mutation_permitted()`:
- **Protected Name Patterns**: Any project name containing `WATCH`, `BEEBOX`, `CUSTOMER`, or `PRODUCTION` immediately aborts any write operation with a `SafetyViolationError`.
- **Pre-Mutation Snapshot Requirement**: A verified snapshot must exist in the project's `.snapshot/` history before mutating any file.
- **Explicit Captain Authorization**: Outside verified disposable testing projects, all live writes halt and require explicit Captain confirmation.

### 2.2 Offline Readback & Inspection
All diagnostic and extraction routines run non-destructively:
- **Project Structure**: Discovers schematics, PCB documents, netlists, and metadata without opening EasyEDA Pro GUI windows.
- **PCB Primitive Extraction**: Parses JSON and tabular primitive definitions (components, pads, tracks, vias, zones, poured copper, outlines) directly from disk.

---

## 3. Python API Reference

```python
from desk.eda.easyeda_pro import get_easyeda_manager, SafetyViolationError

mgr = get_easyeda_manager()

# 1. Offline Project Inspection (Safe)
info = mgr.inspect_project_offline("projects/my_board")
print("Protected:", info["is_protected"])

# 2. Safety Gate Assertion
# Will raise SafetyViolationError if project is protected or lacks snapshot:
mgr.assert_mutation_permitted(
    project_path_or_name="projects/my_board",
    is_disposable_test=False,
    has_snapshot=True,
    captain_approval=True
)

# 3. Readback Primitives
primitives = mgr.read_pcb_primitives_offline("projects/my_board/pcb.json")
for comp in primitives.components:
    print(comp["id"], comp["footprint"])
```
