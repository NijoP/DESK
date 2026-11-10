# Known Failure Patterns Index

Searchable summary of previously encountered failure patterns in DESK engineering operations.

---

## KF-20251111-001: Bridge Monolithic Script Failure

### Failure Pattern
**500 Internal Server Error / "a is not iterable"** when executing large JavaScript scripts via EasyEDA bridge.

### Root Cause
Bridge server resource limits (execution time, memory, payload size) exceeded by monolithic scripts >100 lines using multiple `getAll()` + `map()` operations.

### Symptoms
- Non-deterministic 500 errors
- "a is not iterable" or similar V8 internal errors
- Same script sometimes works, sometimes fails
- Large return payloads (>5KB)

### Proven Resolution
Decompose into atomic single-domain calls (<100 lines, <15s timeout, <5KB return each).

### Prevention Rule
**BRIDGE_ATOMIC_OPERATIONS:** Every bridge execution targets one primitive type. Max 100 lines, 15s timeout, 5KB payload.

### Related Incident
INC-20251111-001

### Confidence
CONFIRMED

---

## KF-20251111-002: Document Type Primitive Restriction

### Failure Pattern
**"Unable to create region primitive, possibly incorrect parameters"** when calling `pcb_PrimitiveRegion.create(layer=11, ...)` on PCB document.

### Root Cause
PCB documents and Panel documents have different primitive creation capabilities. Board outline regions (layer 11) only allowed on Panel documents.

### Symptoms
- Same parameters work on Panel doc, fail on PCB doc
- Error suggests parameter problem but parameters are correct
- `dmt_Pcb.createPcb()` used for panelisation task

### Proven Resolution
Use `dmt_Panel.createPanel()` for manufacturing panels, not `dmt_Pcb.createPcb()`.

### Prevention Rule
**DOCUMENT_TYPE_MATCHING:** Panelisation → `dmt_Panel.createPanel()`, Single PCB → `dmt_Pcb.createPcb()`, Schematic → `dmt_Schematic.createSchematic()`.

### Related Incident
INC-20251111-002

### Confidence
CONFIRMED

---

## KF-20251111-003: Bridge Window Disconnection During Long Operations

### Failure Pattern
**"EDA window 'xxx' disconnected"** 500 error after ~60-120 seconds of sustained bridge activity.

### Root Cause
EasyEDA bridge WebSocket connection has idle/activity timeout. Client disconnects and reconnects with new window ID during long operations.

### Symptoms
- Operations succeed for first 1-2 minutes
- Then 500 error with "disconnected" message
- `/eda-windows` shows new `activeWindowId`
- Cached window ID becomes invalid

### Proven Resolution
Auto-discover window ID per call (or 30s TTL). Retry once on disconnect error with new window ID.

### Prevention Rule
**BRIDGE_WINDOW_RESILIENCE:** No global window ID caching. Auto-retry on disconnect (max 2). Log rotation events.

### Related Incident
INC-20251111-003

### Confidence
CONFIRMED

---

## KF-20251111-004: Copper Pour Polygon Translation Failure (HYPOTHESIS)

### Failure Pattern
Copper pour zones (`pcb_PrimitivePour`) not correctly translated when using `modify()` with `complexPolygon` parameter.

### Root Cause (Hypothesis)
Pour polygon translation requires rebuilding the pour from translated vertices, not modifying the complexPolygon in place. The `complexPolygon` property may be read-only or require specific vertex format.

### Symptoms
- Pour zones remain at original position after translate script
- No error reported, but geometry unchanged
- Tracks, vias, components translate correctly

### Proven Resolution (Pending)
Recreate pour zones at target position instead of translating. Extract pour net/layer/priority, delete original, create new at translated position.

### Prevention Rule
**COPPER_POUR_TRANSLATION:** Never translate pours via `modify(complexPolygon)`. Always recreate at target position with same properties.

### Related Incident
Not yet encountered (anticipated during panel copy)

### Confidence
HYPOTHESIS

---

## KF-20251111-005: Net Name Collision in Panel Copies (ANTICIPATED)

### Failure Pattern
Electrical connectivity between panel copies due to shared net names (e.g., "GND", "VCC" connecting across board instances).

### Root Cause
Net names are global in EasyEDA project. Copying PCB duplicates net names, creating unintended connections across panel instances.

### Symptoms
- DRC shows short circuits between copies
- Ratlines connect pads across board boundaries
- Copper pours merge across gaps

### Proven Resolution (Pending)
Rename nets in each copy with instance prefix (e.g., "GND_0", "GND_1", "VCC_0", "VCC_1") or use panel-local net scoping if supported.

### Prevention Rule
**PANEL_NET_ISOLATION:** After copying PCB to panel, rename all nets with instance suffix before copper refill.

### Related Incident
Not yet encountered (anticipated during panel copy)

### Confidence
HYPOTHESIS (based on EasyEDA net architecture)

---

## KF-20251111-006: Poured Region Getter API Mismatch

### Failure Pattern
`pr.getState_Net()` is not a function on `pcb_PrimitivePoured` objects.

### Root Cause
`pcb_PrimitivePoured` has different API surface than `pcb_PrimitivePour`. Uses `pourPrimitiveId` and `pourFills` properties instead of getter methods.

### Symptoms
- Bridge error: "pr.getState_Net is not a function"
- Works for `pcb_PrimitivePour` but not `pcb_PrimitivePoured`

### Proven Resolution
Use property access: `pr.pourPrimitiveId`, `pr.pourFills` instead of `getState_Net()`, `getState_Layer()`.

### Prevention Rule
**API_SURFACE_VALIDATION:** Test getter methods on each primitive type before bulk extraction. Don't assume uniform API.

### Related Incident
INC-20251111-001 (encountered during poured region extraction)

### Confidence
CONFIRMED

---

## Search Index

| Pattern | Subsystem | Status | Keywords |
|---------|-----------|--------|----------|
| KF-20251111-001 | bridge | CONFIRMED | 500, monolithic, iterable, timeout |
| KF-20251111-002 | easyeda-api | CONFIRMED | region, layer 11, document type |
| KF-20251111-003 | bridge | CONFIRMED | disconnected, window, rotation |
| KF-20251111-004 | copper | HYPOTHESIS | pour, translate, polygon |
| KF-20251111-005 | panelisation | HYPOTHESIS | net, collision, isolation |
| KF-20251111-006 | easyeda-api | CONFIRMED | poured, getter, API surface |

---

## Usage

Before attempting risky operations:
1. Search this index for relevant patterns
2. Apply prevention rules
3. If pattern matches, use proven resolution
4. If new failure, document as new incident