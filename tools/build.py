"""Draw ONE block on the product sheet in the DESK style (desk/draw.py). Additive and guarded.
Usage: python tools/build.py projects/<product> <BLOCK_ID> [--at X Y]
Refuses to run if: lint fails for the block, the active sheet is not project.json 'sheet_uuid' (or the block's
sheet 'uuid' in a multi-sheet project), or any designator of the block already exists on the sheet (=> use
tools/clear_block.py first).
Wiring style (docs/02_SCHEMATIC_STYLE.md): block 'wiring' > project.json 'wiring' > 'labels'. `labels` draws the block
in one script (stub + label per pin). `subsystem` places the parts, plans in-block wires offline
(desk/schematic_router.py), checks the plan geometrically, then draws it (UNVERIFIED-LIVE adapter); the plan is saved
in state/wiring/<BLOCK_ID>.json.
Placement: blocks flow left->right in rows (row_max), new row below the tallest block. Position saved in state/layout.json."""
import sys, os, json
from _common import ex, guard, load_project, check, S
from desk.draw import block_js, place_js, plan_subsystem, STYLE, SUBSYSTEM_STYLE
from desk import ledger as LG

args = sys.argv[1:]
proj, bid = args[0], args[1]
P = load_project(proj)
# Resolve the alias (file name, stem, numeric prefix) FIRST, then lint and build that one block under its canonical
# id: linting the raw argument let `build.py P 02` lint nothing and draw a block with lint errors (report F-2).
b = S.find_block(proj, bid)
bid = b["id"]
E, _ = S.lint(proj, bid)
if E:
    for e in E: print("ERROR", e)
    raise SystemExit("STOP: lint failed - fix the block spec first (python tools/lint.py)")
try:
    wiring = S.wiring_policy(P, b)
    sheet_uuid = S.sheet_uuid_for(P, [bid])
except ValueError as e:
    raise SystemExit(f"STOP: {e}")
lib = S.load_library()
nopin = sorted({p["mpn"] for p in b["parts"] if S.load_pins(p["mpn"]) is None})
if nopin:
    raise SystemExit(f"STOP: no pin cache for {nopin} -> python tools/pins.py --mpn {' '.join(nopin)}, then re-check the pin map")
pin_counts = {m: len(S.load_pins(m) or []) for m in {p["mpn"] for p in b["parts"]}}
G = guard(sheet_uuid)

st_file = os.path.join(proj, "state", "layout.json")
os.makedirs(os.path.dirname(st_file), exist_ok=True)
st = json.load(open(st_file)) if os.path.exists(st_file) else {"cursor": [100, P.get("top", 3200)], "row_h": 0, "blocks": {}}
if bid in st["blocks"]:
    raise SystemExit(f"STOP: {bid} already built at {st['blocks'][bid]} - run tools/clear_block.py {proj} {bid} first")

existing = check(ex(G + 'const cs=await eda.sch_PrimitiveComponent.get(await eda.sch_PrimitiveComponent.getAllPrimitiveId());'
                        'return cs.map(c=>c.getState_Designator()).filter(x=>x);', window_id=P.get("window_id")))
clash = sorted(set(existing) & {p["ref"] for p in b["parts"]})
if clash:
    raise SystemExit(f"STOP: designators already on sheet: {clash}")

from desk import ops
if "--at" in args:
    i = args.index("--at"); x, y = int(args[i + 1]), int(args[i + 2])
else:
    x, y = st["cursor"]
note = ""
with ops.write_op(proj, "build", bid, force_unlock="--force-unlock" in args, approval=ops.cli_approval(proj, "build", bid)) as rec:
    rec["dirty"] = True                      # from here on the sheet may change
    if wiring == "labels":
        res = check(ex(G + block_js(b, lib, x, y, pin_counts), timeout=600, window_id=P.get("window_id")))
        W, H, nparts = res["W"], res["H"], len(res["REF"])
    else:
        x, y = x - x % 10, y - y % 10        # wires need the block origin on the 10-unit grid
        from desk.schematic_io import subsystem_draw_js
        from desk.schematic_router import check_plan
        from desk.fsutil import atomic_write_json
        placed = check(ex(G + place_js(b, lib, x, y, pin_counts), timeout=600, window_id=P.get("window_id")))
        plan = plan_subsystem(b, S.load_blocks(proj), placed, x, y, P)
        plan["check"] = check_plan(plan, b)
        atomic_write_json(os.path.join(proj, "state", "wiring", bid + ".json"), plan, indent=1)
        if not plan["check"]["ok"]:
            for e in plan["check"]["errors"]: print("ERROR", e)
            raise SystemExit(f"STOP: the wiring plan failed the geometric check; parts are placed, no wire drawn "
                             f"(state/wiring/{bid}.json). Run tools/clear_block.py {proj} {bid}, fix the spec, rebuild")
        check(ex(G + subsystem_draw_js(plan, SUBSYSTEM_STYLE), timeout=600, window_id=P.get("window_id")))
        W, H, nparts = plan["frame"][2], plan["frame"][3], len(placed["REF"])
        wired = sorted(n for n, v in plan["nets"].items() if v["mode"] == "wire")
        note = f"; subsystem wiring: {len(wired)} nets wired, {len(plan['fallback'])} fell back to labels"
        for n, why in plan["fallback"].items(): print(f"NOTE {n} drawn with labels: {why}")
    st["blocks"][bid] = {"x": x, "y": y, "W": W, "H": H}
    if wiring != "labels":
        st["blocks"][bid]["wiring"] = wiring
    nx, rh = x + W + STYLE["block_gap"], max(st["row_h"], H)
    if nx > P.get("row_max", 5200):
        st["cursor"], st["row_h"] = [100, y - rh - STYLE["block_gap"]], 0
    else:
        st["cursor"], st["row_h"] = [nx, y], rh
    with open(st_file, "w") as f: json.dump(st, f, indent=1)
    LG.add(proj, "built", f"built at ({x},{y}) size {W:.0f}x{H:.0f}, {nparts} parts{note}",
           block=bid, spec_hash=LG.block_hash(b, lib))
print(f"BUILT {bid} '{b['title']}' at ({x},{y}) size {W:.0f}x{H:.0f}, {nparts} parts{note}")
print(f"NEXT: python tools/verify.py {proj} {bid}")
