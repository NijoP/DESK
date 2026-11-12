import sys, os, json, collections
DESK = r"C:\nemotron test\Plotus\DESK"; sys.path.insert(0, DESK)
from desk.bridge import ex, guard
W = "17ea844c-a5d0-4a6a-b78a-b64521ae7895"
out = sys.argv[1]
r = ex(guard("bb03148ad5ac7687") + 'const r=await eda.pcb_Drc.check(true,false,true); return r;', window_id=W, timeout=600)
json.dump(r, open(out, "w"), indent=1)
c = collections.Counter(); ex_ = []
for cat in r:
    for sub in cat.get("list", []):
        for it in sub.get("list", []):
            c[(cat["name"], sub["name"])] += 1
            p = (it.get("explanation") or {}).get("param", {})
            if cat["name"] == "Clearance Error" and len(ex_) < 12:
                ex_.append((sub["name"], p.get("minDistance"), p.get("shouldBe"), (it.get("obj1") or {}).get("suffix"), (it.get("obj2") or {}).get("suffix"), it.get("pos")))
print("TOTAL", sum(c.values()), dict(c))
for e in ex_: print(e)
