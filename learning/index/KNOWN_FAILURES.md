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

## KF-20251111-007: Window Rotation Document Context Loss

### Failure Pattern
**Panel document context lost after window rotation.** Auto-retry succeeds but on wrong document (empty/new PCB).

### Root Cause
Bridge window rotation creates new window context without preserving active document. Retry executes on whatever document is active in new window (often empty/new PCB).

### Symptoms
- Window rotation during long operation
- Retry appears to succeed (HTTP 200)
- But document has wrong content (missing copies, missing copper pours)
- Repour finds 0 pours, DRC passes on empty document

### Proven Resolution (PENDING)
Track target document UUID explicitly. On rotation, re-open specific UUID before retry.

### Prevention Rule
**BRIDGE_DOCUMENT_CONTINUITY:** Track target document UUID. On rotation, re-open specific UUID before retry. Verify document content after rotation.

### Related Incident
INC-20251111-004

### Confidence
HYPOTHESIS (needs verified fix)

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
| KF-20251111-007 | bridge | HYPOTHESIS | window rotation, document context, retry |

---

## Usage

## KF-20261111-004: DSN Without Planes

### Failure Pattern
Autorouter stalls with 100+ unrouted connections on a 4-layer board that has solid GND / power pours.

### Root Cause
EasyEDA's DSN export carries no pours; the router routes every plane-net pin as a trace.

### Symptoms
- GND / 3V3 dominate the unrouted list; plateau from pass ~15

### Proven Resolution
Declare `(plane NET (polygon LAYER 0 ...))` in `(structure)` from `placement.json` `planes` (route.py Phase 9b).

### Prevention Rule
**ROUTE_PLANES_DECLARED:** every pour-backed net has a plane in the DSN matching the pour polygon.

### Related Incident
INC-20261111-007

### Confidence
CONFIRMED

---

## KF-20261111-005: Placement Keep-outs Exported as Router Keep-outs

### Failure Pattern
Router log full of "maze search algorithm could not be created"; plateau at 30-45 unrouted regardless of time budget.

### Root Cause
Placement keep-outs (mic ports, antenna, holes) exported as all-layer `(keepout (polygon signal ...))`; pads inside them are unreachable.

### Symptoms
- Failures concentrate on parts that sit inside or next to keep-outs (mics, module corner pads)

### Proven Resolution
`placement.json` `route_keepouts` (routing-only set); pre-flight: no pad inside a router keep-out.

### Prevention Rule
**ROUTE_KEEPOUTS_PAD_FREE:** abort routing if any pad lies inside a router keep-out.

### Related Incident
INC-20261111-007

### Confidence
CONFIRMED

---

## KF-20261111-006: Freerouting 2.1.0 Never Returns a Partial Board

### Failure Pattern
Engine reaches 5-7 unrouted, keeps looping; orchestrator kills it at budget; no SES; nothing to import.

### Root Cause
Freerouting v2.1.0 ignores `-mp`, `router.max_passes`, `router.autorouter.max_passes` and `job_timeout` (per-run and `%TEMP%\freerouting\freerouting.json`); the SES is written only at 100 %. Newer JARs need Java 25.

### Symptoms
- Pass counter exceeds the configured limit; the run ends only by external kill

### Proven Resolution
None yet for 2.1.0. Workarounds: EasyEDA native autorouter (GUI), Freerouting >= 2.4 on Java 25, or API mode with cancel + output.

### Prevention Rule
**ROUTER_SMOKE_RUN:** before any long run, a 2-pass smoke run must produce a SES on this host.

### Related Incident
INC-20261111-007

### Confidence
CONFIRMED

---

## KF-20261111-007: Board Outline Must Be One Closed Primitive

### Failure Pattern
`getDsnFile()` returns `undefined`; GUI export says "board outline missing"; polyline creation freezes the editor.

### Root Cause
Outline drawn as 36 `pcb_PrimitiveLine` segments; `pcb_PrimitivePolyline.create` with a long explicit vertex list hangs EasyEDA; the `"R"` polygon with radii exports a skewed boundary.

### Symptoms
- DSN export undefined after ~3 s while Gerber and netlist exports work

### Proven Resolution
One polyline from `createPolygon(["R", x, yTop, w, h, 0, 0])` on layer 11; corner keep-outs for routing; rounded fab outline drawn in the GUI until an arc polygon format is verified.

### Prevention Rule
**OUTLINE_SINGLE_PRIMITIVE:** exactly one outline primitive on layer 11 before any export.

### Related Incident
INC-20261111-008

### Confidence
CONFIRMED

---

Before attempting risky operations:
1. Search this index for relevant patterns
2. Apply prevention rules
3. If pattern matches, use proven resolution
4. If new failure, document as new incident