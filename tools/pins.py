"""Dump the real symbol pins (number + name) of library devices into library/pins/<MPN>.json.
Write the block 'pins' map from THIS output, never from memory or the datasheet alone.
Usage: python tools/pins.py projects/<product>      (all MPNs of the product without pin cache)
       python tools/pins.py --mpn TPS62840DLCR ...
The part is placed far off-sheet on the ACTIVE schematic and deleted again."""
import sys, os, json
from _common import ex, S

args = sys.argv[1:]
lib = S.load_library()
want = args[1:] if args and args[0] == "--mpn" else sorted({p["mpn"] for b in S.load_blocks(args[0]) for p in b["parts"]})
os.makedirs(S.PIN_DIR, exist_ok=True)
for m in want:
    if m not in lib: print(f"SKIP {m}: not resolved (run tools/resolve.py)"); continue
    if S.load_pins(m) and "--force" not in args: continue
    d = lib[m]
    r = ex('''const c=await eda.sch_PrimitiveComponent.create({libraryUuid:"%s",uuid:"%s"},-5000,-5000,"",0,false,true,true);
const ps=await c.getAllPins(); const o=ps.map(p=>({num:p.getState_PinNumber(),name:p.getState_PinName()}));
await eda.sch_PrimitiveComponent.delete([c.getState_PrimitiveId()]); return o;''' % (d["libraryUuid"], d["uuid"]))
    r.sort(key=lambda q: (len(q["num"]), q["num"]))
    json.dump(r, open(os.path.join(S.PIN_DIR, S.safe(m) + ".json"), "w", encoding="utf-8"), indent=0)
    print(f"{m}: " + ", ".join(f"{q['num']}={q['name']}" for q in r))
