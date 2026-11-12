"""Set the hand-designed USB pair tracks back to their design width (EasyEDA's SES import applies the 6-mil rule width),
leaving the 0.15 mm J1 fan-outs; delete zero-length and exact-duplicate USB segments created by the import."""
import sys, json
sys.path.insert(0, r"C:\nemotron test\Plotus\DESK")
from desk.bridge import ex, guard, check
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"; G = guard("bb03148ad5ac7687"); M = 39.37007874
tr = check(ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).filter(l=>l.net=="USB_DP"||l.net=="USB_DN").map(l=>({id:l.primitiveId,net:l.net,x1:l.startX,y1:l.startY,x2:l.endX,y2:l.endY,w:l.lineWidth,layer:l.layer}));', window_id=W, timeout=60))
seen, dele, wide = set(), [], []
for t in tr:
    a = (round(t["x1"] / M, 2), round(t["y1"] / M, 2)); b = (round(t["x2"] / M, 2), round(t["y2"] / M, 2))
    key = (t["net"], t["layer"], tuple(sorted([a, b])))
    if a == b or key in seen: dele.append(t["id"]); continue
    seen.add(key)
    fanout = max(a[0], b[0]) <= 9.21 and not (sorted([a, b]) == [(7.67, 21.25), (9.0, 21.25)])
    if not fanout: wide.append(t["id"])
print("delete", len(dele), "widen", len(wide), "keep 0.15 fan-out", len(tr) - len(dele) - len(wide))
for i in dele:
    try: print("del", i, check(ex(G + "return await eda.pcb_PrimitiveLine.delete([%s]);" % json.dumps(i), window_id=W, timeout=60)))
    except Exception as e: print("del", i, "ERR", e)
print("widen", check(ex(G + "for(const id of %s){ await eda.pcb_PrimitiveLine.modify(id,{lineWidth:10}); } await eda.pcb_Document.save(); return true;" % json.dumps(wide), window_id=W, timeout=120)))
