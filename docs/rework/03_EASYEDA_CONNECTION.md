# DESK Rework Mode: ECAD Connection & Project Identity

**Document ID:** `docs/rework/03_EASYEDA_CONNECTION.md`  

---

## 1. Zero-Disruption Connection

Rework Mode reuses DESK's high-speed bridge architecture (`desk/bridge.py`):
- Connects to local EasyEDA Pro bridge (ports `49620..49629`).
- Queries active windows (`GET /eda-windows`).
- Identifies active project via `eda.dmt_Project.getCurrentProjectInfo()`.
- Identifies active documents (PCB UUID, Sheet UUID) via `eda.dmt_SelectControl.getCurrentDocumentInfo()`.

---

## 2. Project Binding Contract (`ProjectBinding`)

Before any analysis or mutation, DESK constructs a `ProjectBinding`:
- `project_name`
- `project_path`
- `project_uuid`
- `window_id`
- `pcb_uuid`
- `sheet_uuid`
- `eda_port`

### Protection Against Project Switching
If the engineer switches projects or opens another tab in EasyEDA Pro, `ECADConnectionManager.verify_binding()` detects the change, raises `ProjectMismatchError`, and pauses all operations. DESK will never accidentally modify the wrong project.
