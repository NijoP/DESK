# DESK Live EasyEDA Pro Integration Checklist

This checklist documents the prerequisites, verification steps, expected results, and abort/rollback procedures for running a live integration test against EasyEDA Pro.

> [!CAUTION]
> **DO NOT EXECUTE ON PRODUCTION OR CUSTOMER PROJECTS.**
> Live integration tests must ONLY be run against an explicitly designated disposable test project (e.g. `projects/DISPOSABLE_TEST`).
> Never run while a customer PCB (e.g. `WATCH`, `BEEBOX`) is open in EasyEDA Pro.

---

## 1. Pre-Flight Verification & Safety Gates

- [ ] **Target Project Isolation**: Verify that the project path contains `DISPOSABLE` or `TEST`.
- [ ] **Customer Board Protection**: Confirm that `projects/WATCH` and customer workspaces are closed or inactive.
- [ ] **Bridge Health Check**:
  - Check that EasyEDA Pro is running with API Gateway enabled (`EDA_PORT=49620` or detected in `49620..49629`).
  - Verify editor version via `sys_Environment.getEditorCurrentVersion()`.
- [ ] **Git Working Tree State**: Confirm local working tree is clean (`git status`) before executing mutations.

---

## 2. Nine-Stage Live Verification Sequence

| Stage | Operation | API / Tool | Expected Result | Pass Criteria |
|---|---|---|---|---|
| **1** | **Connection & Document Identity** | `eda.dmt_SelectControl.getCurrentDocumentInfo()` | Active document matches target `pcb_uuid` | `uuid === pcb_uuid` |
| **2** | **PCB Primitive Readback** | `EasyEDAPcbAdapter.build_batch_readback_script` | Full primitives dictionary returned in single call | Components, lines, vias, pours > 0 |
| **3** | **Component Placement Verification** | `pcb_PrimitiveComponent.get` & bounding boxes | Component coordinates within board dimensions | Coordinates match `placement.json` |
| **4** | **Ground Copper-Zone Creation** | `pcb_MathPolygon.createPolygon`, `pcb_PrimitivePour.create` | Ground pour zone created on layer 2 (or bottom) | Returns valid `primitive_id` |
| **5** | **Power Polygon Creation** | `pcb_PrimitivePour.create` with `priority: 2` | Switch node/power polygon created with higher priority | Zone created and priority set |
| **6** | **Global Copper Repour** | `pcb_PrimitivePour.rebuildCopperRegion()` | All copper regions rebuilt successfully | `repoured_count == total` |
| **7** | **Poured Copper Readback** | `pcb_PrimitivePoured.getAll()` | Poured copper primitives detected and mapped to nets | Poured regions exist for GND and PWR |
| **8** | **Live DRC Execution** | `eda.pcb_Drc.check(true, true, true)` | DRC executed through EasyEDA native engine | Returns list of DRC violations |
| **9** | **Manufacturing Export** | `eda.pcb_ManufactureData.getDsnFile` / Gerber | Output files generated on disk | Export file size > 0 bytes |

---

## 3. Rollback & Abort Procedures

If any stage fails during a live execution:
1. **Immediate Halt**: Terminate script execution; do not proceed to subsequent mutations.
2. **Zone Cleanup**: Execute `eda.pcb_PrimitivePour.delete(primitiveIds)` to remove test zones created during the run.
3. **Document Re-check**: Inspect EasyEDA canvas visually to confirm that board state has returned to pristine baseline.
4. **Log Incident**: Record error details, JS call trace, and unexpected EasyEDA responses in `state/live_test_error.log`.
