"""Draw ONE block on the product sheet in the DESK style (desk/draw.py). Additive and guarded.
Usage: python tools/build.py projects/<product> <BLOCK_ID> [--at X Y]
Refuses to run if: lint fails for the block, the active sheet is not project.json 'sheet_uuid',
or any designator of the block already exists on the sheet (=> use tools/clear_block.py first).
Placement: blocks flow left->right in rows (row_max), new row below the tallest block. Position saved in state/layout.json."""
import sys, os, json
from _common import ex, guard, load_project, check, S
from desk.draw import block_js, STYLE
from desk import ledger as LG

args = sys.argv[1:]
proj, bid = args[0], args[1]
P = load_project(proj)
E, _ = S.lint(proj, bid)
if E:
    for e in E: print("ERROR", e)
    raise SystemExit("STOP: lint failed - fix the block spec first (python tools/lint.py)")
b = S.find_block(proj, bid)
lib = S.load_library()
nopin = sorted({p["mpn"] for p in b["parts"] if S.load_pins(p["mpn"]) is None})
if nopin:
    raise SystemExit(f"STOP: no pin cache for {nopin} -> python tools/pins.py --mpn {' '.join(nopin)}, then re-check the pin map")
pin_counts = {m: len(S.load_pins(m) or []) for m in {p["mpn"] for p in b["parts"]}}
G = guard(P["sheet_uuid"])

st_file = os.path.join(proj, "state", "layout.json")
os.makedirs(os.path.dirname(st_file), exist_ok=True)
st = json.load(open(st_file)) if os.path.exists(st_file) else {"cursor": [100, P.get("top", 3200)], "row_h": 0, "blocks": {}}
if bid in st["blocks"]:
    raise SystemExit(f"STOP: {bid} already built at {st['blocks'][bid]} - run tools/clear_block.py {proj} {bid} first")

existing = check(ex(G + 'const cs=await eda.sch_PrimitiveComponent.get(await eda.sch_PrimitiveComponent.getAllPrimitiveId());'
                        'return cs.map(c=>c.getState_Designator()).filter(x=>x);'))
clash = sorted(set(existing) & {p["ref"] for p in b["parts"]})
if clash:
    raise SystemExit(f"STOP: designators already on sheet: {clash}")

from desk import ops
if "--at" in args:
    i = args.index("--at"); x, y = int(args[i + 1]), int(args[i + 2])
else:
    x, y = st["cursor"]
with ops.write_op(proj, "build", bid, force_unlock="--force-unlock" in args) as rec:
    rec["dirty"] = True                      # from here on the sheet may change
    res = check(ex(G + block_js(b, lib, x, y, pin_counts), timeout=600))
    W, H = res["W"], res["H"]
    st["blocks"][bid] = {"x": x, "y": y, "W": W, "H": H}
    nx, rh = x + W + STYLE["block_gap"], max(st["row_h"], H)
    if nx > P.get("row_max", 5200):
        st["cursor"], st["row_h"] = [100, y - rh - STYLE["block_gap"]], 0
    else:
        st["cursor"], st["row_h"] = [nx, y], rh
    with open(st_file, "w") as f: json.dump(st, f, indent=1)
    LG.add(proj, "built", f"built at ({x},{y}) size {W:.0f}x{H:.0f}, {len(res['REF'])} parts", block=bid, spec_hash=LG.block_hash(b, lib))
print(f"BUILT {bid} '{b['title']}' at ({x},{y}) size {W:.0f}x{H:.0f}, {len(res['REF'])} parts")
print(f"NEXT: python tools/verify.py {proj} {bid}")
