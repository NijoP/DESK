# 06 — EasyEDA Pro connection + API notes

## How the connection works

```
DESK python tool ──HTTP──► Bridge server (Node.js, localhost:49620-49629) ◄──WebSocket── EasyEDA Pro + "Run API Gateway" extension
```
DESK sends JavaScript to `POST /execute`; the extension runs it inside the open EasyEDA window and returns the result.

## One-time setup
1. **Install Node.js 18+** and **Python 3.9+**.
2. **Install the EasyEDA extension** "Run API Gateway" (`run-api-gateway.eext`):
   https://jlc-ext.com/item/oshwhub/run-api-gateway
   In EasyEDA Pro: *Settings / Extensions → Extension Manager → Import* the `.eext`, enable it.
   Allow it external interaction if EasyEDA asks.
3. **Get a bridge server.** Any server that speaks this protocol works. The open `easyeda-api` agent skill ships one:
   `scripts/bridge-server.mjs` (run `npm install` once in the skill folder).

## Every session
```bash
# 1. start the bridge in the background (it picks a free port 49620-49629)
node <path-to>/bridge-server.mjs &

# 2. open EasyEDA Pro + your project; the extension connects automatically. Check:
curl http://localhost:49620/health          # -> service: easyeda-bridge
curl http://localhost:49620/eda-windows     # -> count >= 1

# 3. several EasyEDA windows? pick one
curl -X POST http://localhost:49620/eda-windows/select -H "Content-Type: application/json" -d '{"windowId":"<id>"}'

# 4. DESK smoke test (open the schematic page first, copy its uuid into project.json)
python tools/ping.py
```
DESK auto-discovers the port (scans 49620-49629). Force one with `EDA_PORT=49621`.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `Bridge not reachable` | bridge not started, or blocked by firewall; check `/health` |
| `/eda-windows` count 0 | extension not enabled / EasyEDA not open / reload the extension |
| `STOP: WRONG SHEET` | the page in `project.json` `sheet_uuid` is not the one open; run `ping.py`, fix uuid |
| timeouts on big blocks | the bridge retries are slow while EasyEDA is busy; wait, then run `verify.py` — it tells you what exists |
| script runs but nothing visible | API screenshots can be stale; check the live screen, trust `verify.py` |

## API calls DESK relies on (EasyEDA Pro 2.x/3.x)
| Purpose | Call |
|---|---|
| active doc / guard | `eda.dmt_SelectControl.getCurrentDocumentInfo()`, `eda.dmt_EditorControl.openDocument(uuid)` |
| library search | `eda.lib_Device.search(mpn)` → `{uuid, libraryUuid, name, supplierId, footprintName}` |
| place part | `eda.sch_PrimitiveComponent.create({libraryUuid, uuid}, x, y, "", 0, false, true, true)` |
| move / designator | `eda.sch_PrimitiveComponent.modify(id, {x, y, designator})` |
| pins | `eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id)` → `getState_PinNumber/Name/X/Y/Rotation()` |
| wire stub | `eda.sch_PrimitiveWire.create([x1,y1,x2,y2], net)` |
| net label | `eda.sch_PrimitiveAttribute.createNetLabel(x, y, net)` |
| NC flag | `pin.setState_NoConnected(true); await pin.done()` |
| frame / title | `eda.sch_PrimitiveRectangle.create(...)`, `eda.sch_PrimitiveText.create(...)` |
| netlist | `eda.sch_Netlist.getNetlist("Protel2")` |
| PCB parts | `eda.pcb_PrimitiveComponent.get/modify`, `getAllPinsByPrimitiveId`, `eda.pcb_Primitive.getPrimitivesBBox` |

## Hard-won gotchas
- **Labels close together merge nets.** That is why stubs alternate length and `verify.py` flags "unexpected net".
- **Pin names repeat** (GND ×4); always map by **pin number**.
- **Pin rotation** tells which side the pin exits: 180 = left, 0 = right, 90/270 = top/bottom.
- Schematic units = 0.01 inch. PCB API units = mil (1 mm = 39.37 mil).
- Keep each `/execute` call small (≤ ~40 parts); big jobs are chunked by the tools.
- Only **one writer** on the live project at a time.
