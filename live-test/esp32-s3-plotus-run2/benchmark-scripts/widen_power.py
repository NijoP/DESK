"""Clearance-safe power widening (same mechanism as DESK route.py Phase 16: pcb_PrimitiveLine.modify lineWidth).
1. widen every track of the power nets to TARGET mil; 2. live DRC; 3. any widened track named in a clearance error is
reverted to its original width (neck-down); repeat until no widened track is in a clearance error.
Writes pcb/routing/power_widening.json."""
import sys, os, json
DESK = r"C:\nemotron test\Plotus\DESK"; sys.path.insert(0, DESK)
from desk.bridge import ex, guard
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"; G = guard("bb03148ad5ac7687")
NETS = ["VBUS", "VBUS_PROT", "5V", "3V3"]; TARGET = 12.0
tr = ex(G + 'return (await eda.pcb_PrimitiveLine.getAll()).map(l=>({id:l.primitiveId,net:l.net,w:l.lineWidth}));', window_id=W, timeout=120)
orig = {t["id"]: t["w"] for t in tr if t["net"] in NETS}
def setw(ids, w):
    for i in range(0, len(ids), 60):
        ex(G + 'for(const id of %s){ await eda.pcb_PrimitiveLine.modify(id,{lineWidth:%s}); } return true;' % (json.dumps(ids[i:i + 60]), w), window_id=W, timeout=300)
setw(list(orig), TARGET)
reverted = set()
for it in range(4):
    r = ex(G + 'return await eda.pcb_Drc.check(true,false,true);', window_id=W, timeout=600)
    hit = set()
    for cat in r:
        if cat.get("name") != "Clearance Error": continue
        for sub in cat.get("list", []):
            for e in sub.get("list", []):
                ed = (e.get("explanation") or {}).get("errData", {})
                for k in ("obj1", "obj2"):
                    if ed.get(k) in orig and ed.get(k) not in reverted: hit.add(ed.get(k))
    print("iteration", it, "widened tracks in clearance errors:", len(hit))
    if not hit: break
    for i in hit: ex(G + 'await eda.pcb_PrimitiveLine.modify(%s,{lineWidth:%s}); return true;' % (json.dumps(i), orig[i]), window_id=W, timeout=60)
    reverted |= hit
ex(G + 'return await eda.pcb_Document.save();', window_id=W, timeout=120)
res = {"target_mil": TARGET, "nets": NETS, "tracks_total": len(orig), "widened": len(orig) - len(reverted), "necked_down_reverted": sorted(reverted)}
json.dump(res, open(r"C:\nemotron test\Plotus\run2\ESP32-S3-Development\pcb\routing\power_widening.json", "w"), indent=1)
print({k: v for k, v in res.items() if k != "necked_down_reverted"}, "reverted", len(reverted))
