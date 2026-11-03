"""Resolve MPNs to real EasyEDA library devices and cache them in library/devices.json (shared by all products).
Usage:
  python tools/resolve.py projects/<product>          # every MPN used in the product's blocks
  python tools/resolve.py --mpn TPS62840DLCR C12345   # explicit MPNs or LCSC codes
Rule: exact name match wins; otherwise the candidates are printed and NOTHING is saved -> human picks with --pick."""
import sys, json
from _common import ex, S

args = sys.argv[1:]
pick = None
if "--pick" in args:                       # --pick <MPN> <index>
    i = args.index("--pick"); pick = (args[i + 1], int(args[i + 2])); del args[i:i + 3]
if args and args[0] == "--mpn":
    want = args[1:]
else:
    want = sorted({p["mpn"] for b in S.load_blocks(args[0]) for p in b["parts"]})
lib = S.load_library()
todo = [m for m in want if m not in lib] if not pick else [pick[0]]
for q in todo:
    r = ex('const r=await eda.lib_Device.search(%s); return (r||[]).slice(0,8).map(d=>({name:d.name,lcsc:d.supplierId,'
           'mfr:d.manufacturerId,footprint:d.footprintName,uuid:d.uuid,libraryUuid:d.libraryUuid}));' % json.dumps(q))
    exact = [d for d in r if d["name"] == q or d.get("lcsc") == q or d.get("mfr") == q]
    if pick:
        lib[q] = r[pick[1]]; print(f"PICKED {q} -> {r[pick[1]]['name']}")
    elif len(exact) >= 1:
        lib[q] = exact[0]; print(f"OK   {q} -> {exact[0]['name']} {exact[0].get('lcsc')} {exact[0].get('footprint')}")
    else:
        print(f"??   {q}: no exact match. Candidates:")
        for k, d in enumerate(r): print(f"     [{k}] {d['name']}  {d.get('lcsc')}  {d.get('footprint')}")
        print(f"     -> python tools/resolve.py --pick {q} <index>")
S.save_library(lib)
print("library size:", len(lib))
